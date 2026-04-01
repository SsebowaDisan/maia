"""RAG Bridge — adapts the new clean pipeline to the old app interface.

This module lets the app use the new RAG pipeline without rewriting every
callback and router at once. It wraps pipeline.query_* in the shape that
fast_qa_turn_helpers.py and routers/uploads.py expect.

Migration path:
1. Bridge phase: old code calls bridge, bridge calls new pipeline (WE ARE HERE)
2. Direct phase: old code replaced with direct new pipeline calls
3. Delete phase: old code removed entirely

Usage in fast_qa_turn_helpers.py:
    from api.services.rag.bridge import run_rag_query_bridge
    result = await run_rag_query_bridge(question, source_ids, group_id, owner_id)

Usage in routers/uploads.py:
    from api.services.rag.bridge import run_rag_ingest_bridge
    source = await run_rag_ingest_bridge(file_path, group_id, owner_id)
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json as _stdlib_json
import logging
import os
from pathlib import Path
from threading import RLock
from typing import Any

from api.services.rag.pipeline import (
    ingest_file,
    ingest_url,
    ingest_chat_upload,
    query_group,
    query_file,
    query_sources,
)
from api.services.rag.types import (
    DeliveryPayload, SourceRecord, Citation, CitationTier,
    IngestionStatus, SourceType,
)
from api.services.rag.config import get_config

logger = logging.getLogger(__name__)

_SOURCE_REGISTRY_LOCK = RLock()
_SOURCE_REGISTRY: dict[str, SourceRecord] = {}
_SOURCE_REGISTRY_ORDER: list[str] = []

# ── Registry persistence ────────────────────────────────────────────────────

_REGISTRY_FILE = os.environ.get(
    "MAIA_RAG_REGISTRY_FILE",
    str(
        Path("D:/maia-data/rag_source_registry.json")
        if Path("D:/").exists()
        else Path("ktem_app_data/rag_source_registry.json")
    ),
)


def _save_registry() -> None:
    """Persist the source registry to disk (JSON)."""
    try:
        registry_path = Path(_REGISTRY_FILE)
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        with _SOURCE_REGISTRY_LOCK:
            entries = []
            for source_id in _SOURCE_REGISTRY_ORDER:
                source = _SOURCE_REGISTRY.get(source_id)
                if not source:
                    continue
                entries.append({
                    "id": source.id,
                    "filename": source.filename,
                    "source_type": source.source_type.value if isinstance(source.source_type, SourceType) else str(source.source_type or ""),
                    "group_id": source.group_id or "",
                    "owner_id": source.owner_id or "",
                    "upload_url": source.upload_url or "",
                    "file_size": source.file_size or 0,
                    "rag_ready": source.rag_ready,
                    "citation_ready": source.citation_ready,
                    "status": source.status.value if isinstance(source.status, IngestionStatus) else str(source.status or ""),
                    "created_at": source.created_at or "",
                    "updated_at": source.updated_at or "",
                    "metadata": source.metadata if isinstance(source.metadata, dict) else {},
                })
        registry_path.write_text(_stdlib_json.dumps(entries, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to save source registry: %s", exc)


def _load_registry() -> None:
    """Load the source registry from disk on startup."""
    registry_path = Path(_REGISTRY_FILE)
    if not registry_path.exists():
        return
    try:
        raw = _stdlib_json.loads(registry_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return
        count = 0
        for entry in raw:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            try:
                st = SourceType(entry.get("source_type", "unknown"))
            except (ValueError, KeyError):
                st = SourceType.UNKNOWN
            try:
                status = IngestionStatus(entry.get("status", "rag_ready"))
            except (ValueError, KeyError):
                status = IngestionStatus.RAG_READY
            source = SourceRecord(
                id=entry["id"],
                filename=entry.get("filename", ""),
                source_type=st,
                group_id=entry.get("group_id", ""),
                owner_id=entry.get("owner_id", ""),
                upload_url=entry.get("upload_url", ""),
                file_size=entry.get("file_size", 0),
                rag_ready=entry.get("rag_ready", False),
                citation_ready=entry.get("citation_ready", False),
                status=status,
                created_at=entry.get("created_at", ""),
                updated_at=entry.get("updated_at", ""),
                metadata=entry.get("metadata", {}),
            )
            with _SOURCE_REGISTRY_LOCK:
                sid = str(source.id).strip()
                _SOURCE_REGISTRY[sid] = source
                if sid not in _SOURCE_REGISTRY_ORDER:
                    _SOURCE_REGISTRY_ORDER.append(sid)
            count += 1
        logger.info("Loaded %d sources from registry file", count)
    except Exception as exc:
        logger.warning("Failed to load source registry: %s", exc)


# Load on import
_load_registry()


def _source_scope(source: SourceRecord) -> str:
    metadata = source.metadata if isinstance(source.metadata, dict) else {}
    raw_scope = str(metadata.get("scope") or "").strip().lower()
    if raw_scope:
        return raw_scope
    if metadata.get("chat_id"):
        return "chat_temp"
    return "persistent"


def _normalize_index_id(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _sanitize_source_for_registry(source: SourceRecord) -> SourceRecord:
    metadata = source.metadata if isinstance(source.metadata, dict) else {}
    sanitized = {k: v for k, v in metadata.items() if k != "file_data"}
    return replace(source, metadata=sanitized)


def _register_source(source: SourceRecord) -> None:
    safe_source = _sanitize_source_for_registry(source)
    with _SOURCE_REGISTRY_LOCK:
        source_id = str(safe_source.id or "").strip()
        if not source_id:
            return
        if source_id in _SOURCE_REGISTRY:
            _SOURCE_REGISTRY[source_id] = safe_source
        else:
            _SOURCE_REGISTRY[source_id] = safe_source
            _SOURCE_REGISTRY_ORDER.append(source_id)
    _save_registry()


def list_registered_sources(
    *,
    owner_id: str = "",
    include_chat_temp: bool = False,
    index_id: int | None = None,
) -> list[SourceRecord]:
    normalized_owner = str(owner_id or "").strip()
    requested_index_id = _normalize_index_id(index_id)
    with _SOURCE_REGISTRY_LOCK:
        ordered_ids = list(reversed(_SOURCE_REGISTRY_ORDER))
        rows = [
            _SOURCE_REGISTRY[source_id]
            for source_id in ordered_ids
            if source_id in _SOURCE_REGISTRY
        ]
    selected: list[SourceRecord] = []
    for source in rows:
        if normalized_owner and source.owner_id and source.owner_id != normalized_owner:
            continue
        metadata = source.metadata if isinstance(source.metadata, dict) else {}
        source_scope = _source_scope(source)
        if source_scope == "chat_temp" and not include_chat_temp:
            continue
        if requested_index_id is not None:
            source_index_id = _normalize_index_id(metadata.get("index_id"))
            if source_index_id != requested_index_id:
                continue
        selected.append(source)
    return selected


def resolve_registered_source_path(
    *,
    source_id: str,
    owner_id: str = "",
    index_id: int | None = None,
) -> tuple[Path, str] | None:
    normalized_source_id = str(source_id or "").strip()
    if not normalized_source_id:
        return None
    normalized_owner = str(owner_id or "").strip()
    requested_index_id = _normalize_index_id(index_id)
    with _SOURCE_REGISTRY_LOCK:
        source = _SOURCE_REGISTRY.get(normalized_source_id)
    if source is None:
        return None
    if normalized_owner and source.owner_id and source.owner_id != normalized_owner:
        return None
    metadata = source.metadata if isinstance(source.metadata, dict) else {}
    if requested_index_id is not None:
        source_index_id = _normalize_index_id(metadata.get("index_id"))
        if source_index_id != requested_index_id:
            return None
    raw_path = str(source.upload_url or "").strip()
    if not raw_path or raw_path.startswith(("http://", "https://")):
        return None
    path = Path(raw_path)
    if not path.exists():
        return None
    filename = str(source.filename or path.name or normalized_source_id).strip() or normalized_source_id
    return path, filename


# ── Query Bridge ─────────────────────────────────────────────────────────────

async def run_rag_query_bridge(
    question: str,
    source_ids: list[str] | list[int] | None = None,
    group_id: str = "",
    owner_id: str = "",
    config_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bridge: runs the new pipeline and returns data in the old app's format.

    Returns a dict compatible with what the old fast_qa pipeline returned:
    {
        "answer_text": str,
        "answer_html": str,
        "citations": [...],
        "sources_used": [...],
        "evidence_items": [...],
        "coverage_status": str,
        "trace_id": str,
    }
    """
    cfg = get_config(config_overrides)

    # Normalize source_ids to strings
    str_source_ids = [str(s) for s in source_ids] if source_ids else []

    # Route to the right query function
    try:
        if group_id:
            payload = await query_group(question, group_id, owner_id, cfg)
        elif str_source_ids:
            if len(str_source_ids) == 1:
                payload = await query_file(question, str_source_ids[0], owner_id, cfg)
            else:
                payload = await query_sources(question, str_source_ids, owner_id, cfg)
        else:
            # No specific scope — search all documents for this user
            from api.services.rag.retrieve import RetrievalScope
            payload = await _run_query_unscoped(question, owner_id, cfg)
    except Exception as exc:
        logger.error("RAG pipeline query failed: %s", exc, exc_info=True)
        return _empty_result(f"RAG query failed: {exc}")

    return _payload_to_legacy_format(payload)


def _payload_to_legacy_format(payload: DeliveryPayload) -> dict[str, Any]:
    """Convert the new DeliveryPayload to the old app's expected format."""
    answer_text = payload.answer.text if payload.answer else ""
    highlight_map = payload.answer.highlight_map if payload.answer else {}

    # Build citations in old format
    citations_legacy = []
    for cit in payload.citations:
        legacy_cit: dict[str, Any] = {
            "ref_id": cit.ref_id,
            "source_id": cit.source_id,
            "source_name": cit.source_name,
            "source_type": cit.source_type.value if cit.source_type else "unknown",
            "page": cit.page,
            "snippet": cit.snippet,
            "tier": cit.tier.value if cit.tier else "fallback",
            "credibility": cit.credibility,
            "relevance_score": cit.relevance_score,
            "chunk_id": str(getattr(cit.anchor, "chunk_id", "") or ""),
        }

        # Highlight data for PDF jump
        if cit.highlight_boxes:
            legacy_cit["highlight_boxes"] = [
                {
                    "x": box.x, "y": box.y, "width": box.width, "height": box.height,
                    "page": box.page, "page_width": box.page_width, "page_height": box.page_height,
                }
                for box in cit.highlight_boxes
            ]

        # URL jump data
        if cit.url:
            legacy_cit["url"] = cit.url
            legacy_cit["url_fragment"] = cit.url_fragment

        citations_legacy.append(legacy_cit)

    # Build sources used list
    seen_sources: set[str] = set()
    sources_used = []
    for card in payload.evidence_panel:
        if card.source_id not in seen_sources:
            seen_sources.add(card.source_id)
            sources_used.append({
                "source_id": card.source_id,
                "source_name": card.source_name,
                "source_type": card.source_type.value if card.source_type else "unknown",
                "page": card.page,
                "relevance_score": card.relevance_score,
            })

    # Build evidence items (for the right panel)
    evidence_items = []
    for card in payload.evidence_panel:
        item: dict[str, Any] = {
            "source_id": card.source_id,
            "source_name": card.source_name,
            "page": card.page,
            "snippet": card.snippet,
            "relevance_score": card.relevance_score,
            "heading_path": card.heading_path,
            "ref_id": card.ref_id,
        }
        if card.highlight_boxes:
            item["highlight_boxes"] = [
                {
                    "x": b.x, "y": b.y, "width": b.width, "height": b.height,
                    "page": b.page, "page_width": b.page_width, "page_height": b.page_height,
                }
                for b in card.highlight_boxes
            ]
        evidence_items.append(item)

    # Coverage status
    coverage_status = "unknown"
    if payload.answer and payload.answer.coverage:
        coverage_status = payload.answer.coverage.verdict.value

    # Build answer HTML with proper citation anchors
    answer_html = _inject_citation_anchors(answer_text, citations_legacy, highlight_map)

    # Build infoPanel for the evidence right panel
    info_panel = _build_info_panel(evidence_items, citations_legacy, sources_used, payload, highlight_map)

    # Build info HTML summary
    info_html = _build_info_html(citations_legacy, sources_used, coverage_status)

    return {
        "answer_text": answer_text,
        "answer_html": answer_html,
        "citations": citations_legacy,
        "sources_used": sources_used,
        "evidence_items": evidence_items,
        "info_panel": info_panel,
        "info_html": info_html,
        "coverage_status": coverage_status,
        "warnings": payload.warnings,
        "trace_id": payload.trace_id,
        "search_scope": payload.search_scope,
        "has_calculations": payload.answer.has_calculations if payload.answer else False,
    }


import json as _json
import re as _re

def _to_ui_page_label(raw_page: Any) -> str:
    """Convert 0-indexed pipeline pages to 1-indexed UI labels."""
    if raw_page is None:
        return ""
    raw_text = str(raw_page).strip()
    if not raw_text:
        return ""
    try:
        page_num = int(raw_text)
    except Exception:
        return raw_text
    # RAG pipeline uses 0-indexed pages.
    return str(max(1, page_num + 1))


def _inject_citation_anchors(
    text: str,
    citations: list[dict],
    highlight_map: dict[str, dict] | None = None,
) -> str:
    """Convert [1], [2] markers in answer text to <a class="citation"> HTML tags.
    The frontend parses these data attributes to power the evidence panel + PDF viewer.

    If highlight_map is provided (from LLM), uses the exact sentences as data-phrase
    for precise text-search highlighting in the PDF viewer.
    """
    highlight_map = highlight_map or {}
    cit_map: dict[str, dict] = {}
    for cit in citations:
        ref = cit.get("ref_id", "")  # "[1]"
        num = ref.strip("[]")
        cit_map[num] = cit

    def replace_ref(match: _re.Match) -> str:
        num = match.group(1)
        cit = cit_map.get(num)
        if not cit:
            return match.group(0)

        attrs = [
            f'class="citation"',
            f'href="#evidence-{num}"',
            f'data-citation-number="{num}"',
            f'data-evidence-id="evidence-{num}"',
        ]

        source_type = str(cit.get("source_type", "")).strip().lower()
        is_file_backed = source_type not in {"url", "web", "website"}

        if cit.get("source_id") and is_file_backed:
            attrs.append(f'data-file-id="{cit["source_id"]}"')
            attrs.append(f'data-viewer-url="/api/uploads/files/{cit["source_id"]}/raw"')
        if cit.get("chunk_id"):
            attrs.append(f'data-chunk-id="{cit["chunk_id"]}"')

        if cit.get("url"):
            attrs.append(f'data-source-url="{cit["url"]}"')

        # Use highlight_map page if available, else fall back to citation page
        hm_entry = highlight_map.get(num, {})
        hm_page = hm_entry.get("page")
        if hm_page is not None:
            attrs.append(f'data-page="{hm_page}"')
        else:
            page_label = _to_ui_page_label(cit.get("page"))
            if page_label:
                attrs.append(f'data-page="{page_label}"')

        # Use LLM-provided exact sentences for highlighting (preferred)
        # or fall back to first sentence of chunk snippet
        hm_sentences = hm_entry.get("sentences", [])
        if hm_sentences and isinstance(hm_sentences, list):
            # Join sentences for the phrase — these are exact copies from the PDF
            phrase = " ".join(str(s) for s in hm_sentences[:3])
            safe_phrase = phrase[:300].replace('"', '&quot;')
            attrs.append(f'data-phrase="{safe_phrase}"')
        elif cit.get("snippet"):
            raw_snippet = cit["snippet"]
            first_sentence = _re.split(r'[.!?\n]', raw_snippet, maxsplit=1)[0].strip()
            safe_phrase = (first_sentence[:120] if first_sentence else raw_snippet[:80]).replace('"', '&quot;')
            attrs.append(f'data-phrase="{safe_phrase}"')

        # Strength tier from relevance score
        score = cit.get("relevance_score", 0)
        tier = 3 if score >= 0.7 else (2 if score >= 0.42 else 1)
        attrs.append(f'data-strength="{score:.2f}"')
        attrs.append(f'data-strength-tier="{tier}"')
        attrs.append(f'data-match-quality="{"exact" if score >= 0.7 else "high" if score >= 0.42 else "estimated"}"')

        # Highlight boxes (normalized 0-1)
        boxes = cit.get("highlight_boxes", [])
        if boxes:
            # Normalize pixel coords to 0-1 range using actual page dimensions
            normalized = []
            for b in boxes:
                pw = b.get("page_width") or 595
                ph = b.get("page_height") or 842
                normalized.append({
                    "x": round(b["x"] / pw, 4),
                    "y": round(b["y"] / ph, 4),
                    "width": round(b["width"] / pw, 4),
                    "height": round(b["height"] / ph, 4),
                })
            attrs.append(f'data-boxes=\'{_json.dumps(normalized)}\'')

        return f'<a {" ".join(attrs)}>[{num}]</a>'

    return _re.sub(r"\[(\d+)\]", replace_ref, text)


def _build_info_panel(
    evidence_items: list[dict],
    citations: list[dict],
    sources_used: list[dict],
    payload: DeliveryPayload,
    highlight_map: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Build the infoPanel JSON that powers the evidence right panel."""
    highlight_map = highlight_map or {}
    citation_by_ref: dict[str, dict[str, Any]] = {}
    for row in citations:
        ref_key = str(row.get("ref_id") or "").strip()
        if ref_key:
            citation_by_ref[ref_key] = row

    # Build evidence items in frontend format
    fe_evidence: list[dict[str, Any]] = []
    for i, item in enumerate(evidence_items):
        item_ref = str(item.get("ref_id") or "").strip()
        cit = citation_by_ref.get(item_ref) or (citations[i] if i < len(citations) else {})
        ref_match = _re.search(r"\[(\d+)\]", item_ref or "")
        ref_num = ref_match.group(1) if ref_match else str(i + 1)

        # Use LLM-provided sentences for extract if available
        hm_entry = highlight_map.get(ref_num, {})
        hm_sentences = hm_entry.get("sentences", [])
        if hm_sentences and isinstance(hm_sentences, list):
            extract_text = " ".join(str(s) for s in hm_sentences[:3])[:300]
        else:
            extract_text = _re.split(r'[.!?\n]', item.get("snippet", ""), maxsplit=1)[0].strip()[:150]

        fe_item: dict[str, Any] = {
            "id": f"evidence-{ref_num}",
            "title": f"Evidence [{ref_num}]",
            "source": item.get("source_name", ""),
            "source_type": cit.get("source_type", "pdf"),
            "file_id": item.get("source_id", "") if str(cit.get("source_type", "")).strip().lower() not in {"url", "web", "website"} else "",
            "chunk_id": str(cit.get("chunk_id", "") or ""),
            "source_url": cit.get("url", ""),
            "page": str(hm_entry.get("page", "")) if hm_entry.get("page") else _to_ui_page_label(item.get("page")),
            "extract": extract_text,
            "confidence": item.get("relevance_score", 0),
            "strength_score": cit.get("relevance_score", 0),
            "strength_tier": 3 if cit.get("relevance_score", 0) >= 0.7 else (2 if cit.get("relevance_score", 0) >= 0.42 else 1),
            "match_quality": "exact" if cit.get("relevance_score", 0) >= 0.7 else "high",
        }

        # Highlight boxes
        boxes = item.get("highlight_boxes", [])
        if boxes:
            normalized = []
            for b in boxes:
                pw = b.get("page_width") or 595
                ph = b.get("page_height") or 842
                normalized.append({
                    "x": round(b["x"] / pw, 4),
                    "y": round(b["y"] / ph, 4),
                    "width": round(b["width"] / pw, 4),
                    "height": round(b["height"] / ph, 4),
                })
            fe_item["highlight_boxes"] = normalized

        # Evidence units for character-level highlighting
        # Use LLM sentences if available — these are exact PDF text for precise highlighting
        if hm_sentences:
            fe_item["evidence_units"] = [
                {"text": str(s), "highlight_boxes": fe_item.get("highlight_boxes", [])}
                for s in hm_sentences[:3]
            ]
        elif item.get("snippet"):
            first_sentence = _re.split(r'[.!?\n]', item["snippet"], maxsplit=1)[0].strip()
            fe_item["evidence_units"] = [{
                "text": first_sentence[:150],
                "highlight_boxes": fe_item.get("highlight_boxes", []),
            }]

        # Review location for "Open" button
        fe_item["review_location"] = {
            "file_id": item.get("source_id", "") if str(cit.get("source_type", "")).strip().lower() not in {"url", "web", "website"} else "",
            "chunk_id": str(cit.get("chunk_id", "") or ""),
            "source_url": cit.get("url", ""),
            "page": _to_ui_page_label(item.get("page")),
            "surface": "web" if str(cit.get("source_type", "")).strip().lower() in {"url", "web", "website"} else "pdf",
        }

        fe_evidence.append(fe_item)

    # Selected scope
    scope: dict[str, Any] = {
        "file_count": len(sources_used),
        "covered_file_count": len(sources_used),
        "searched_source_count": len(sources_used),
        "searched_sources": [
            {
                "label": s.get("source_name", ""),
                "source_type": s.get("source_type", "pdf"),
                "file_id": s.get("source_id", ""),
                "credibility_tier": "platform",
            }
            for s in sources_used
        ],
    }

    return {
        "evidence_items": fe_evidence,
        "selected_scope": scope,
    }


def _build_info_html(citations: list[dict], sources_used: list[dict], coverage: str) -> str:
    """Build the info HTML string for the legacy info panel."""
    if not citations:
        return ""

    parts = ['<div class="rag-evidence-summary">']
    parts.append(f'<p><strong>{len(citations)} source{"s" if len(citations) != 1 else ""}</strong> cited from {len(sources_used)} file{"s" if len(sources_used) != 1 else ""}</p>')

    for cit in citations:
        ref = cit.get("ref_id", "")
        name = cit.get("source_name", "")
        page = _to_ui_page_label(cit.get("page", ""))
        snippet = cit.get("snippet", "")[:150]
        parts.append(f'<details class="evidence"><summary>{ref} {name} p.{page}</summary><p>{snippet}</p></details>')

    parts.append('</div>')
    return "\n".join(parts)


def _empty_result(message: str) -> dict[str, Any]:
    return {
        "answer_text": message,
        "answer_html": message,
        "citations": [],
        "sources_used": [],
        "evidence_items": [],
        "coverage_status": "insufficient",
        "warnings": [message],
        "trace_id": "",
        "search_scope": "",
        "has_calculations": False,
    }


async def _run_query_unscoped(
    question: str,
    owner_id: str,
    config: Any,
) -> DeliveryPayload:
    """Query all indexed documents for this user (no specific file/group scope)."""
    from api.services.rag.pipeline import _run_query
    from api.services.rag.retrieve import RetrievalScope

    scope = RetrievalScope(owner_id=owner_id)
    return await _run_query(question, scope, "all documents", config, f"trace_{__import__('uuid').uuid4().hex[:12]}")


# ── Ingestion Bridge ─────────────────────────────────────────────────────────

async def run_rag_ingest_bridge(
    file_path: str,
    group_id: str = "",
    owner_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bridge: runs the new ingestion pipeline and returns data in old format.

    Returns:
    {
        "source_id": str,
        "status": str,
        "rag_ready": bool,
        "citation_ready": bool,
        "filename": str,
    }
    """
    try:
        source = await ingest_file(file_path, group_id, owner_id, metadata=metadata)
        _register_source(source)
        return _source_to_legacy_format(source)
    except Exception as exc:
        logger.error("RAG pipeline ingest failed: %s", exc, exc_info=True)
        return {
            "source_id": "",
            "status": "failed",
            "rag_ready": False,
            "citation_ready": False,
            "filename": file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path,
            "error": str(exc),
        }


async def run_rag_ingest_url_bridge(
    url: str,
    group_id: str = "",
    owner_id: str = "",
) -> dict[str, Any]:
    """Bridge: ingest a URL via the new pipeline."""
    try:
        source = await ingest_url(url, group_id, owner_id)
        _register_source(source)
        return _source_to_legacy_format(source)
    except Exception as exc:
        logger.error("RAG URL ingest failed: %s", exc, exc_info=True)
        return {
            "source_id": "",
            "status": "failed",
            "rag_ready": False,
            "citation_ready": False,
            "filename": url,
            "error": str(exc),
        }


async def run_rag_chat_upload_bridge(
    file_data: bytes,
    filename: str,
    chat_id: str,
    owner_id: str = "",
) -> dict[str, Any]:
    """Bridge: ingest a chat-uploaded file via the new pipeline."""
    try:
        source = await ingest_chat_upload(file_data, filename, chat_id, owner_id)
        _register_source(source)
        return _source_to_legacy_format(source)
    except Exception as exc:
        logger.error("RAG chat upload failed: %s", exc, exc_info=True)
        return {
            "source_id": "",
            "status": "failed",
            "rag_ready": False,
            "citation_ready": False,
            "filename": filename,
            "error": str(exc),
        }


def _source_to_legacy_format(source: SourceRecord) -> dict[str, Any]:
    return {
        "source_id": source.id,
        "status": source.status.value if isinstance(source.status, IngestionStatus) else str(source.status),
        "rag_ready": source.rag_ready,
        "citation_ready": source.citation_ready,
        "filename": source.filename,
        "source_type": source.source_type.value if source.source_type else "unknown",
        "group_id": source.group_id,
        "processing_route": source.processing_route.value if source.processing_route else "",
    }


# ── Highlight Bridge ─────────────────────────────────────────────────────────

async def get_highlight_target_bridge(
    source_id: str,
    chunk_id: str,
    page: int | None = None,
) -> dict[str, Any]:
    """Bridge: replaces the old pdf_highlight_locator endpoint.

    Returns highlight box data for the PDF viewer:
    {
        "source_id": str,
        "page": int,
        "highlight_boxes": [{"x": float, "y": float, "width": float, "height": float}],
        "tier": str,
        "snippet": str,
    }
    """
    from api.services.rag.citation_prep import get_anchors

    requested_page_zero: int | None = None
    if page is not None:
        try:
            page_int = int(page)
            # UI sends 1-indexed pages; anchors are 0-indexed.
            requested_page_zero = max(0, page_int - 1)
        except Exception:
            requested_page_zero = None

    anchors = get_anchors(chunk_id)

    if not anchors:
        return {
            "source_id": source_id,
            "page": max(1, int(page or 1)),
            "highlight_boxes": [],
            "tier": "fallback",
            "snippet": "",
        }

    # Find best anchor — prefer EXACT tier, or matching page
    best = anchors[0]
    for a in anchors:
        if a.tier == CitationTier.EXACT:
            best = a
            break
        if requested_page_zero is not None and a.page == requested_page_zero:
            best = a

    boxes = []
    if best.bbox:
        x = float(best.bbox.x)
        y = float(best.bbox.y)
        width = float(best.bbox.width)
        height = float(best.bbox.height)
        # Frontend preview expects normalized 0..1 geometry. Extraction stores
        # PDF point coordinates, so normalize if values look non-normalized.
        if max(abs(x), abs(y), abs(width), abs(height)) > 1.5:
            x = x / 595.0
            y = y / 842.0
            width = width / 595.0
            height = height / 842.0
        x = max(0.0, min(1.0, x))
        y = max(0.0, min(1.0, y))
        width = max(0.0, min(1.0 - x, width))
        height = max(0.0, min(1.0 - y, height))
        boxes.append({
            "x": round(x, 6),
            "y": round(y, 6),
            "width": round(width, 6),
            "height": round(height, 6),
        })

    return {
        "source_id": source_id,
        "page": max(1, int(best.page) + 1),
        "highlight_boxes": boxes,
        "tier": best.tier.value if best.tier else "fallback",
        "snippet": best.text_snippet,
    }
