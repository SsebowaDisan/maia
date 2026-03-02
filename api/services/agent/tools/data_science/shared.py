from __future__ import annotations

from pathlib import Path
from typing import Any
import io
import json

from api.context import get_context
from api.services.agent.models import AgentSource
from api.services.agent.tools.base import ToolExecutionContext, ToolTraceEvent
from api.services.upload_service import resolve_indexed_file_path

SCENE_SURFACE_SYSTEM = "system"
SUPPORTED_CHART_TYPES = {"scatter", "line", "bar", "histogram"}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_file_ids(raw: Any) -> list[str]:
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, list):
        cleaned = [str(item).strip() for item in raw if str(item).strip()]
        return list(dict.fromkeys(cleaned))
    return []


def _selected_file_ids(context: ToolExecutionContext, params: dict[str, Any]) -> list[str]:
    file_ids = _normalize_file_ids(params.get("file_ids"))
    if not file_ids:
        file_ids = _normalize_file_ids(params.get("file_id"))
    if not file_ids:
        file_ids = _normalize_file_ids(context.settings.get("__selected_file_ids"))
    return file_ids


def _selected_index_id(context: ToolExecutionContext, params: dict[str, Any]) -> int | None:
    for candidate in (params.get("index_id"), context.settings.get("__selected_index_id")):
        text = str(candidate or "").strip()
        if text.isdigit():
            return int(text)
    return None


def _import_pandas():
    try:
        import pandas as pd  # type: ignore

        return pd
    except Exception:
        return None


def _read_dataframe_from_file(pd: Any, file_path: Path) -> Any:
    suffix = file_path.suffix.lower()
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(file_path)
    if suffix in {".tsv"}:
        return pd.read_csv(file_path, sep="\t")
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)
    if suffix in {".parquet"}:
        return pd.read_parquet(file_path)
    if suffix in {".json", ".ndjson"}:
        text = file_path.read_text(encoding="utf-8")
        if suffix == ".ndjson":
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
            return pd.DataFrame(rows)
        payload = json.loads(text)
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        if isinstance(payload, dict):
            return pd.DataFrame([payload])
    raise ValueError(f"Unsupported dataset extension: {suffix or 'unknown'}")


def _normalize_dataframe_columns(df: Any) -> Any:
    names: list[str] = []
    used: set[str] = set()
    for idx, column in enumerate(list(df.columns)):
        base = str(column).strip() or f"column_{idx + 1}"
        candidate = base
        bump = 2
        while candidate in used:
            candidate = f"{base}_{bump}"
            bump += 1
        used.add(candidate)
        names.append(candidate)
    df.columns = names
    return df


def _load_dataframe(
    *,
    context: ToolExecutionContext,
    params: dict[str, Any],
) -> tuple[Any | None, str, list[str], AgentSource | None]:
    pd = _import_pandas()
    if pd is None:
        return None, "", ["`pandas` is required for this operation but is not installed."], None

    warnings: list[str] = []
    rows = params.get("rows")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        df = pd.DataFrame([dict(item) for item in rows])
        return _normalize_dataframe_columns(df), "inline rows", warnings, None

    csv_text = str(params.get("csv_text") or "").strip()
    if csv_text:
        df = pd.read_csv(io.StringIO(csv_text))
        return _normalize_dataframe_columns(df), "inline csv_text", warnings, None

    file_ids = _selected_file_ids(context, params)
    index_id = _selected_index_id(context, params)
    if not file_ids:
        return (
            None,
            "",
            ["No dataset provided. Use `rows`, `csv_text`, or select indexed files."],
            None,
        )
    if index_id is None:
        return (
            None,
            "",
            ["No `index_id` is available for selected file IDs."],
            None,
        )

    for file_id in file_ids:
        try:
            file_path, display_name = resolve_indexed_file_path(
                context=get_context(),
                user_id=context.user_id,
                file_id=file_id,
                index_id=index_id,
            )
            df = _read_dataframe_from_file(pd, file_path)
            source = AgentSource(
                source_type="file",
                label=display_name,
                file_id=file_id,
                score=0.8,
                metadata={"path": str(file_path.resolve())},
            )
            return _normalize_dataframe_columns(df), f"indexed file `{display_name}`", warnings, source
        except Exception as exc:
            warnings.append(f"Failed to load file `{file_id}`: {str(exc)}")
    return None, "", warnings or ["No readable tabular file found."], None


def _limit_rows(df: Any, *, max_rows: int) -> tuple[Any, bool]:
    if len(df) <= max_rows:
        return df, False
    return df.head(max_rows), True


def _infer_problem_type(target_series: Any, requested: str) -> str:
    candidate = str(requested or "").strip().lower()
    if candidate in {"classification", "regression"}:
        return candidate
    is_numeric = str(getattr(target_series, "dtype", "")) not in {"", "object"}
    if is_numeric and int(target_series.nunique(dropna=True)) > 15:
        return "regression"
    return "classification"


def _trace_event(
    *,
    tool_id: str,
    event_type: str,
    title: str,
    detail: str = "",
    data: dict[str, Any] | None = None,
) -> ToolTraceEvent:
    payload = {
        "tool_id": tool_id,
        "scene_surface": SCENE_SURFACE_SYSTEM,
    }
    if isinstance(data, dict):
        payload.update(data)
    return ToolTraceEvent(
        event_type=event_type,
        title=title,
        detail=detail,
        data=payload,
    )


def _serialize_cell(value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= 220 else f"{text[:219]}..."
