from __future__ import annotations

from typing import Any
import json

from api.services.agent.llm_runtime import call_json_response
from api.services.agent.tools.base import ToolExecutionResult, ToolTraceEvent

from .shared import (
    SUPPORTED_CHART_TYPES,
    _serialize_cell,
    _trace_event,
)


def _dataset_profile_for_llm(df: Any) -> dict[str, Any]:
    row_count = int(len(df))
    columns: list[dict[str, Any]] = []
    for name in list(df.columns)[:40]:
        series = df[name]
        missing = int(series.isna().sum())
        columns.append(
            {
                "name": str(name),
                "dtype": str(series.dtype),
                "missing": missing,
                "missing_pct": round((missing / row_count * 100.0) if row_count else 0.0, 2),
                "unique": int(series.nunique(dropna=True)),
            }
        )
    sample_rows: list[dict[str, Any]] = []
    for _, row in df.head(12).iterrows():
        payload: dict[str, Any] = {}
        for key in list(df.columns)[:18]:
            payload[str(key)] = _serialize_cell(row.get(key))
        sample_rows.append(payload)
    duplicate_rows = int(df.duplicated().sum()) if len(df.columns) else 0
    return {
        "row_count": row_count,
        "column_count": int(len(df.columns)),
        "duplicate_rows": duplicate_rows,
        "columns": columns,
        "sample_rows": sample_rows,
    }


def _normalize_llm_cleaning_steps(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    output: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        operation = str(item.get("operation") or "").strip().lower()
        if operation not in {
            "drop_duplicates",
            "drop_rows_with_missing",
            "coerce_numeric",
            "clip_outliers",
        }:
            continue
        columns = [
            str(value).strip()
            for value in (item.get("columns") if isinstance(item.get("columns"), list) else [])
            if str(value).strip()
        ]
        normalized = {
            "operation": operation,
            "columns": columns,
            "reason": " ".join(str(item.get("reason") or "").split()).strip()[:260],
        }
        if operation == "clip_outliers":
            try:
                lower_q = float(item.get("lower_quantile"))
            except Exception:
                lower_q = 0.01
            try:
                upper_q = float(item.get("upper_quantile"))
            except Exception:
                upper_q = 0.99
            lower_q = max(0.0, min(0.49, lower_q))
            upper_q = max(0.51, min(1.0, upper_q))
            normalized["lower_quantile"] = lower_q
            normalized["upper_quantile"] = upper_q
        output.append(normalized)
        if len(output) >= 10:
            break
    return output


def _fallback_cleaning_steps(
    *,
    profile: dict[str, Any],
    required_numeric: list[str],
    required_columns: list[str],
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if int(profile.get("duplicate_rows") or 0) > 0:
        steps.append(
            {
                "operation": "drop_duplicates",
                "columns": [],
                "reason": "Duplicate rows detected.",
            }
        )
    if required_numeric:
        steps.append(
            {
                "operation": "coerce_numeric",
                "columns": required_numeric,
                "reason": "Required numeric columns for chart rendering.",
            }
        )
    if required_columns:
        steps.append(
            {
                "operation": "drop_rows_with_missing",
                "columns": required_columns,
                "reason": "Remove rows missing required chart columns.",
            }
        )
    return steps


def _is_numeric_dtype(pd: Any, series: Any) -> bool:
    try:
        return bool(pd.api.types.is_numeric_dtype(series))
    except Exception:
        return False


def _apply_cleaning_steps(
    *,
    pd: Any,
    df: Any,
    steps: list[dict[str, Any]],
) -> tuple[Any, list[dict[str, Any]], list[str]]:
    working = df.copy()
    applied: list[dict[str, Any]] = []
    warnings: list[str] = []
    for step in steps:
        operation = str(step.get("operation") or "").strip().lower()
        columns = [
            str(name).strip()
            for name in (step.get("columns") if isinstance(step.get("columns"), list) else [])
            if str(name).strip()
        ]
        existing_columns = [name for name in columns if name in working.columns]
        before_rows = int(len(working))
        affected_rows = 0
        affected_cols = 0
        try:
            if operation == "drop_duplicates":
                subset = existing_columns or None
                working = working.drop_duplicates(subset=subset)
                affected_rows = max(0, before_rows - int(len(working)))
            elif operation == "drop_rows_with_missing":
                subset = existing_columns or None
                if subset is None:
                    continue
                working = working.dropna(subset=subset)
                affected_rows = max(0, before_rows - int(len(working)))
            elif operation == "coerce_numeric":
                targets = existing_columns or []
                if not targets:
                    continue
                affected_cols = len(targets)
                for column in targets:
                    working[column] = pd.to_numeric(working[column], errors="coerce")
            elif operation == "clip_outliers":
                targets = [
                    column
                    for column in (existing_columns or list(working.columns))
                    if _is_numeric_dtype(pd, working[column])
                ]
                if not targets:
                    continue
                lower_q = float(step.get("lower_quantile") or 0.01)
                upper_q = float(step.get("upper_quantile") or 0.99)
                lower_q = max(0.0, min(0.49, lower_q))
                upper_q = max(0.51, min(1.0, upper_q))
                affected_cols = len(targets)
                for column in targets:
                    series = working[column].dropna()
                    if series.empty:
                        continue
                    lower = float(series.quantile(lower_q))
                    upper = float(series.quantile(upper_q))
                    working[column] = working[column].clip(lower=lower, upper=upper)
            else:
                continue
        except Exception as exc:
            warnings.append(f"Cleaning step `{operation}` failed: {str(exc)}")
            continue

        applied.append(
            {
                "operation": operation,
                "columns": existing_columns,
                "rows_before": before_rows,
                "rows_after": int(len(working)),
                "rows_changed": affected_rows,
                "columns_changed": affected_cols,
                "reason": str(step.get("reason") or "").strip(),
            }
        )
    return working, applied, warnings


def _resolve_chart_requirements(
    *,
    pd: Any,
    df: Any,
    chart_type: str,
    x_col: str,
    y_col: str,
) -> tuple[str, str, str, list[str], list[str], list[str]]:
    requested_chart = str(chart_type or "").strip().lower() or "histogram"
    errors: list[str] = []
    warnings: list[str] = []
    available_columns = [str(column) for column in list(df.columns)]
    numeric_columns = [str(column) for column in available_columns if _is_numeric_dtype(pd, df[column])]
    non_numeric_columns = [column for column in available_columns if column not in numeric_columns]

    if requested_chart not in SUPPORTED_CHART_TYPES:
        errors.append(
            f"Unsupported chart_type `{requested_chart}`. Supported values: {', '.join(sorted(SUPPORTED_CHART_TYPES))}."
        )
        requested_chart = "histogram"

    x_name = str(x_col or "").strip()
    y_name = str(y_col or "").strip()
    if x_name and x_name not in df.columns:
        errors.append(f"Column `{x_name}` was not found.")
    if y_name and y_name not in df.columns:
        errors.append(f"Column `{y_name}` was not found.")

    if requested_chart == "scatter":
        if not x_name:
            x_name = numeric_columns[0] if len(numeric_columns) >= 1 else ""
        if not y_name:
            y_name = numeric_columns[1] if len(numeric_columns) >= 2 else ""
        if not x_name or not y_name:
            errors.append("Scatter requires two numeric columns (`x` and `y`).")
        for column in (x_name, y_name):
            if column and column in df.columns and not _is_numeric_dtype(pd, df[column]):
                errors.append(f"Scatter requires numeric column `{column}`.")
    elif requested_chart == "line":
        if not y_name:
            y_name = numeric_columns[0] if numeric_columns else ""
        if not y_name:
            errors.append("Line chart requires one numeric `y` column.")
        elif not _is_numeric_dtype(pd, df[y_name]):
            errors.append(f"Line chart requires numeric `y` column, got `{y_name}`.")
        if not x_name and non_numeric_columns:
            x_name = non_numeric_columns[0]
        if not x_name:
            warnings.append("No `x` column provided; chart will use row index.")
    elif requested_chart == "bar":
        if not x_name:
            x_name = non_numeric_columns[0] if non_numeric_columns else (available_columns[0] if available_columns else "")
        if not y_name:
            y_name = numeric_columns[0] if numeric_columns else ""
        if not x_name or not y_name:
            errors.append("Bar chart requires category-like `x` and numeric `y` columns.")
        elif not _is_numeric_dtype(pd, df[y_name]):
            errors.append(f"Bar chart requires numeric `y` column, got `{y_name}`.")
    else:
        requested_chart = "histogram"
        if not x_name:
            x_name = numeric_columns[0] if numeric_columns else ""
        if not x_name:
            errors.append("Histogram requires one numeric `x` column.")
        elif not _is_numeric_dtype(pd, df[x_name]):
            errors.append(f"Histogram requires numeric `x` column, got `{x_name}`.")

    return requested_chart, x_name, y_name, errors, warnings, available_columns


def _plan_dataset_cleaning_with_llm(
    *,
    df: Any,
    workflow: str,
    required_numeric: list[str],
    required_columns: list[str],
    context_payload: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]], bool]:
    profile = _dataset_profile_for_llm(df)
    payload = {
        "workflow": str(workflow or "generic").strip().lower() or "generic",
        "required_numeric_columns": required_numeric,
        "required_columns": required_columns,
        "dataset_profile": profile,
    }
    if isinstance(context_payload, dict):
        payload["context"] = context_payload
    response = call_json_response(
        system_prompt=(
            "You are a data-cleaning planner for analytics workflows.\n"
            "Return strict JSON only."
        ),
        user_prompt=(
            "Create a dataset cleaning plan.\n"
            "Allowed operations only:\n"
            "- drop_duplicates\n"
            "- drop_rows_with_missing\n"
            "- coerce_numeric\n"
            "- clip_outliers\n"
            "Return JSON schema:\n"
            "{"
            '"issues": ["..."],'
            '"cleaning_steps": ['
            '{"operation":"drop_duplicates","columns":[],"reason":"..."},'
            '{"operation":"drop_rows_with_missing","columns":["col"],"reason":"..."},'
            '{"operation":"coerce_numeric","columns":["col"],"reason":"..."},'
            '{"operation":"clip_outliers","columns":["col"],"lower_quantile":0.01,"upper_quantile":0.99,"reason":"..."}'
            "],"
            '"notes": ["..."]'
            "}\n"
            f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
        ),
        temperature=0.0,
        timeout_seconds=10,
        max_tokens=420,
    )
    if not isinstance(response, dict):
        return [], _fallback_cleaning_steps(
            profile=profile,
            required_numeric=required_numeric,
            required_columns=required_columns,
        ), False

    issues = [
        " ".join(str(item).split()).strip()[:220]
        for item in (response.get("issues") if isinstance(response.get("issues"), list) else [])
        if " ".join(str(item).split()).strip()
    ][:10]
    llm_steps = _normalize_llm_cleaning_steps(response.get("cleaning_steps"))
    if not llm_steps:
        llm_steps = _fallback_cleaning_steps(
            profile=profile,
            required_numeric=required_numeric,
            required_columns=required_columns,
        )
    return issues, llm_steps, True


def _plan_cleaning_with_llm(
    *,
    df: Any,
    chart_type: str,
    x_col: str,
    y_col: str,
    required_numeric: list[str],
    required_columns: list[str],
) -> tuple[list[str], list[dict[str, Any]], bool]:
    return _plan_dataset_cleaning_with_llm(
        df=df,
        workflow="visualization",
        required_numeric=required_numeric,
        required_columns=required_columns,
        context_payload={
            "chart_type": chart_type,
            "x": x_col,
            "y": y_col,
        },
    )


def _missing_dataset_result(
    messages: list[str],
    *,
    tool_id: str = "",
    events_prefix: list[ToolTraceEvent] | None = None,
) -> ToolExecutionResult:
    detail = "\n".join(f"- {item}" for item in messages if item) or "- Dataset missing."
    events = list(events_prefix or [])
    events.append(
        _trace_event(
            tool_id=tool_id or "data.science",
            event_type="tool_failed",
            title="Dataset unavailable",
            detail="No readable tabular data was resolved",
            data={"remediation": "Provide rows/csv_text/indexed tabular files and retry."},
        )
    )
    return ToolExecutionResult(
        summary="Dataset could not be loaded.",
        content=(
            "Unable to start data-science operation.\n"
            f"{detail}\n\n"
            "Use one of:\n"
            "- `rows` (list of objects)\n"
            "- `csv_text` (CSV string)\n"
            "- selected indexed files"
        ),
        data={},
        sources=[],
        next_steps=[
            "Provide dataset input and rerun.",
            "For model training, include `target` in params.",
        ],
        events=events,
    )
