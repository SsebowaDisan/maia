from __future__ import annotations

from typing import Any

from api.services.agent.models import AgentSource

from .text_utils import compact


def collect_evidence_units(
    *,
    sources: list[AgentSource],
    executed_steps: list[dict[str, Any]],
) -> list[dict[str, str]]:
    units: list[dict[str, str]] = []
    for source in sources:
        metadata = source.metadata if isinstance(source.metadata, dict) else {}
        excerpt = ""
        for key in ("excerpt", "snippet", "text_excerpt", "description"):
            value = metadata.get(key) if isinstance(metadata, dict) else None
            if isinstance(value, str) and value.strip():
                excerpt = value.strip()
                break
        candidate = " ".join(
            part for part in [source.label.strip(), excerpt] if part
        ).strip()
        if not candidate:
            continue
        units.append(
            {
                "source": source.label.strip() or "Source",
                "url": str(source.url or "").strip(),
                "text": compact(candidate, 560),
            }
        )
    for row in executed_steps:
        tool_id = str(row.get("tool_id") or "").strip()
        summary = str(row.get("summary") or "").strip()
        if not tool_id or not summary:
            continue
        units.append(
            {
                "source": tool_id,
                "url": "",
                "text": compact(summary, 320),
            }
        )
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for unit in units:
        key = f"{unit['source']}|{unit['text']}".lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(unit)
    return deduped[:24]
