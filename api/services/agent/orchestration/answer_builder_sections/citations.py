from __future__ import annotations

from typing import Any

from ..text_helpers import compact
from .models import AnswerBuildContext


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _citation_key(*, label: str, url: str) -> str:
    if url:
        return f"url::{url.lower()}"
    if label:
        return f"label::{label.lower()}"
    return ""


def _first_note_text(payload: dict[str, Any]) -> str:
    for key in ("snippet", "excerpt", "summary", "text", "quote"):
        note = _clean(payload.get(key))
        if note:
            return note
    return ""


def _collect_citations(ctx: AnswerBuildContext) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for source in ctx.sources:
        label = _clean(source.label) or "Source"
        url = _clean(source.url)
        metadata = source.metadata if isinstance(source.metadata, dict) else {}
        note = compact(_first_note_text(metadata), 160) if metadata else ""
        key = _citation_key(label=label, url=url)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append({"label": label, "url": url, "note": note})

    report = ctx.verification_report if isinstance(ctx.verification_report, dict) else {}
    evidence_units = report.get("evidence_units")
    if isinstance(evidence_units, list):
        for unit in evidence_units:
            if not isinstance(unit, dict):
                continue
            label = _clean(unit.get("source")) or _clean(unit.get("label")) or "Evidence source"
            url = _clean(unit.get("url"))
            note = compact(_first_note_text(unit), 160)
            key = _citation_key(label=label, url=url)
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append({"label": label, "url": url, "note": note})

    return rows


def append_evidence_citations(lines: list[str], ctx: AnswerBuildContext) -> None:
    lines.append("")
    lines.append("## Evidence Citations")

    citations = _collect_citations(ctx)
    if not citations:
        lines.append(
            "- No external evidence sources were captured in this run; findings are based on internal execution traces."
        )
        return

    for idx, row in enumerate(citations[:12], start=1):
        label = row["label"]
        url = row["url"]
        note = row["note"]
        entry = f"- [{idx}] {label}"
        if url:
            entry += f" | {url}"
        else:
            entry += " | internal evidence"
        if note:
            entry += f" | Note: {note}"
        lines.append(entry)
