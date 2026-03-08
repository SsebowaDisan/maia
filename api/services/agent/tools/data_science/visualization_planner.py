from __future__ import annotations

from typing import Any
import json

from api.services.agent.llm_runtime import call_json_response

from .quality import _dataset_profile_for_llm
from .shared import SUPPORTED_CHART_TYPES


def _normalize_column_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        values = [item.strip() for item in raw.split(",")]
        return [item for item in values if item]
    if isinstance(raw, list):
        values = [" ".join(str(item).split()).strip() for item in raw]
        return [item for item in values if item]
    return []


def _is_probably_numeric_dtype(dtype_name: str) -> bool:
    text = str(dtype_name or "").strip().lower()
    return any(token in text for token in ("int", "float", "double", "decimal", "number"))


def _fallback_visualization_plan(
    *,
    profile: dict[str, Any],
    requested_chart_type: str,
    requested_x: str,
    requested_y: str,
    requested_y_series: list[str],
) -> dict[str, Any]:
    available_columns = [
        str(item.get("name") or "").strip()
        for item in (profile.get("columns") if isinstance(profile.get("columns"), list) else [])
        if str(item.get("name") or "").strip()
    ]
    numeric_columns = [
        str(item.get("name") or "").strip()
        for item in (profile.get("columns") if isinstance(profile.get("columns"), list) else [])
        if str(item.get("name") or "").strip()
        and _is_probably_numeric_dtype(item.get("dtype"))
    ]
    non_numeric_columns = [item for item in available_columns if item not in numeric_columns]
    chart_type = str(requested_chart_type or "").strip().lower()
    if chart_type not in SUPPORTED_CHART_TYPES:
        if len(numeric_columns) >= 2 and non_numeric_columns:
            chart_type = "line"
        elif len(numeric_columns) >= 2:
            chart_type = "scatter"
        elif numeric_columns:
            chart_type = "histogram"
        else:
            chart_type = "bar"
    x_name = str(requested_x or "").strip()
    y_name = str(requested_y or "").strip()
    if chart_type == "scatter":
        if not x_name:
            x_name = numeric_columns[0] if len(numeric_columns) >= 1 else ""
        if not y_name:
            y_name = numeric_columns[1] if len(numeric_columns) >= 2 else ""
    elif chart_type == "line":
        if not x_name:
            x_name = non_numeric_columns[0] if non_numeric_columns else ""
        if not y_name:
            y_name = numeric_columns[0] if numeric_columns else ""
    elif chart_type == "bar":
        if not x_name:
            x_name = non_numeric_columns[0] if non_numeric_columns else (available_columns[0] if available_columns else "")
        if not y_name:
            y_name = numeric_columns[0] if numeric_columns else ""
    elif chart_type == "heatmap":
        pass  # uses all numeric columns internally
    elif chart_type == "box":
        if not x_name:
            x_name = non_numeric_columns[0] if non_numeric_columns else ""
        if not y_name:
            y_name = numeric_columns[0] if numeric_columns else ""
    elif chart_type == "pie":
        if not x_name:
            x_name = non_numeric_columns[0] if non_numeric_columns else (available_columns[0] if available_columns else "")
        if not y_name:
            y_name = numeric_columns[0] if numeric_columns else ""
    elif chart_type == "area":
        if not x_name:
            x_name = non_numeric_columns[0] if non_numeric_columns else ""
        if not y_name:
            y_name = numeric_columns[0] if numeric_columns else ""
    else:
        if not x_name:
            x_name = numeric_columns[0] if numeric_columns else ""
    y_series = [name for name in requested_y_series if name in numeric_columns]
    if y_name and y_name in numeric_columns and y_name not in y_series:
        y_series.insert(0, y_name)
    if chart_type in {"line", "bar"} and not y_series and numeric_columns:
        y_series = numeric_columns[:2]
        if y_name and y_name in y_series:
            y_series = [y_name, *[name for name in y_series if name != y_name]]
    return {
        "chart_type": chart_type,
        "x": x_name,
        "y": y_name,
        "y_series": y_series[:4],
        "title": "",
        "reasoning": "fallback",
    }


def _normalize_visualization_plan(
    *,
    raw: Any,
    profile: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return fallback
    available_columns = {
        str(item.get("name") or "").strip()
        for item in (profile.get("columns") if isinstance(profile.get("columns"), list) else [])
        if str(item.get("name") or "").strip()
    }
    chart_type = str(raw.get("chart_type") or fallback.get("chart_type") or "").strip().lower()
    if chart_type not in SUPPORTED_CHART_TYPES:
        chart_type = str(fallback.get("chart_type") or "histogram")

    x_name = str(raw.get("x") or fallback.get("x") or "").strip()
    y_name = str(raw.get("y") or fallback.get("y") or "").strip()
    if x_name and x_name not in available_columns:
        x_name = str(fallback.get("x") or "")
    if y_name and y_name not in available_columns:
        y_name = str(fallback.get("y") or "")

    y_series_raw = _normalize_column_list(raw.get("y_series"))
    y_series: list[str] = []
    for name in [*y_series_raw, *_normalize_column_list(fallback.get("y_series"))]:
        if not name or name not in available_columns or name in y_series:
            continue
        y_series.append(name)
        if len(y_series) >= 4:
            break
    if y_name and y_name not in y_series:
        y_series.insert(0, y_name)
    title = " ".join(str(raw.get("title") or "").split()).strip()[:180]
    reasoning = " ".join(str(raw.get("reasoning") or "").split()).strip()[:320]
    return {
        "chart_type": chart_type,
        "x": x_name,
        "y": y_name,
        "y_series": y_series[:4],
        "title": title,
        "reasoning": reasoning,
    }


def plan_visualization_with_llm(
    *,
    df: Any,
    prompt: str,
    requested_chart_type: str,
    requested_x: str,
    requested_y: str,
    requested_y_series: list[str],
) -> tuple[dict[str, Any], bool]:
    profile = _dataset_profile_for_llm(df)
    fallback = _fallback_visualization_plan(
        profile=profile,
        requested_chart_type=requested_chart_type,
        requested_x=requested_x,
        requested_y=requested_y,
        requested_y_series=requested_y_series,
    )
    response = call_json_response(
        system_prompt=(
            "You are a data-visualization planner.\n"
            "Choose chart_type and columns that best explain the dataset intent.\n"
            "Prefer: heatmap/scatter for correlation or relationship queries; "
            "box for distribution or outlier queries; pie for share or proportion queries; "
            "area for cumulative or stacked trend queries; line/bar for trend comparisons; "
            "histogram for single-variable distribution.\n"
            "Return strict JSON only."
        ),
        user_prompt=(
            "Create a chart plan for this dataset.\n"
            "Allowed chart_type values: scatter, line, bar, histogram, heatmap, box, pie, area.\n"
            "Prefer line/bar for trend comparisons, scatter for numeric relationships, "
            "histogram for single-variable distribution, heatmap for correlation matrices, "
            "box for quartile/outlier analysis, pie for category proportions, "
            "area for filled/cumulative time-series.\n"
            "Return JSON schema:\n"
            "{"
            '"chart_type":"line",'
            '"x":"column_name_or_empty",'
            '"y":"column_name_or_empty",'
            '"y_series":["col_a","col_b"],'
            '"title":"chart title",'
            '"reasoning":"short explanation"'
            "}\n"
            "Do not return markdown.\n"
            f"User request:\n{prompt}\n\n"
            f"Requested params:\n{json.dumps({'chart_type': requested_chart_type, 'x': requested_x, 'y': requested_y, 'y_series': requested_y_series}, ensure_ascii=True)}\n\n"
            f"Dataset profile:\n{json.dumps(profile, ensure_ascii=True)}"
        ),
        temperature=0.0,
        timeout_seconds=10,
        max_tokens=340,
    )
    if not isinstance(response, dict):
        return fallback, False
    normalized = _normalize_visualization_plan(
        raw=response,
        profile=profile,
        fallback=fallback,
    )
    return normalized, True


__all__ = ["plan_visualization_with_llm"]
