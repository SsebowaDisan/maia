from __future__ import annotations

from typing import Any

from api.services.agent.llm_runtime import call_json_response
from api.services.agent.tools.base import ToolExecutionContext, ToolExecutionResult

from .plot_payload import build_heatmap_payload
from .quality import _missing_dataset_result
from .shared import _as_int, _import_pandas, _limit_rows, _load_dataframe, _trace_event


def _select_analysis_mode(prompt: str) -> tuple[str, str]:
    response = call_json_response(
        system_prompt="You are a statistical analysis planner. Return strict JSON only.",
        user_prompt=(
            "Choose the statistical analysis mode for this request.\n"
            "Modes: correlation (relationships between columns), "
            "descriptive (summary statistics per column), "
            "distribution (normality/skew tests).\n"
            'Return JSON: {"mode": "correlation|descriptive|distribution", "method": "pearson|spearman"}\n'
            "Use spearman only if the user mentions rank/non-parametric/spearman.\n"
            f"Request: {prompt}"
        ),
        temperature=0.0,
        timeout_seconds=10,
        max_tokens=200,
    )
    if not isinstance(response, dict):
        return "descriptive", "pearson"
    mode = str(response.get("mode") or "descriptive").strip().lower()
    if mode not in {"correlation", "descriptive", "distribution"}:
        mode = "descriptive"
    method = str(response.get("method") or "pearson").strip().lower()
    if method not in {"pearson", "spearman"}:
        method = "pearson"
    return mode, method


def execute_data_science_stats(
    *,
    context: ToolExecutionContext,
    prompt: str,
    params: dict[str, Any],
    tool_id: str,
) -> ToolExecutionResult:
    events = []
    df, source_label, warnings, source_ref = _load_dataframe(context=context, params=params)
    if df is None:
        return _missing_dataset_result(warnings, tool_id=tool_id)
    pd = _import_pandas()
    if pd is None:
        return _missing_dataset_result(
            warnings + ["`pandas` is required but is not installed."], tool_id=tool_id
        )
    max_rows = max(100, min(_as_int(params.get("max_rows"), 20000), 200000))
    df, truncated = _limit_rows(df, max_rows=max_rows)
    row_count = int(len(df))
    col_count = int(len(df.columns))
    events.append(_trace_event(
        tool_id=tool_id, event_type="prepare_request", title="Prepare dataset",
        detail=f"Loaded {row_count} rows and {col_count} columns",
        data={"row_count": row_count, "column_count": col_count},
    ))
    prompt_text = " ".join(str(prompt or "").split()).strip()
    mode_param = str(params.get("mode") or "").strip().lower()
    if mode_param in {"correlation", "descriptive", "distribution"}:
        mode: str = mode_param
        method: str = str(params.get("method") or "pearson").strip().lower()
        if method not in {"pearson", "spearman"}:
            method = "pearson"
        llm_used = False
    else:
        events.append(_trace_event(
            tool_id=tool_id, event_type="llm.plan_started", title="Select analysis mode",
            detail="LLM choosing statistical mode from prompt", data={"preview": prompt_text[:80]},
        ))
        mode, method = _select_analysis_mode(prompt_text)
        llm_used = True
    events.append(_trace_event(
        tool_id=tool_id, event_type="llm.plan_completed", title="Analysis mode selected",
        detail=f"mode={mode}, method={method}",
        data={"mode": mode, "method": method, "llm_used": llm_used},
    ))
    numeric_df = df.select_dtypes(include="number")
    numeric_cols = list(numeric_df.columns)
    result_data: dict[str, Any] = {
        "mode": mode, "method": method, "source": source_label,
        "row_count": row_count, "column_count": col_count,
        "numeric_columns": numeric_cols, "warnings": warnings,
    }
    events.append(_trace_event(
        tool_id=tool_id, event_type="api_call_started", title=f"Compute {mode} statistics",
        detail=f"{len(numeric_cols)} numeric columns", data={"mode": mode},
    ))
    content_lines: list[str] = []

    if mode == "correlation":
        if len(numeric_cols) < 2:
            return _missing_dataset_result(
                warnings + ["Correlation requires at least 2 numeric columns."], tool_id=tool_id
            )
        corr_df = numeric_df.corr(method=method).round(4)  # type: ignore[arg-type]
        pairs: list[dict[str, Any]] = []
        for i, left in enumerate(numeric_cols):
            for right in numeric_cols[i + 1:]:
                try:
                    score = float(corr_df.loc[left, right])
                except Exception:
                    continue
                pairs.append({"left": left, "right": right, "r": round(score, 4), "abs_r": round(abs(score), 4)})
        pairs.sort(key=lambda x: x["abs_r"], reverse=True)
        heatmap_plot = build_heatmap_payload(df=df, title=f"Correlation Matrix ({method.title()})")
        result_data.update({"correlation_pairs": pairs[:40], "heatmap_plot": heatmap_plot})
        content_lines = [
            f"### Correlation Matrix ({method.title()})",
            f"- Source: {source_label or 'payload'}, rows={row_count}",
            "", "| Column A | Column B | r |", "|---|---|---|",
            *[f"| {p['left']} | {p['right']} | {p['r']:+.4f} |" for p in pairs[:20]],
        ]

    elif mode == "distribution":
        try:
            from scipy import stats as scipy_stats  # type: ignore
            has_scipy = True
        except Exception:
            has_scipy = False
            warnings.append("scipy not installed — Shapiro-Wilk tests skipped.")
        tests: list[dict[str, Any]] = []
        for col in numeric_cols[:20]:
            series = numeric_df[col].dropna()
            if series.empty:
                continue
            entry: dict[str, Any] = {
                "column": col, "n": int(len(series)),
                "mean": round(float(series.mean()), 4),
                "std": round(float(series.std()), 4),
                "skew": round(float(series.skew()), 4),
                "kurtosis": round(float(series.kurtosis()), 4),
            }
            if has_scipy and len(series) >= 3:
                stat, p = scipy_stats.shapiro(series.head(5000))
                entry["shapiro_w"] = round(float(stat), 6)
                entry["shapiro_p"] = round(float(p), 6)
                entry["normal"] = bool(p > 0.05)
            tests.append(entry)
        result_data["distribution_tests"] = tests
        if has_scipy:
            header = "| Column | N | Mean | Std | Skew | Kurtosis | Shapiro-p | Normal? |"
            sep = "|---|---|---|---|---|---|---|---|"
            rows_md = [
                f"| {t['column']} | {t['n']} | {t['mean']} | {t['std']} | {t['skew']} | {t['kurtosis']}"
                f" | {t.get('shapiro_p', 'n/a')} | {'Yes' if t.get('normal') else 'No'} |"
                for t in tests[:20]
            ]
        else:
            header = "| Column | N | Mean | Std | Skew | Kurtosis |"
            sep = "|---|---|---|---|---|---|"
            rows_md = [
                f"| {t['column']} | {t['n']} | {t['mean']} | {t['std']} | {t['skew']} | {t['kurtosis']} |"
                for t in tests[:20]
            ]
        content_lines = [
            "### Distribution Tests", f"- Source: {source_label or 'payload'}, rows={row_count}",
            "", header, sep, *rows_md,
        ]

    else:  # descriptive
        stats: list[dict[str, Any]] = []
        for col in numeric_cols[:30]:
            series = numeric_df[col].dropna()
            if series.empty:
                continue
            stats.append({
                "column": col, "count": int(len(series)),
                "mean": round(float(series.mean()), 4), "median": round(float(series.median()), 4),
                "std": round(float(series.std()), 4), "min": round(float(series.min()), 4),
                "max": round(float(series.max()), 4), "skew": round(float(series.skew()), 4),
                "kurtosis": round(float(series.kurtosis()), 4),
            })
        result_data["descriptive_stats"] = stats
        content_lines = [
            "### Descriptive Statistics", f"- Source: {source_label or 'payload'}, rows={row_count}",
            "", "| Column | Count | Mean | Median | Std | Min | Max | Skew |",
            "|---|---|---|---|---|---|---|---|",
            *[
                f"| {s['column']} | {s['count']} | {s['mean']} | {s['median']}"
                f" | {s['std']} | {s['min']} | {s['max']} | {s['skew']} |"
                for s in stats[:20]
            ],
        ]

    if warnings:
        content_lines.extend(["", "### Notes", *[f"- {w}" for w in warnings[:6]]])
    events.append(_trace_event(
        tool_id=tool_id, event_type="api_call_completed", title=f"{mode.title()} statistics complete",
        detail=f"rows={row_count}, numeric_cols={len(numeric_cols)}", data={"mode": mode},
    ))
    context.settings["__latest_stats"] = {"mode": mode, "method": method, "row_count": row_count}
    return ToolExecutionResult(
        summary=f"Computed {mode} statistics for {row_count} rows, {len(numeric_cols)} numeric columns.",
        content="\n".join(content_lines),
        data=result_data,
        sources=[source_ref] if source_ref else [],
        next_steps=[
            "Use `data.science.visualize` with chart_type=heatmap for a visual correlation matrix.",
            "Use `data.science.feature_importance` to rank predictive features.",
        ],
        events=events + [
            _trace_event(
                tool_id=tool_id, event_type="tool_progress",
                title="Statistical analysis ready",
                detail=f"{mode} analysis complete",
                data={"mode": mode, "row_count": row_count},
            )
        ],
    )


__all__ = ["execute_data_science_stats"]
