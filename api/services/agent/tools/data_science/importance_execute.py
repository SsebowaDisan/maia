from __future__ import annotations

from typing import Any

from api.services.agent.tools.base import ToolExecutionContext, ToolExecutionResult

from .plot_payload import build_interactive_plot_payload
from .quality import _apply_cleaning_steps, _missing_dataset_result, _plan_dataset_cleaning_with_llm
from .shared import _as_int, _import_pandas, _infer_problem_type, _limit_rows, _load_dataframe, _trace_event


def execute_data_science_feature_importance(
    *,
    context: ToolExecutionContext,
    prompt: str,
    params: dict[str, Any],
    tool_id: str,
) -> ToolExecutionResult:
    del prompt
    events = []
    df, source_label, warnings, source_ref = _load_dataframe(context=context, params=params)
    if df is None:
        return _missing_dataset_result(warnings, tool_id=tool_id)
    pd = _import_pandas()
    if pd is None:
        return _missing_dataset_result(
            warnings + ["`pandas` is required but is not installed."], tool_id=tool_id
        )
    target = str(params.get("target") or params.get("target_column") or "").strip()
    if not target:
        return _missing_dataset_result(
            warnings + ["Feature importance requires `target` or `target_column`."], tool_id=tool_id
        )
    if target not in df.columns:
        return _missing_dataset_result(
            warnings + [f"Target column `{target}` was not found."], tool_id=tool_id
        )
    max_rows = max(200, min(_as_int(params.get("max_rows"), 50000), 250000))
    df, truncated = _limit_rows(df, max_rows=max_rows)
    row_count_before = int(len(df))
    col_count = int(len(df.columns))
    events.append(_trace_event(
        tool_id=tool_id, event_type="prepare_request", title="Prepare dataset",
        detail=f"Loaded {row_count_before} rows and {col_count} columns",
        data={"row_count": row_count_before, "column_count": col_count, "target": target},
    ))
    features_raw = params.get("features")
    if isinstance(features_raw, list) and features_raw:
        feature_cols = [str(c).strip() for c in features_raw if str(c).strip() in df.columns and str(c).strip() != target]
    else:
        feature_cols = [c for c in df.columns if c != target]
    numeric_features = [
        c for c in feature_cols
        if pd.api.types.is_numeric_dtype(df[c])
    ]
    required_numeric = numeric_features[:40]
    events.append(_trace_event(
        tool_id=tool_id, event_type="llm.dataset_cleaning_started",
        title="Analyze dataset quality", detail="LLM planning data cleaning",
        data={"workflow": "feature_importance", "target": target},
    ))
    quality_issues, cleaning_plan, llm_cleaning_used = _plan_dataset_cleaning_with_llm(
        df=df, workflow="feature_importance",
        required_numeric=required_numeric, required_columns=[target],
        context_payload={"target": target, "source": source_label or "payload"},
    )
    events.append(_trace_event(
        tool_id=tool_id, event_type="llm.dataset_cleaning_completed",
        title="Dataset quality analysis complete",
        detail=f"Issues: {len(quality_issues)} | planned steps: {len(cleaning_plan)}",
        data={"issues_count": len(quality_issues), "llm_used": llm_cleaning_used},
    ))
    df, cleaning_applied, cleaning_warnings = _apply_cleaning_steps(pd=pd, df=df, steps=cleaning_plan)
    warnings.extend(cleaning_warnings)
    row_count = int(len(df))
    events.append(_trace_event(
        tool_id=tool_id, event_type="api_call_started",
        title="Train Random Forest for feature importance",
        detail=f"{len(numeric_features)} numeric features, target={target}",
        data={"target": target, "n_features": len(numeric_features)},
    ))
    try:
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor  # type: ignore
        from sklearn.preprocessing import LabelEncoder  # type: ignore
    except Exception:
        return _missing_dataset_result(
            warnings + ["`scikit-learn` is required but is not installed."], tool_id=tool_id
        )
    if not numeric_features:
        return _missing_dataset_result(
            warnings + ["No numeric feature columns found for importance analysis."], tool_id=tool_id
        )
    work = df[[*numeric_features, target]].dropna()
    if len(work) < 10:
        return _missing_dataset_result(
            warnings + [f"Too few rows after cleaning ({len(work)}) for feature importance."], tool_id=tool_id
        )
    X = work[numeric_features].values
    y_series = work[target]
    problem_type = _infer_problem_type(y_series, str(params.get("problem_type") or ""))
    if problem_type == "classification":
        le = LabelEncoder()
        y = le.fit_transform(y_series.astype(str))
        n_estimators = max(50, min(_as_int(params.get("n_estimators"), 100), 300))
        rf = RandomForestClassifier(n_estimators=n_estimators, max_depth=10, random_state=42, n_jobs=-1)
    else:
        y = y_series.values
        n_estimators = max(50, min(_as_int(params.get("n_estimators"), 100), 300))
        rf = RandomForestRegressor(n_estimators=n_estimators, max_depth=10, random_state=42, n_jobs=-1)
    rf.fit(X, y)
    importances = rf.feature_importances_.tolist()
    ranked = sorted(
        [{"feature": name, "importance": round(float(imp), 6)} for name, imp in zip(numeric_features, importances)],
        key=lambda x: x["importance"],
        reverse=True,
    )
    events.append(_trace_event(
        tool_id=tool_id, event_type="api_call_completed",
        title="Random Forest training complete",
        detail=f"problem_type={problem_type}, features={len(ranked)}",
        data={"problem_type": problem_type, "n_features": len(ranked), "n_estimators": n_estimators},
    ))
    import pandas as _pd  # noqa: F401
    importance_df = _pd.DataFrame(ranked)
    bar_plot = build_interactive_plot_payload(
        df=importance_df, chart_type="bar", title=f"Feature Importance — {target}",
        x_col="feature", y_col="importance", row_count=len(ranked),
        series_columns=None, top_n=min(len(ranked), 20), bins=20,
    )
    content_lines = [
        f"### Feature Importance ({problem_type.title()})",
        f"- Source: {source_label or 'payload'}, rows={row_count}, target={target}",
        f"- Estimators: {n_estimators}",
        "", "| Rank | Feature | Importance |", "|---|---|---|",
        *[f"| {i + 1} | {r['feature']} | {r['importance']:.6f} |" for i, r in enumerate(ranked[:20])],
    ]
    if warnings:
        content_lines.extend(["", "### Notes", *[f"- {w}" for w in warnings[:6]]])
    context.settings["__feature_importance"] = {
        "target": target, "problem_type": problem_type,
        "ranked": ranked[:30], "row_count": row_count,
    }
    return ToolExecutionResult(
        summary=f"Ranked {len(ranked)} features by importance for target `{target}`.",
        content="\n".join(content_lines),
        data={
            "target": target, "problem_type": problem_type, "ranked_features": ranked,
            "n_estimators": n_estimators, "row_count": row_count, "bar_plot": bar_plot,
            "quality_issues": quality_issues, "cleaning_applied": cleaning_applied,
            "warnings": warnings, "truncated": truncated,
        },
        sources=[source_ref] if source_ref else [],
        next_steps=[
            "Use top-ranked features as `features` param in `data.science.ml.train`.",
            "Use `data.science.stats` mode=correlation to confirm feature relationships.",
        ],
        events=events + [
            _trace_event(
                tool_id=tool_id, event_type="tool_progress",
                title="Feature importance ready",
                detail=f"Top feature: {ranked[0]['feature']} ({ranked[0]['importance']:.4f})" if ranked else "no features",
                data={"top_features": ranked[:5]},
            )
        ],
    )


__all__ = ["execute_data_science_feature_importance"]
