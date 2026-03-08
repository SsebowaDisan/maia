from __future__ import annotations

from typing import Any

from api.services.agent.llm_runtime import call_json_response
from api.services.agent.tools.base import ToolExecutionContext, ToolExecutionResult

from .plot_payload import build_interactive_plot_payload
from .quality import _apply_cleaning_steps, _missing_dataset_result, _plan_dataset_cleaning_with_llm
from .shared import _as_float, _as_int, _import_pandas, _limit_rows, _load_dataframe, _trace_event


def _select_cluster_params(prompt: str) -> dict[str, Any]:
    response = call_json_response(
        system_prompt="You are a clustering algorithm planner. Return strict JSON only.",
        user_prompt=(
            "Choose a clustering algorithm and parameters for this request.\n"
            "Algorithms: kmeans, dbscan.\n"
            'Return JSON: {"algorithm": "kmeans|dbscan", "k": 3, "eps": 0.5, "min_samples": 5}\n'
            "Use kmeans unless the user mentions density/noise/dbscan. "
            "k must be 2-8 for kmeans. eps is float for dbscan, min_samples is int.\n"
            f"Request: {prompt}"
        ),
        temperature=0.0,
        timeout_seconds=10,
        max_tokens=250,
    )
    if not isinstance(response, dict):
        return {"algorithm": "kmeans", "k": 3, "eps": 0.5, "min_samples": 5}
    algo = str(response.get("algorithm") or "kmeans").strip().lower()
    if algo not in {"kmeans", "dbscan"}:
        algo = "kmeans"
    k = max(2, min(int(_as_int(response.get("k"), 3)), 8))
    eps = max(0.01, float(_as_float(response.get("eps"), 0.5)))
    min_samples = max(2, int(_as_int(response.get("min_samples"), 5)))
    return {"algorithm": algo, "k": k, "eps": eps, "min_samples": min_samples}


def _auto_k_elbow(X: Any, k_range: range) -> int:
    """Pick k using inertia elbow heuristic."""
    try:
        from sklearn.cluster import KMeans as _KMeans  # type: ignore
        inertias = []
        for k in k_range:
            km = _KMeans(n_clusters=k, random_state=42, n_init=5)
            km.fit(X)
            inertias.append(float(km.inertia_))
        if len(inertias) < 2:
            return k_range[0]
        diffs = [inertias[i] - inertias[i + 1] for i in range(len(inertias) - 1)]
        best_idx = max(range(len(diffs)), key=lambda i: diffs[i])
        return k_range[best_idx + 1]
    except Exception:
        return k_range[0]


def execute_data_science_cluster(
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
    max_rows = max(200, min(_as_int(params.get("max_rows"), 30000), 150000))
    df, truncated = _limit_rows(df, max_rows=max_rows)
    row_count_before = int(len(df))
    col_count = int(len(df.columns))
    events.append(_trace_event(
        tool_id=tool_id, event_type="prepare_request", title="Prepare dataset",
        detail=f"Loaded {row_count_before} rows and {col_count} columns",
        data={"row_count": row_count_before, "column_count": col_count},
    ))
    prompt_text = " ".join(str(prompt or "").split()).strip()
    algo_param = str(params.get("algorithm") or "").strip().lower()
    if algo_param in {"kmeans", "dbscan"}:
        cluster_params = {
            "algorithm": algo_param,
            "k": max(2, min(_as_int(params.get("k"), 3), 8)),
            "eps": max(0.01, _as_float(params.get("eps"), 0.5)),
            "min_samples": max(2, _as_int(params.get("min_samples"), 5)),
        }
        llm_used = False
    else:
        events.append(_trace_event(
            tool_id=tool_id, event_type="llm.plan_started",
            title="Select clustering algorithm", detail="LLM choosing algorithm from prompt",
            data={"preview": prompt_text[:80]},
        ))
        cluster_params = _select_cluster_params(prompt_text)
        llm_used = True
    algorithm: str = cluster_params["algorithm"]
    events.append(_trace_event(
        tool_id=tool_id, event_type="llm.plan_completed", title="Clustering plan selected",
        detail=f"algorithm={algorithm}", data={**cluster_params, "llm_used": llm_used},
    ))
    numeric_df = df.select_dtypes(include="number")
    numeric_cols = list(numeric_df.columns)
    feature_cols_raw = params.get("features")
    if isinstance(feature_cols_raw, list) and feature_cols_raw:
        feature_cols = [str(c).strip() for c in feature_cols_raw if str(c).strip() in numeric_cols]
    else:
        feature_cols = numeric_cols[:20]
    if len(feature_cols) < 2:
        return _missing_dataset_result(
            warnings + ["Clustering requires at least 2 numeric feature columns."], tool_id=tool_id
        )
    events.append(_trace_event(
        tool_id=tool_id, event_type="llm.dataset_cleaning_started",
        title="Analyze dataset quality", detail="LLM planning data cleaning",
        data={"algorithm": algorithm},
    ))
    quality_issues, cleaning_plan, llm_cleaning_used = _plan_dataset_cleaning_with_llm(
        df=df, workflow="clustering",
        required_numeric=feature_cols[:10], required_columns=feature_cols[:10],
        context_payload={"algorithm": algorithm, "source": source_label or "payload"},
    )
    df, cleaning_applied, cleaning_warnings = _apply_cleaning_steps(pd=pd, df=df, steps=cleaning_plan)
    warnings.extend(cleaning_warnings)
    events.append(_trace_event(
        tool_id=tool_id, event_type="llm.dataset_cleaning_completed",
        title="Cleaning complete", detail=f"Issues: {len(quality_issues)}",
        data={"issues_count": len(quality_issues)},
    ))
    work = df[feature_cols].dropna()
    if len(work) < 10:
        return _missing_dataset_result(
            warnings + [f"Too few rows after cleaning ({len(work)}) for clustering."], tool_id=tool_id
        )
    try:
        from sklearn.preprocessing import StandardScaler  # type: ignore
        scaler = StandardScaler()
        X = scaler.fit_transform(work.values)
    except Exception:
        X = work.values
    events.append(_trace_event(
        tool_id=tool_id, event_type="api_call_started", title=f"Run {algorithm.upper()} clustering",
        detail=f"rows={len(work)}, features={len(feature_cols)}",
        data={"algorithm": algorithm, "n_rows": len(work), "n_features": len(feature_cols)},
    ))
    labels: list[int] = []
    algo_meta: dict[str, Any] = {}
    try:
        if algorithm == "dbscan":
            from sklearn.cluster import DBSCAN  # type: ignore
            from sklearn.neighbors import NearestNeighbors  # type: ignore
            eps = float(cluster_params["eps"])
            if eps == 0.5:
                nbrs = NearestNeighbors(n_neighbors=min(5, len(X))).fit(X)
                distances, _ = nbrs.kneighbors(X)
                eps = float(sorted(distances[:, -1])[int(len(X) * 0.9)])
                eps = max(0.01, round(eps, 4))
            min_samples = int(cluster_params["min_samples"])
            model = DBSCAN(eps=eps, min_samples=min_samples)
            labels = model.fit_predict(X).tolist()
            n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
            n_noise = labels.count(-1)
            algo_meta = {"eps": eps, "min_samples": min_samples, "n_clusters": n_clusters, "n_noise": n_noise}
        else:
            from sklearn.cluster import KMeans  # type: ignore
            k = int(cluster_params["k"])
            if str(params.get("auto_k", "")).lower() in {"true", "1", "yes"}:
                k = _auto_k_elbow(X, range(2, 9))
            model = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = model.fit_predict(X).tolist()
            n_clusters = k
            algo_meta = {"k": k, "inertia": round(float(model.inertia_), 4)}
    except Exception as exc:
        return _missing_dataset_result(
            warnings + [f"Clustering failed: {str(exc)}"], tool_id=tool_id
        )
    events.append(_trace_event(
        tool_id=tool_id, event_type="api_call_completed", title="Clustering complete",
        detail=f"clusters={algo_meta.get('n_clusters', algo_meta.get('k'))}",
        data=algo_meta,
    ))
    work = work.copy()
    work["__cluster__"] = labels
    counts: dict[str, int] = {}
    for lbl in labels:
        key = "noise" if lbl == -1 else f"cluster_{lbl}"
        counts[key] = counts.get(key, 0) + 1
    centroids: list[dict[str, Any]] = []
    for lbl in sorted(set(labels)):
        if lbl == -1:
            continue
        sub = work[work["__cluster__"] == lbl][feature_cols]
        centroid = {col: round(float(sub[col].mean()), 4) for col in feature_cols[:10]}
        centroid["cluster"] = lbl
        centroid["count"] = int((work["__cluster__"] == lbl).sum())
        centroids.append(centroid)
    scatter_plot: dict[str, Any] = {}
    if len(feature_cols) >= 2:
        scatter_plot = build_interactive_plot_payload(
            df=work.rename(columns={"__cluster__": "cluster"}),
            chart_type="scatter", title=f"Cluster Scatter — {algorithm.upper()}",
            x_col=feature_cols[0], y_col=feature_cols[1],
            row_count=len(work), series_columns=None, top_n=12, bins=20,
        )
    row_count = int(len(work))
    content_lines = [
        f"### Clustering Results ({algorithm.upper()})",
        f"- Source: {source_label or 'payload'}, rows={row_count}",
        f"- Features: {', '.join(feature_cols[:8])}",
        *[f"- {k}: {v}" for k, v in algo_meta.items()],
        "", "### Cluster Counts",
        *[f"- {k}: {v}" for k, v in sorted(counts.items())],
        "", "### Centroids (first 10 features)",
        "| Cluster | Count | " + " | ".join(feature_cols[:6]) + " |",
        "|---|---|" + "|---|" * min(len(feature_cols), 6),
        *[
            f"| {c['cluster']} | {c['count']} | " + " | ".join(str(c.get(col, "")) for col in feature_cols[:6]) + " |"
            for c in centroids
        ],
    ]
    if warnings:
        content_lines.extend(["", "### Notes", *[f"- {w}" for w in warnings[:6]]])
    context.settings["__latest_clusters"] = {
        "algorithm": algorithm, "n_clusters": algo_meta.get("n_clusters", algo_meta.get("k")),
        "counts": counts, "row_count": row_count,
    }
    return ToolExecutionResult(
        summary=f"{algorithm.upper()} clustering: {algo_meta.get('n_clusters', algo_meta.get('k'))} clusters from {row_count} rows.",
        content="\n".join(content_lines),
        data={
            "algorithm": algorithm, "algo_meta": algo_meta, "counts": counts,
            "centroids": centroids, "feature_cols": feature_cols,
            "scatter_plot": scatter_plot, "row_count": row_count,
            "quality_issues": quality_issues, "cleaning_applied": cleaning_applied,
            "warnings": warnings, "truncated": truncated,
        },
        sources=[source_ref] if source_ref else [],
        next_steps=[
            "Use `data.science.visualize` chart_type=scatter with cluster column to color segments.",
            "Use `data.science.stats` mode=descriptive to profile each cluster.",
        ],
        events=events + [
            _trace_event(
                tool_id=tool_id, event_type="tool_progress",
                title="Clustering ready",
                detail=f"{algorithm.upper()}: {algo_meta.get('n_clusters', algo_meta.get('k'))} clusters",
                data=algo_meta,
            )
        ],
    )


__all__ = ["execute_data_science_cluster"]
