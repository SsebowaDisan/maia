from __future__ import annotations

from typing import Any

SERIES_COLORS = [
    "#111111",
    "#374151",
    "#4b5563",
    "#6b7280",
    "#9ca3af",
    "#1f2937",
]


def _safe_number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def _normalize_series_columns(
    *,
    chart_type: str,
    y_col: str,
    series_columns: list[str] | None,
) -> list[str]:
    ordered: list[str] = []
    for name in [y_col, *(series_columns or [])]:
        text = str(name or "").strip()
        if not text or text in ordered:
            continue
        ordered.append(text)
    if chart_type in {"line", "bar"}:
        return ordered[:4]
    return ordered[:1]


def _series_specs(series_columns: list[str], *, default_type: str) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    for idx, name in enumerate(series_columns):
        specs.append(
            {
                "key": name,
                "label": name.replace("_", " ").strip().title() or name,
                "type": default_type,
                "color": SERIES_COLORS[idx % len(SERIES_COLORS)],
            }
        )
    return specs


def _string_or_number(value: Any) -> str | float | int:
    numeric = _safe_number(value)
    if numeric is None:
        return str(value)
    if float(numeric).is_integer():
        return int(numeric)
    return float(numeric)


def build_interactive_plot_payload(
    *,
    df: Any,
    chart_type: str,
    title: str,
    x_col: str,
    y_col: str,
    row_count: int,
    series_columns: list[str] | None,
    top_n: int,
    bins: int,
) -> dict[str, Any]:
    normalized_series = _normalize_series_columns(
        chart_type=chart_type,
        y_col=y_col,
        series_columns=series_columns,
    )
    payload: dict[str, Any] = {
        "kind": "chart",
        "library": "recharts",
        "chart_type": chart_type,
        "title": title,
        "x": x_col,
        "y": y_col,
        "row_count": row_count,
        "x_type": "category",
        "series": [],
        "points": [],
        "interactive": {
            "brush": chart_type in {"line", "bar"},
        },
    }

    if chart_type == "scatter":
        y_key = normalized_series[0] if normalized_series else y_col
        if not y_key:
            return payload
        rows = df[[x_col, y_key]].dropna().head(800).to_dict(orient="records")
        points: list[dict[str, Any]] = []
        for item in rows:
            x_num = _safe_number(item.get(x_col))
            y_num = _safe_number(item.get(y_key))
            if x_num is None or y_num is None:
                continue
            points.append({"x": x_num, "y": y_num})
        payload["x_type"] = "numeric"
        payload["series"] = _series_specs([y_key], default_type="scatter")
        payload["points"] = points
        return payload

    if chart_type == "line":
        if not normalized_series:
            return payload
        if x_col and x_col in df.columns:
            subset = [x_col, *normalized_series]
            rows = df[subset].dropna(subset=normalized_series).head(800).to_dict(orient="records")
            points = []
            for item in rows:
                point: dict[str, Any] = {"x": _string_or_number(item.get(x_col))}
                for key in normalized_series:
                    value = _safe_number(item.get(key))
                    if value is not None:
                        point[key] = value
                if len(point) > 1:
                    point["y"] = point.get(normalized_series[0])
                    points.append(point)
            payload["x_type"] = (
                "numeric"
                if all(_safe_number(point.get("x")) is not None for point in points[:120])
                else "category"
            )
            payload["points"] = points
        else:
            rows = df[normalized_series].dropna(subset=normalized_series).head(800)
            points = []
            for idx, row in enumerate(rows.to_dict(orient="records"), start=1):
                point: dict[str, Any] = {"x": idx}
                for key in normalized_series:
                    value = _safe_number(row.get(key))
                    if value is not None:
                        point[key] = value
                if len(point) > 1:
                    point["y"] = point.get(normalized_series[0])
                    points.append(point)
            payload["x"] = x_col or "row_index"
            payload["x_type"] = "numeric"
            payload["points"] = points
        payload["series"] = _series_specs(normalized_series, default_type="line")
        return payload

    if chart_type == "bar":
        if not normalized_series:
            return payload
        if x_col and x_col in df.columns:
            grouped = (
                df[[x_col, *normalized_series]]
                .dropna(subset=[x_col])
                .groupby(x_col)[normalized_series]
                .mean()
                .sort_values(by=normalized_series[0], ascending=False)
                .head(max(3, min(int(top_n or 12), 40)))
            )
            points = []
            for index, row in grouped.iterrows():
                point: dict[str, Any] = {"x": str(index)}
                for key in normalized_series:
                    value = _safe_number(row.get(key))
                    if value is not None:
                        point[key] = value
                if len(point) > 1:
                    point["y"] = point.get(normalized_series[0])
                    points.append(point)
            payload["points"] = points
        else:
            rows = df[normalized_series].dropna(subset=normalized_series).head(max(5, min(int(top_n or 12), 60)))
            points = []
            for idx, row in enumerate(rows.to_dict(orient="records"), start=1):
                point: dict[str, Any] = {"x": str(idx)}
                for key in normalized_series:
                    value = _safe_number(row.get(key))
                    if value is not None:
                        point[key] = value
                if len(point) > 1:
                    point["y"] = point.get(normalized_series[0])
                    points.append(point)
            payload["x"] = x_col or "row_index"
            payload["points"] = points
        payload["series"] = _series_specs(normalized_series, default_type="bar")
        return payload

    # Histogram
    values = [_safe_number(item) for item in df[x_col].dropna().head(2200).tolist()]
    numeric_values = [item for item in values if item is not None]
    if not numeric_values:
        return payload
    min_value = min(numeric_values)
    max_value = max(numeric_values)
    bounded_bins = max(5, min(int(bins or 20), 120))
    if max_value == min_value:
        points = [{"x": f"{round(min_value, 4)}", "count": len(numeric_values), "y": len(numeric_values)}]
    else:
        width = (max_value - min_value) / bounded_bins
        counts = [0 for _ in range(bounded_bins)]
        for item in numeric_values:
            bucket = int((item - min_value) / width)
            bucket = min(bounded_bins - 1, max(0, bucket))
            counts[bucket] += 1
        points = []
        for idx, count in enumerate(counts):
            left = min_value + width * idx
            right = left + width
            points.append(
                {
                    "x": f"{left:.2f}-{right:.2f}",
                    "count": count,
                    "y": count,
                }
            )
    payload["series"] = _series_specs(["count"], default_type="bar")
    payload["x_type"] = "category"
    payload["points"] = points
    payload["y"] = "count"
    return payload


def build_heatmap_payload(*, df: Any, title: str) -> dict[str, Any]:
    numeric_df = df.select_dtypes(include="number")
    labels = list(numeric_df.columns[:20])
    payload: dict[str, Any] = {
        "kind": "chart",
        "library": "recharts",
        "chart_type": "heatmap",
        "title": title,
        "labels": labels,
        "matrix": [],
    }
    if len(labels) < 2:
        return payload
    corr = numeric_df[labels].corr().round(3)
    payload["matrix"] = corr.values.tolist()
    return payload


def build_box_payload(*, df: Any, title: str, x_col: str, y_col: str, top_n: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": "chart",
        "library": "recharts",
        "chart_type": "box",
        "title": title,
        "x": x_col,
        "y": y_col,
        "groups": [],
    }
    if not y_col or y_col not in df.columns:
        return payload
    if x_col and x_col in df.columns:
        top_cats = (
            df[[x_col, y_col]].dropna().groupby(x_col)[y_col]
            .count().sort_values(ascending=False).head(max(3, min(top_n, 20))).index
        )
        groups_iter = df[[x_col, y_col]].dropna().groupby(x_col)[y_col]
        groups_data = [(str(cat), groups_iter.get_group(cat)) for cat in top_cats]
    else:
        groups_data = [("all", df[y_col].dropna())]
    groups = []
    for label, series in groups_data:
        if series.empty:
            continue
        q1 = float(series.quantile(0.25))
        median = float(series.median())
        q3 = float(series.quantile(0.75))
        iqr = q3 - q1
        wl = max(float(series.min()), q1 - 1.5 * iqr)
        wh = min(float(series.max()), q3 + 1.5 * iqr)
        outliers = [round(float(v), 4) for v in series.tolist() if v < wl or v > wh][:40]
        groups.append({
            "x": label, "q1": round(q1, 4), "median": round(median, 4),
            "q3": round(q3, 4), "whisker_low": round(wl, 4), "whisker_high": round(wh, 4),
            "outliers": outliers,
        })
    payload["groups"] = groups
    return payload


def build_pie_payload(*, df: Any, title: str, x_col: str, y_col: str, top_n: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": "chart",
        "library": "recharts",
        "chart_type": "pie",
        "title": title,
        "x": x_col,
        "y": y_col,
        "slices": [],
    }
    if not x_col or x_col not in df.columns or not y_col or y_col not in df.columns:
        return payload
    bounded_n = max(3, min(top_n, 16))
    grouped = df[[x_col, y_col]].dropna().groupby(x_col)[y_col].sum().sort_values(ascending=False)
    total = float(grouped.sum())
    if total == 0:
        return payload
    top = grouped.head(bounded_n)
    slices = [
        {"label": str(lbl), "value": round(float(val), 4), "percent": round(float(val) / total * 100, 2)}
        for lbl, val in top.items()
    ]
    other_sum = float(grouped.iloc[bounded_n:].sum())
    if other_sum > 0:
        slices.append({"label": "Other", "value": round(other_sum, 4), "percent": round(other_sum / total * 100, 2)})
    payload["slices"] = slices
    return payload


def build_area_payload(*, df: Any, title: str, x_col: str, y_col: str, series_columns: list[str] | None) -> dict[str, Any]:
    normalized = _normalize_series_columns(chart_type="line", y_col=y_col, series_columns=series_columns)
    payload: dict[str, Any] = {
        "kind": "chart",
        "library": "recharts",
        "chart_type": "area",
        "title": title,
        "x": x_col,
        "y": y_col,
        "x_type": "category",
        "filled": True,
        "series": _series_specs(normalized, default_type="area"),
        "points": [],
        "interactive": {"brush": True},
    }
    if not normalized:
        return payload
    if x_col and x_col in df.columns:
        subset = [x_col, *normalized]
        rows = df[subset].dropna(subset=normalized).head(800).to_dict(orient="records")
        points: list[dict[str, Any]] = []
        for item in rows:
            point: dict[str, Any] = {"x": _string_or_number(item.get(x_col))}
            for key in normalized:
                value = _safe_number(item.get(key))
                if value is not None:
                    point[key] = value
            if len(point) > 1:
                point["y"] = point.get(normalized[0])
                points.append(point)
        payload["x_type"] = (
            "numeric"
            if all(_safe_number(pt.get("x")) is not None for pt in points[:120])
            else "category"
        )
        payload["points"] = points
    else:
        rows_df = df[normalized].dropna(subset=normalized).head(800)
        points = []
        for idx, row in enumerate(rows_df.to_dict(orient="records"), start=1):
            point = {"x": idx}
            for key in normalized:
                value = _safe_number(row.get(key))
                if value is not None:
                    point[key] = value
            if len(point) > 1:
                point["y"] = point.get(normalized[0])
                points.append(point)
        payload["x"] = x_col or "row_index"
        payload["x_type"] = "numeric"
        payload["points"] = points
    return payload
