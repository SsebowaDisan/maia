from __future__ import annotations

import html
from typing import Any
from urllib.parse import parse_qs, urlparse

from .verification_contract_core import (
    VERIFICATION_CONTRACT_VERSION,
    normalize_verification_evidence_items,
)


def _safe_int(value: Any) -> int | None:
    try:
        parsed = int(str(value).strip())
    except Exception:
        return None
    return parsed


def _clean_text(value: Any, *, max_len: int = 1200) -> str:
    return " ".join(str(value or "").split()).strip()[: max(1, int(max_len))]


def _normalize_http_url(value: Any) -> str:
    text = _clean_text(value, max_len=2048).strip(" <>\"'`")
    if not text:
        return ""
    text = text.rstrip(".,;:!?")
    try:
        parsed = urlparse(text)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return parsed.geturl()


def _normalize_source_id(value: Any) -> str:
    text = _clean_text(value, max_len=220).lower()
    return text


def _domain_from_url(value: str) -> str:
    try:
        host = str(urlparse(value).hostname or "").strip().lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


_TEST_HOSTS = {"example.com", "example.org", "example.net"}
_TEST_PARAMS = {"maia_gap_test_media", "maia_no_pdf", "maia_gap_test"}


def _is_placeholder_test_url(value: str) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    host = str(parsed.hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    if host in _TEST_HOSTS:
        return True
    try:
        query_keys = set(parse_qs(parsed.query).keys())
    except Exception:
        query_keys = set()
    return bool(query_keys & _TEST_PARAMS)


def _is_placeholder_test_source(*, source_url: str, source_id: str) -> bool:
    if _is_placeholder_test_url(source_url):
        return True
    source_id_text = _clean_text(source_id, max_len=2048)
    if source_id_text.lower().startswith("url:"):
        return _is_placeholder_test_url(source_id_text[4:])
    return False


def _source_url_from_item(item: dict[str, Any]) -> str:
    source_map = item.get("source") if isinstance(item.get("source"), dict) else {}
    review_map = item.get("review_location") if isinstance(item.get("review_location"), dict) else {}
    return _normalize_http_url(
        item.get("source_url")
        or item.get("sourceUrl")
        or source_map.get("url")
        or review_map.get("source_url")
        or review_map.get("sourceUrl")
        or item.get("url")
    )


def _source_id_from_item(item: dict[str, Any], *, source_url: str) -> str:
    source_map = item.get("source") if isinstance(item.get("source"), dict) else {}
    review_map = item.get("review_location") if isinstance(item.get("review_location"), dict) else {}
    source_id = _normalize_source_id(
        item.get("source_id")
        or item.get("sourceId")
        or source_map.get("id")
        or review_map.get("source_id")
        or review_map.get("sourceId")
    )
    if source_id:
        return source_id
    if source_url:
        return f"url:{source_url}".lower()
    return ""


def _source_type_from_item(item: dict[str, Any], *, source_url: str) -> str:
    source_map = item.get("source") if isinstance(item.get("source"), dict) else {}
    review_map = item.get("review_location") if isinstance(item.get("review_location"), dict) else {}
    lowered = _clean_text(
        item.get("source_type")
        or item.get("sourceType")
        or source_map.get("type")
        or review_map.get("surface"),
        max_len=48,
    ).lower()
    if lowered in {"web", "website", "url", "site"}:
        return "web"
    if source_url:
        return "web"
    return lowered


def _extract_review_content(item: dict[str, Any]) -> dict[str, str]:
    review_content = item.get("review_content")
    if not isinstance(review_content, dict):
        review_content = item.get("reviewContent") if isinstance(item.get("reviewContent"), dict) else {}
    review_html = _clean_text(review_content.get("html"), max_len=24000)
    review_text = _clean_text(review_content.get("text"), max_len=24000)
    review_title = _clean_text(review_content.get("title"), max_len=240)
    return {
        "html": review_html,
        "text": review_text,
        "title": review_title,
    }


def _extract_snippet(item: dict[str, Any]) -> str:
    citation_map = item.get("citation") if isinstance(item.get("citation"), dict) else {}
    target_map = item.get("highlight_target") if isinstance(item.get("highlight_target"), dict) else {}
    return _clean_text(
        item.get("extract")
        or item.get("snippet")
        or citation_map.get("quote")
        or target_map.get("phrase")
        or item.get("text"),
        max_len=1600,
    )


def _build_safe_paragraph_html(paragraphs: list[str]) -> str:
    if not paragraphs:
        return ""
    rendered = "".join(f"<p>{html.escape(row)}</p>" for row in paragraphs if row)
    return rendered[:32000]


def build_web_review_content(
    evidence_items: list[dict[str, Any]],
    *,
    max_sources: int = 16,
    max_snippets_per_source: int = 18,
) -> dict[str, Any]:
    if not isinstance(evidence_items, list) or not evidence_items:
        return {}

    grouped: dict[str, dict[str, Any]] = {}
    source_order: list[str] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        source_url = _source_url_from_item(item)
        source_type = _source_type_from_item(item, source_url=source_url)
        if source_type != "web":
            continue
        source_id = _source_id_from_item(item, source_url=source_url)
        if not source_id:
            source_id = f"url:{source_url}".lower() if source_url else ""
        if not source_id:
            continue
        if _is_placeholder_test_source(source_url=source_url, source_id=source_id):
            continue
        row = grouped.get(source_id)
        if row is None:
            if len(source_order) >= max(1, int(max_sources)):
                continue
            source_order.append(source_id)
            source_map = item.get("source") if isinstance(item.get("source"), dict) else {}
            source_title = _clean_text(
                source_map.get("title")
                or item.get("source_name")
                or item.get("source")
                or item.get("title")
                or "Website source",
                max_len=220,
            ) or "Website source"
            review_payload = _extract_review_content(item)
            row = {
                "source_id": source_id,
                "source_url": source_url,
                "title": review_payload["title"] or source_title,
                "domain": _domain_from_url(source_url),
                "readable_text": review_payload["text"],
                "readable_html": review_payload["html"],
                "evidence_ids": [],
                "snippets": [],
                "snippet_seen": set(),
            }
            grouped[source_id] = row

        evidence_id = _clean_text(item.get("id") or item.get("evidence_id"), max_len=80).lower()
        if evidence_id and evidence_id not in row["evidence_ids"]:
            row["evidence_ids"].append(evidence_id)

        snippet = _extract_snippet(item)
        if snippet and snippet.lower() not in row["snippet_seen"]:
            if len(row["snippets"]) < max(1, int(max_snippets_per_source)):
                row["snippets"].append(snippet)
                row["snippet_seen"].add(snippet.lower())

    sources_payload: list[dict[str, Any]] = []
    for source_id in source_order:
        row = grouped.get(source_id)
        if not row:
            continue
        snippets = list(row["snippets"])
        readable_text = _clean_text(
            row.get("readable_text") or "\n\n".join(snippets),
            max_len=32000,
        )
        readable_html = _clean_text(
            row.get("readable_html") or _build_safe_paragraph_html(snippets),
            max_len=32000,
        )
        if not readable_text and snippets:
            readable_text = _clean_text("\n\n".join(snippets), max_len=32000)
        if not readable_html and snippets:
            readable_html = _build_safe_paragraph_html(snippets)
        if not readable_text and not readable_html:
            continue
        sources_payload.append(
            {
                "source_id": row["source_id"],
                "source_url": row["source_url"] or None,
                "title": row["title"],
                "domain": row["domain"] or None,
                "readable_text": readable_text or None,
                "readable_html": readable_html or None,
                "evidence_ids": row["evidence_ids"][:24],
                "snippet_count": len(snippets),
            }
        )

    if not sources_payload:
        return {}
    return {
        "version": "web_review.v1",
        "sources": sources_payload,
        "source_order": source_order[: len(sources_payload)],
    }


def build_verification_evidence_items(
    *,
    snippets_with_refs: list[dict[str, Any]],
    refs: list[dict[str, Any]],
    max_items: int = 64,
) -> list[dict[str, Any]]:
    if not snippets_with_refs and not refs:
        return []
    refs_by_id: dict[int, dict[str, Any]] = {}
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        ref_id = _safe_int(ref.get("id"))
        if ref_id is None or ref_id <= 0:
            continue
        refs_by_id[ref_id] = ref

    candidates: list[dict[str, Any]] = []
    seen_ref_ids: set[int] = set()
    for snippet in snippets_with_refs:
        if not isinstance(snippet, dict):
            continue
        ref_id = _safe_int(snippet.get("ref_id"))
        if ref_id and ref_id in seen_ref_ids:
            continue
        if ref_id:
            seen_ref_ids.add(ref_id)
        ref = refs_by_id.get(ref_id or 0, {})
        candidate: dict[str, Any] = {
            "id": f"evidence-{ref_id}" if ref_id and ref_id > 0 else "",
            "title": f"Evidence [{ref_id}]" if ref_id and ref_id > 0 else "Evidence",
            "source_name": snippet.get("source_name") or ref.get("source_name") or ref.get("label") or "Indexed source",
            "source_url": snippet.get("source_url") or snippet.get("page_url") or snippet.get("url") or ref.get("source_url"),
            "source_id": snippet.get("source_id") or ref.get("source_id"),
            "source_type": snippet.get("source_type") or ref.get("source_type"),
            "page": snippet.get("page_label") or ref.get("page_label"),
            "extract": snippet.get("text") or ref.get("phrase"),
            "unit_id": snippet.get("unit_id") or ref.get("unit_id"),
            "selector": snippet.get("selector") or ref.get("selector"),
            "char_start": snippet.get("char_start") or ref.get("char_start"),
            "char_end": snippet.get("char_end") or ref.get("char_end"),
            "match_quality": snippet.get("match_quality") or ref.get("match_quality"),
            "strength_score": snippet.get("strength_score") or ref.get("strength_score"),
            "strength_tier": snippet.get("strength_tier") or ref.get("strength_tier"),
            "highlight_boxes": snippet.get("highlight_boxes") or ref.get("highlight_boxes"),
        }
        candidates.append(candidate)

    for ref_id, ref in sorted(refs_by_id.items(), key=lambda item: item[0]):
        if ref_id in seen_ref_ids:
            continue
        candidates.append(
            {
                "id": f"evidence-{ref_id}",
                "title": f"Evidence [{ref_id}]",
                "source_name": ref.get("source_name") or ref.get("label") or "Indexed source",
                "source_url": ref.get("source_url"),
                "source_id": ref.get("source_id"),
                "source_type": ref.get("source_type"),
                "page": ref.get("page_label"),
                "extract": ref.get("phrase"),
                "unit_id": ref.get("unit_id"),
                "selector": ref.get("selector"),
                "char_start": ref.get("char_start"),
                "char_end": ref.get("char_end"),
                "match_quality": ref.get("match_quality"),
                "strength_score": ref.get("strength_score"),
                "strength_tier": ref.get("strength_tier"),
                "highlight_boxes": ref.get("highlight_boxes"),
            }
        )

    return normalize_verification_evidence_items(candidates, max_items=max_items)


__all__ = [
    "VERIFICATION_CONTRACT_VERSION",
    "build_verification_evidence_items",
    "build_web_review_content",
    "normalize_verification_evidence_items",
]
