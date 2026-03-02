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
