from __future__ import annotations

from datetime import datetime, timezone
import os
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


def coerce_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def normalize_public_role(value: Any) -> str:
    role = str(value or "reader").strip().lower() or "reader"
    if role not in {"reader", "commenter", "writer"}:
        return "reader"
    return role


def resolve_public_share_options(*, params: dict[str, Any], settings: dict[str, Any]) -> tuple[bool, str, bool]:
    make_public_default = coerce_bool(
        settings.get("agent.workspace_make_public"),
        default=coerce_bool(os.getenv("MAIA_WORKSPACE_MAKE_PUBLIC"), default=False),
    )
    make_public = coerce_bool(params.get("make_public"), default=make_public_default)

    role_default = normalize_public_role(
        settings.get("agent.workspace_public_role") or os.getenv("MAIA_WORKSPACE_PUBLIC_ROLE")
    )
    role = normalize_public_role(params.get("public_role") or role_default)

    discoverable_default = coerce_bool(
        settings.get("agent.workspace_public_discoverable"),
        default=coerce_bool(os.getenv("MAIA_WORKSPACE_PUBLIC_DISCOVERABLE"), default=False),
    )
    discoverable = coerce_bool(params.get("public_discoverable"), default=discoverable_default)
    return make_public, role, discoverable
