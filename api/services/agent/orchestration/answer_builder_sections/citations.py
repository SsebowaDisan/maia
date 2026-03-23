from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from ..text_helpers import compact
from .models import AnswerBuildContext


URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>\]\)]+", re.IGNORECASE)
OPERATIONAL_LABEL_PREFIXES = (
    "workspace.",
    "gmail.",
    "email.",
    "mailer.",
    "report.",
    "contract.",
    "verification.",
)
OPERATIONAL_PROVIDER_HINTS = {
    "google_sheets",
    "workspace_sheets",
    "workspace_docs",
    "workspace_docs_template",
    "workspace_tracker",
}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_url(value: Any) -> str:
    raw = _clean(value).strip(" <>\"'`")
    if not raw:
        return ""
    raw = raw.rstrip(".,;:!?")
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return parsed.geturl()


def _first_url(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ""
    match = URL_IN_TEXT_RE.search(text)
    if not match:
        return ""
    return _normalize_url(match.group(0))


def _is_operational_source(*, label: str, metadata: dict[str, Any] | None) -> bool:
    lowered = _clean(label).lower()
    if any(lowered.startswith(prefix) for prefix in OPERATIONAL_LABEL_PREFIXES):
        return True
    payload = metadata if isinstance(metadata, dict) else {}
    provider = _clean(payload.get("provider")).lower()
    if provider in OPERATIONAL_PROVIDER_HINTS:
        return True
    tool_id = _clean(payload.get("tool_id")).lower()
    if tool_id and any(tool_id.startswith(prefix) for prefix in OPERATIONAL_LABEL_PREFIXES):
        return True
    return False


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


def collect_evidence_citations(ctx: AnswerBuildContext) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    include_operational = bool(ctx.runtime_settings.get("__include_operational_citations"))

    for source in ctx.sources:
        label = _clean(source.label) or "Source"
        metadata = source.metadata if isinstance(source.metadata, dict) else {}
        if not include_operational and _is_operational_source(label=label, metadata=metadata):
            continue
        url = (
            _normalize_url(source.url)
            or _normalize_url(metadata.get("source_url"))
            or _normalize_url(metadata.get("page_url"))
            or _normalize_url(metadata.get("url"))
            or _first_url(label)
        )
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
            if not include_operational and _is_operational_source(label=label, metadata=None):
                continue
            url = _normalize_url(unit.get("url")) or _first_url(unit.get("text"))
            note = compact(_first_note_text(unit), 160)
            key = _citation_key(label=label, url=url)
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append({"label": label, "url": url, "note": note})

    for setting_key in ("__latest_report_sources", "__latest_web_sources"):
        source_rows = ctx.runtime_settings.get(setting_key)
        if not isinstance(source_rows, list):
            continue
        for row in source_rows:
            if not isinstance(row, dict):
                continue
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            label = _clean(row.get("label")) or "Source"
            if not include_operational and _is_operational_source(label=label, metadata=metadata):
                continue
            url = (
                _normalize_url(row.get("url"))
                or _normalize_url(metadata.get("source_url"))
                or _normalize_url(metadata.get("page_url"))
                or _normalize_url(metadata.get("url"))
                or _first_url(row.get("snippet"))
                or _first_url(label)
            )
            note = compact(_first_note_text(row), 160)
            key = _citation_key(label=label, url=url)
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append({"label": label, "url": url, "note": note})

    return rows


def append_evidence_citations(lines: list[str], ctx: AnswerBuildContext) -> None:
    lines.append("")
    lines.append("## Evidence Citations")

    citations = collect_evidence_citations(ctx)
    if not citations:
        lines.append(
            "- No external evidence sources were captured in this run; findings are based on internal execution traces."
        )
        return

    show_diagnostics = bool(ctx.runtime_settings.get("__show_response_diagnostics"))
    depth_tier = " ".join(
        str(ctx.runtime_settings.get("__research_depth_tier") or "").split()
    ).strip().lower()
    # Scale citation count to the depth of the task.  Flooding a simple
    # "what is X?" answer with 24 citations harms readability.
    if depth_tier in {"deep_research", "deep_analytics", "expert"}:
        max_external_citations = 24
    elif depth_tier in {"research", "standard_research"}:
        max_external_citations = 12
    else:
        max_external_citations = 8
    external_rows = [row for row in citations if row.get("url")]
    internal_rows = [row for row in citations if not row.get("url")]
    ordered_rows = external_rows[:max_external_citations]
    if show_diagnostics:
        ordered_rows += internal_rows[:3]

    for idx, row in enumerate(ordered_rows, start=1):
        label = row["label"]
        url = row["url"]
        note = compact(row["note"], 96)
        if url:
            # When the label IS the URL, use just the hostname as the display text
            # so we don't get redundant "- [1] [https://example.com](https://example.com)"
            display_label = label
            if label.lower().startswith(("http://", "https://")) and label.rstrip("/") == url.rstrip("/"):
                try:
                    from urllib.parse import urlparse as _urlparse
                    parsed = _urlparse(url)
                    display_label = parsed.netloc or label
                except Exception:
                    display_label = label
            entry = f"- [{idx}] [{display_label}]({url})"
        else:
            entry = f"- [{idx}] {label} | internal evidence"
        if note and not url:
            entry += f" | {note}"
        lines.append(entry)
