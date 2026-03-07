from __future__ import annotations

from typing import Any


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized_text(value: Any) -> str:
    return _clean_text(value).lower()


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed != parsed:
        return None
    return parsed


def _as_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed >= 0 else None


def _string_list(value: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = [_clean_text(item) for item in value]
    non_empty = [item for item in cleaned if item]
    return list(dict.fromkeys(non_empty))[: max(1, int(limit or 1))]


def _candidate_terms(data: dict[str, Any]) -> tuple[list[str], str]:
    semantic_terms = _string_list(data.get("semantic_find_terms"), limit=12)
    if semantic_terms:
        return semantic_terms, "semantic_find_terms"
    query_variants = _string_list(data.get("query_variants"), limit=12)
    if query_variants:
        return query_variants, "query_variants"
    search_terms = _string_list(data.get("search_terms"), limit=12)
    if search_terms:
        return search_terms, "search_terms"
    planned_search_terms = _string_list(data.get("planned_search_terms"), limit=12)
    if planned_search_terms:
        return planned_search_terms, "planned_search_terms"
    highlighted = _string_list(data.get("highlighted_keywords"), limit=12)
    if highlighted:
        return highlighted, "highlighted_keywords"
    keywords = _string_list(data.get("keywords"), limit=12)
    if keywords:
        return keywords, "keywords"
    return [], ""


def _normalize_semantic_find_results(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("semantic_find_results")
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(raw[:12], start=1):
        if not isinstance(row, dict):
            continue
        term = _clean_text(row.get("term") or row.get("query") or row.get("text"))
        if not term:
            continue
        confidence = _as_float(row.get("confidence"))
        if confidence is None:
            confidence = _as_float(row.get("score"))
        if confidence is None:
            confidence = max(0.35, 0.93 - ((index - 1) * 0.08))
        confidence = max(0.0, min(1.0, round(float(confidence), 3)))
        rank = _as_int(row.get("rank")) or index
        normalized.append({"term": term, "confidence": confidence, "rank": rank})
    return normalized


def _derived_semantic_find_results(
    *,
    terms: list[str],
    match_count: int | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    boost = 0.0
    if isinstance(match_count, int) and match_count > 0:
        boost = min(0.07, max(0.0, match_count * 0.004))
    for index, term in enumerate(terms[:12], start=1):
        base_confidence = max(0.35, 0.92 - ((index - 1) * 0.08))
        confidence = max(0.0, min(1.0, round(base_confidence + boost, 3)))
        normalized.append({"term": term, "confidence": confidence, "rank": index})
    return normalized


def apply_semantic_find(
    *,
    event_type: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    payload = dict(data or {})
    normalized_event = _normalized_text(event_type)
    explicit_results = _normalize_semantic_find_results(payload)
    terms, source_key = _candidate_terms(payload)
    if explicit_results:
        payload["semantic_find_results"] = explicit_results
        payload["semantic_find_terms"] = [item["term"] for item in explicit_results]
    elif terms:
        match_count = _as_int(payload.get("match_count"))
        payload["semantic_find_results"] = _derived_semantic_find_results(
            terms=terms,
            match_count=match_count,
        )
        payload["semantic_find_terms"] = terms

    semantic_terms = _string_list(payload.get("semantic_find_terms"), limit=12)
    if semantic_terms:
        query = (
            _clean_text(payload.get("semantic_find_query"))
            or _clean_text(payload.get("find_query"))
            or " ".join(semantic_terms[:2]).strip()
            or semantic_terms[0]
        )
        payload["semantic_find_query"] = query
        if source_key:
            payload["semantic_find_source"] = source_key
        match_count = _as_int(payload.get("match_count"))
        if match_count is not None:
            payload["semantic_find_match_count"] = match_count
        elif normalized_event.startswith(("browser_find", "pdf_find", "pdf.find")):
            payload["semantic_find_match_count"] = len(semantic_terms)

    return payload


__all__ = ["apply_semantic_find"]
