from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
from typing import Any

from api.services.agent.tools.web_quality import clamp01

_STORE_KEY = "__web_evidence"
_MAX_EVIDENCE_ITEMS = 64
_MAX_EVIDENCE_ROWS_PER_ITEM = 12


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact(value: Any, *, limit: int) -> str:
    clean = " ".join(str(value or "").split()).strip()
    return clean[:limit]


def _entry_id(*, tool_id: str, url: str, fingerprint: str, payload: dict[str, Any]) -> str:
    if fingerprint:
        return f"fp:{fingerprint}"
    raw = {
        "tool_id": tool_id,
        "url": url,
        "provider": str(payload.get("provider") or payload.get("web_provider") or "").strip(),
        "quality_score": payload.get("quality_score"),
        "adapter": str(payload.get("adapter") or "").strip(),
    }
    digest = hashlib.sha256(str(raw).encode("utf-8")).hexdigest()[:20]
    return f"row:{digest}"


def _evidence_rows_from_payload(payload: dict[str, Any], *, default_url: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    raw_rows = payload.get("evidence")
    rows = raw_rows if isinstance(raw_rows, list) else []
    for row in rows[:_MAX_EVIDENCE_ROWS_PER_ITEM]:
        if not isinstance(row, dict):
            continue
        quote = _compact(row.get("quote") or row.get("excerpt"), limit=320)
        if not quote:
            continue
        item = {
            "field": _compact(row.get("field"), limit=80),
            "quote": quote,
            "url": _compact(row.get("url") or default_url, limit=240),
            "confidence": clamp01(row.get("confidence"), default=0.0),
        }
        output.append(item)
    return output


def _evidence_rows_from_sources(sources: list[Any], *, default_url: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source in sources[:_MAX_EVIDENCE_ROWS_PER_ITEM]:
        if not hasattr(source, "metadata"):
            continue
        metadata = getattr(source, "metadata", {})
        payload = metadata if isinstance(metadata, dict) else {}
        quote = ""
        for key in ("excerpt", "snippet", "summary", "quote"):
            quote = _compact(payload.get(key), limit=320)
            if quote:
                break
        if not quote:
            continue
        source_url = _compact(getattr(source, "url", "") or default_url, limit=240)
        output.append(
            {
                "field": "",
                "quote": quote,
                "url": source_url,
                "confidence": clamp01(getattr(source, "score", 0.0), default=0.0),
            }
        )
    return output


def record_web_evidence(
    *,
    settings: dict[str, Any],
    tool_id: str,
    status: str,
    data: dict[str, Any] | None,
    sources: list[Any] | None,
) -> dict[str, Any]:
    payload = data if isinstance(data, dict) else {}
    source_rows = sources if isinstance(sources, list) else []
    store = settings.get(_STORE_KEY)
    if not isinstance(store, dict):
        store = {"items": []}

    url = _compact(payload.get("url"), limit=240)
    if not url:
        for source in source_rows:
            candidate = _compact(getattr(source, "url", ""), limit=240)
            if candidate:
                url = candidate
                break

    fingerprint = _compact(payload.get("extraction_fingerprint"), limit=80)
    identifier = _entry_id(tool_id=tool_id, url=url, fingerprint=fingerprint, payload=payload)
    evidence_rows = _evidence_rows_from_payload(payload, default_url=url)
    if not evidence_rows:
        evidence_rows = _evidence_rows_from_sources(source_rows, default_url=url)

    row = {
        "id": identifier,
        "captured_at": _now_iso(),
        "tool_id": _compact(tool_id, limit=80),
        "status": _compact(status, limit=32),
        "url": url,
        "title": _compact(payload.get("title"), limit=220),
        "provider": _compact(payload.get("provider") or payload.get("web_provider"), limit=80),
        "provider_requested": _compact(payload.get("provider_requested"), limit=80),
        "adapter": _compact(payload.get("adapter"), limit=80),
        "render_quality": _compact(payload.get("render_quality"), limit=32),
        "content_density": round(clamp01(payload.get("content_density"), default=0.0), 4),
        "blocked_signal": bool(payload.get("blocked_signal")),
        "blocked_reason": _compact(payload.get("blocked_reason"), limit=160),
        "quality_score": round(clamp01(payload.get("quality_score"), default=0.0), 4),
        "quality_band": _compact(payload.get("quality_band"), limit=24),
        "confidence": round(clamp01(payload.get("confidence"), default=0.0), 4),
        "schema_coverage": round(clamp01(payload.get("schema_coverage"), default=0.0), 4),
        "extraction_fingerprint": fingerprint,
        "evidence": evidence_rows[:_MAX_EVIDENCE_ROWS_PER_ITEM],
    }

    existing = store.get("items")
    items = [dict(item) for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
    replaced = False
    for idx, item in enumerate(items):
        if str(item.get("id") or "").strip() == identifier:
            items[idx] = row
            replaced = True
            break
    if not replaced:
        items.append(row)
    store["items"] = items[-_MAX_EVIDENCE_ITEMS:]
    settings[_STORE_KEY] = store
    return store


def summarize_web_evidence(settings: dict[str, Any]) -> dict[str, Any]:
    store = settings.get(_STORE_KEY)
    if not isinstance(store, dict):
        return {
            "web_evidence_total": 0,
            "blocked_evidence_total": 0,
            "avg_quality_score": 0.0,
            "citations_ready": False,
            "top_sources": [],
            "items": [],
        }
    rows = store.get("items")
    items = [dict(item) for item in rows if isinstance(item, dict)] if isinstance(rows, list) else []
    if not items:
        return {
            "web_evidence_total": 0,
            "blocked_evidence_total": 0,
            "avg_quality_score": 0.0,
            "citations_ready": False,
            "top_sources": [],
            "items": [],
        }

    blocked = 0
    quality_total = 0.0
    url_counter: Counter[str] = Counter()
    citation_ready_count = 0
    for item in items:
        if bool(item.get("blocked_signal")):
            blocked += 1
        quality_total += clamp01(item.get("quality_score"), default=0.0)
        url = _compact(item.get("url"), limit=240)
        if url:
            url_counter[url] += 1
        evidence_rows = item.get("evidence")
        has_rows = isinstance(evidence_rows, list) and len(evidence_rows) > 0
        if url or has_rows:
            citation_ready_count += 1

    avg_quality = quality_total / float(max(1, len(items)))
    top_sources = [{"url": url, "count": count} for url, count in url_counter.most_common(6)]
    return {
        "web_evidence_total": len(items),
        "blocked_evidence_total": blocked,
        "avg_quality_score": round(clamp01(avg_quality, default=0.0), 4),
        "citations_ready": citation_ready_count == len(items),
        "top_sources": top_sources,
        "items": items[-24:],
    }


__all__ = ["record_web_evidence", "summarize_web_evidence"]
