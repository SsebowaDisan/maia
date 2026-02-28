from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generator

from api.services.agent.tools.base import ToolExecutionResult, ToolTraceEvent


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def chunk_text(text: str, *, chunk_size: int = 180, max_chunks: int = 8) -> list[str]:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return []
    chunks: list[str] = []
    cursor = 0
    size = max(40, int(chunk_size))
    while cursor < len(cleaned) and len(chunks) < max(1, int(max_chunks)):
        chunks.append(cleaned[cursor : cursor + size])
        cursor += size
    if cursor < len(cleaned):
        chunks[-1] = f"{chunks[-1]}..."
    return chunks


def sheet_col_name(index_zero_based: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if index_zero_based < 0:
        return "A"
    name = ""
    index = index_zero_based
    while True:
        name = alphabet[index % 26] + name
        index = index // 26 - 1
        if index < 0:
            break
    return name


def drain_stream(
    stream: Generator[ToolTraceEvent, None, ToolExecutionResult],
) -> ToolExecutionResult:
    traces: list[ToolTraceEvent] = []
    while True:
        try:
            traces.append(next(stream))
        except StopIteration as stop:
            result = stop.value
            break
    result.events = traces
    return result


def coerce_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
