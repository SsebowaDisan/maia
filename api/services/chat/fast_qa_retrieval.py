from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from sqlmodel import Session, select

from ktem.db.models import engine

from api.context import ApiContext

from .fast_qa_retrieval_helpers import (
    _extract_evidence_units,
    _extract_highlight_boxes,
    _extract_query_terms,
    _extract_target_hosts,
    _matches_target_hosts,
    _page_label_sort_key,
    _ranked_chunk_selection,
    _to_float,
)


_LOW_VALUE_PREFIXES = (
    "figure ",
    "fig. ",
    "table ",
    "chapter ",
    "contents ",
    "appendix ",
    "# figure ",
    "# table ",
    "# nomenclature",
    "## nomenclature",
)

_STREAM_TERMS = (
    "feed",
    "feeds",
    "vapor",
    "vapour",
    "liquid",
    "distillate",
    "bottoms",
    "column",
    "stream",
    "reflux",
)

_BALANCE_TERMS = (
    "material balance",
    "component balance",
    "mass balance",
    "distillation column",
    "component material balance",
)

_FORMULA_VALUE_RE = re.compile(
    r"(?:\$\$.*?=\s*.*?\$\$|[FDVBLMQW]\s*[xXyYzZ]?\s*_\{?[A-Za-z0-9,+\-]+\}?\s*=\s*.+)",
    re.IGNORECASE | re.DOTALL,
)
_ALPHA_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_PLACEHOLDER_HOSTS = {"example.com", "example.org", "example.net", "localhost", "127.0.0.1"}
_LOW_CREDIBILITY_HOSTS = {
    "w3schools.com",
    "geeksforgeeks.org",
    "tutorialspoint.com",
    "javatpoint.com",
}


def _source_kind(*, source_name: str, source_url: str, metadata: dict[str, Any]) -> str:
    normalized_url = str(source_url or "").strip().lower()
    normalized_name = str(source_name or "").strip().lower()
    mime_type = str(metadata.get("mime_type", "") or "").strip().lower()
    loader = str(metadata.get("loader", "") or "").strip().lower()
    doc_type = str(metadata.get("type", "") or "").strip().lower()
    if normalized_url.startswith(("http://", "https://")) or normalized_name.startswith(("http://", "https://")):
        return "web"
    if mime_type == "application/pdf" or normalized_name.endswith(".pdf") or "pdf" in loader:
        return "pdf"
    if doc_type in {"image", "thumbnail"}:
        return "image"
    return "file"


def _is_low_value_chunk(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return True
    if lowered.startswith(_LOW_VALUE_PREFIXES):
        return True
    if lowered.startswith(("figure", "table")) and len(lowered) < 80:
        return True
    if "nomenclature" in lowered and "=" not in lowered and "$$" not in lowered:
        return True
    if lowered.count("figure ") >= 1 and len(lowered) < 120:
        return True
    return False


def _is_heading_like_chunk(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return True
    if len(lowered) <= 60 and lowered.startswith(("# ", "## ", "### ")):
        return True
    if lowered.startswith("#") and "$$" not in lowered and "=" not in lowered and len(lowered) < 120:
        return True
    return False


def _is_low_signal_chunk(*, text: str, lexical_score: int) -> bool:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return True
    if _FORMULA_VALUE_RE.search(normalized):
        return False
    token_candidates = [
        token.lower()
        for token in _ALPHA_TOKEN_RE.findall(normalized)
        if len(token) >= 3
    ]
    unique_tokens = set(token_candidates)
    if len(normalized) < 48 and lexical_score <= 1:
        return True
    if len(unique_tokens) <= 4 and lexical_score <= 1 and len(normalized) < 96:
        return True
    return False


def _extract_host(raw_url: str) -> str:
    normalized = str(raw_url or "").strip().lower()
    if not normalized:
        return ""
    try:
        parsed = urlparse(normalized)
    except Exception:
        return ""
    host = str(parsed.netloc or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def _placeholder_host_penalty(source_url: str) -> float:
    host = _extract_host(source_url)
    if not host:
        return 0.0
    if host in _PLACEHOLDER_HOSTS:
        return -8.0
    return 0.0


def _source_credibility_profile(*, source_type: str, source_url: str, source_name: str) -> tuple[str, float]:
    normalized_type = str(source_type or "").strip().lower()
    if normalized_type in {"file", "pdf"}:
        return "platform", 2.5
    if normalized_type == "image":
        return "medium", 0.0

    host = _extract_host(source_url or source_name)
    if not host:
        return "medium", 0.0
    if host in _PLACEHOLDER_HOSTS:
        return "low", -8.0
    if host in _LOW_CREDIBILITY_HOSTS:
        return "low", -3.5
    if host.endswith(".gov") or host.endswith(".edu"):
        return "high", 4.0
    if host.startswith(("docs.", "developer.", "developers.", "research.")):
        return "high", 3.0
    if any(
        host.endswith(suffix)
        for suffix in (
            "nature.com",
            "arxiv.org",
            "openml.org",
            "jmlr.org",
            "ibm.com",
            "microsoft.com",
            "google.com",
            "openai.com",
        )
    ):
        return "high", 2.5
    return "medium", 0.0


def _substantive_text_quality_boost(*, text: str) -> float:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return -6.0
    if _FORMULA_VALUE_RE.search(normalized):
        return 4.0
    if _is_low_value_chunk(normalized) or _is_heading_like_chunk(normalized):
        return -6.0
    sentences = [part.strip() for part in _SENTENCE_SPLIT_RE.split(normalized) if part.strip()]
    unique_tokens = {
        token.lower()
        for token in _ALPHA_TOKEN_RE.findall(normalized)
        if len(token) >= 3
    }
    boost = 0.0
    if len(normalized) >= 220:
        boost += 2.0
    elif len(normalized) < 80:
        boost -= 3.0
    if len(sentences) >= 2:
        boost += min(2.5, float(len(sentences) - 1) * 0.8)
    if len(unique_tokens) >= 18:
        boost += 1.5
    elif len(unique_tokens) <= 5:
        boost -= 2.5
    return boost


def _query_coverage_boost(*, text: str, query_terms: list[str]) -> float:
    normalized = str(text or "").lower()
    if not normalized or not query_terms:
        return 0.0
    distinct_terms = [term for term in dict.fromkeys(query_terms) if term]
    matched_terms = [term for term in distinct_terms if term in normalized]
    if not matched_terms:
        return -2.0
    coverage_ratio = float(len(matched_terms)) / float(max(1, len(distinct_terms)))
    boost = coverage_ratio * 6.0
    if len(matched_terms) >= 3:
        boost += 2.0
    if len(matched_terms) >= 5:
        boost += 1.5
    exact_phrase_hits = 0
    for left, right in zip(distinct_terms, distinct_terms[1:]):
        phrase = f"{left} {right}".strip()
        if phrase and phrase in normalized:
            exact_phrase_hits += 1
    if exact_phrase_hits:
        boost += min(3.0, float(exact_phrase_hits) * 1.2)
    return boost


def _technical_query_relevance_boost(*, query_lower: str, text: str, query_terms: list[str]) -> float:
    lowered = str(text or "").lower()
    if not lowered:
        return -8.0

    wants_technical = any(
        token in query_lower
        for token in (
            "derive",
            "equation",
            "formula",
            "balance",
            "stream",
            "vapor",
            "vapour",
            "liquid",
            "feed",
            "distillation",
            "column",
        )
    )
    if not wants_technical:
        return 0.0
    wants_derivation = any(
        token in query_lower
        for token in ("derive", "equation", "formula", "balance", "material balance", "component balance")
    )

    boost = 0.0
    if _is_low_value_chunk(lowered):
        boost -= 24.0
    if _is_heading_like_chunk(lowered):
        boost -= 10.0
    if len(lowered) < 90:
        boost -= 6.0

    formula_hits = len(_FORMULA_VALUE_RE.findall(text or ""))
    if formula_hits:
        boost += min(20.0, 8.0 + (formula_hits * 4.0))
    elif "$$" in text or re.search(r"[A-Za-z]\s*[=]\s*[^=]", text or ""):
        boost += 8.0

    stream_hits = sum(1 for term in _STREAM_TERMS if term in lowered)
    balance_hits = sum(1 for term in _BALANCE_TERMS if term in lowered)
    if stream_hits:
        boost += min(10.0, stream_hits * 2.5)
    if balance_hits:
        boost += min(12.0, balance_hits * 4.0)

    if wants_derivation:
        if formula_hits and balance_hits:
            boost += 22.0
        elif formula_hits:
            boost += 12.0
        elif balance_hits:
            boost += 8.0
        else:
            boost -= 14.0
        if stream_hits == 0:
            boost -= 3.0

    query_overlap = sum(1 for term in query_terms if term and term in lowered)
    if query_overlap >= 4:
        boost += min(10.0, float(query_overlap))

    if "figure " in lowered and formula_hits == 0:
        boost -= 10.0
    if "nomenclature" in lowered and formula_hits == 0:
        boost -= 12.0
    return boost


def load_recent_chunks_for_fast_qa(
    context: ApiContext,
    user_id: str,
    selected_payload: dict[str, list[Any]],
    query: str,
    max_sources: int = 48,
    max_chunks: int = 10,
) -> list[dict[str, Any]]:
    try:
        index = context.get_index(None)
        Source = index._resources["Source"]
        IndexTable = index._resources["Index"]
        doc_store = index._resources["DocStore"]
    except Exception:
        return []

    selected = selected_payload.get(str(index.id), ["all", [], user_id])
    mode = selected[0] if isinstance(selected, list) and selected else "all"
    selected_ids = selected[1] if isinstance(selected, list) and len(selected) > 1 else []
    selected_ids = [str(item) for item in selected_ids] if isinstance(selected_ids, list) else []

    source_ids: list[str] = []
    source_name_by_id: dict[str, str] = {}
    source_scan = max(1, int(max_sources))
    chunk_limit = max(1, int(max_chunks))
    with Session(engine) as session:
        if mode == "disabled":
            return []

        if mode == "select" and selected_ids:
            stmt = select(Source.id, Source.name).where(Source.id.in_(selected_ids))
            if index.config.get("private", False):
                stmt = stmt.where(Source.user == user_id)
            rows = session.execute(stmt).all()
            for row in rows:
                source_id = str(row[0])
                source_ids.append(source_id)
                source_name_by_id[source_id] = str(row[1])
        else:
            stmt = select(Source.id, Source.name).order_by(Source.date_created.desc())  # type: ignore[attr-defined]
            if index.config.get("private", False):
                stmt = stmt.where(Source.user == user_id)
            rows = session.execute(stmt.limit(source_scan)).all()
            for row in rows:
                source_id = str(row[0])
                source_ids.append(source_id)
                source_name_by_id[source_id] = str(row[1])

        if not source_ids:
            return []

        relation_limit = max(chunk_limit * 18, source_scan * 4)
        if mode == "select" and selected_ids:
            # For explicit file-group selection, preserve coverage across the full
            # selected set instead of letting a few hot documents dominate the scan.
            relation_limit = max(
                relation_limit,
                len(source_ids) * max(8, min(chunk_limit, 18)),
            )

        rel_stmt = (
            select(IndexTable.target_id, IndexTable.source_id)
            .where(
                IndexTable.relation_type == "document",
                IndexTable.source_id.in_(source_ids),
            )
            .limit(relation_limit)
        )
        rel_rows = session.execute(rel_stmt).all()

    if not rel_rows:
        return []

    target_to_source: dict[str, str] = {}
    target_ids: list[str] = []
    for target_id, source_id in rel_rows:
        target_key = str(target_id)
        source_key = str(source_id)
        target_to_source[target_key] = source_key
        target_ids.append(target_key)

    try:
        docs = doc_store.get(target_ids)
    except Exception:
        return []

    query_terms = _extract_query_terms(query, max_terms=20)
    query_lower = str(query or "").lower()
    broad_query = len(query_terms) <= 2
    target_hosts = set(_extract_target_hosts(query))

    scored_text: list[dict[str, Any]] = []
    image_by_source: dict[str, dict[str, Any]] = {}
    for doc in docs or []:
        doc_id = str(getattr(doc, "doc_id", "") or "")
        if not doc_id:
            continue

        metadata = getattr(doc, "metadata", {}) or {}
        doc_type = str(metadata.get("type", "") or "")
        page_label = str(metadata.get("page_label", "") or "")
        highlight_boxes = _extract_highlight_boxes(metadata)
        evidence_units = _extract_evidence_units(metadata)

        # Fallback: if no boxes from index metadata, try precomputed page cache
        if not highlight_boxes and page_label:
            try:
                from api.services.upload.pdf_highlight_locator import _extract_page_units
                file_path_meta = metadata.get("file_path") or metadata.get("source_path") or ""
                if file_path_meta:
                    from pathlib import Path
                    cached = _extract_page_units(Path(str(file_path_meta)), max(1, int(page_label) if page_label.isdigit() else 1))
                    cached_units = cached.get("units") or []
                    if cached_units:
                        # Extract boxes from cached page units
                        text_snippet = str(metadata.get("text", "") or "")[:100]
                        for cu in cached_units:
                            cu_text = str(cu.get("text", "") or "")
                            if text_snippet and text_snippet[:40].lower() in cu_text.lower():
                                cu_boxes = cu.get("highlight_boxes") or []
                                if cu_boxes:
                                    highlight_boxes = cu_boxes[:6]
                                    break
            except Exception:
                pass  # Best-effort fallback — don't block retrieval

        source_id = target_to_source.get(doc_id, "")
        source_name = str(metadata.get("file_name", "") or "") or source_name_by_id.get(
            source_id,
            "Indexed file",
        )
        source_name_lower = source_name.lower()
        source_url = str(
            metadata.get("source_url")
            or metadata.get("page_url")
            or (source_name if source_name_lower.startswith(("http://", "https://")) else "")
            or ""
        ).strip()
        source_key = source_id or f"name:{source_name}"
        source_type = _source_kind(
            source_name=source_name,
            source_url=source_url,
            metadata=metadata,
        )
        credibility_tier, credibility_boost = _source_credibility_profile(
            source_type=source_type,
            source_url=source_url,
            source_name=source_name,
        )
        target_host_match = _matches_target_hosts(
            source_name=source_name,
            metadata=metadata,
            target_hosts=target_hosts,
        )

        image_origin = metadata.get("image_origin")
        if (
            isinstance(image_origin, str)
            and image_origin.startswith("data:image/")
            and (not target_hosts or target_host_match)
        ):
            existing = image_by_source.get(source_key)
            if existing is None or (
                doc_type == "thumbnail" and existing.get("doc_type") != "thumbnail"
            ):
                image_by_source[source_key] = {
                    "source_id": source_id,
                    "source_name": source_name,
                    "source_url": source_url,
                    "doc_type": doc_type,
                    "page_label": page_label,
                    "image_origin": image_origin,
                    "target_host_match": target_host_match,
                }

        raw_text = str(getattr(doc, "text", "") or "")
        text = re.sub(r"\s+", " ", raw_text).strip()
        if not text:
            continue
        if doc_type == "thumbnail" and len(text) <= 20:
            continue

        lowered = text.lower()

        # Lexical score: keyword frequency
        lexical_score = sum(lowered.count(term) for term in query_terms)
        lexical_score += 4 * sum(source_name_lower.count(term) for term in query_terms)

        # Semantic scores from index metadata (computed during indexing)
        vector_score = _to_float(metadata.get("vector_score")) or _to_float(metadata.get("score")) or 0.0
        rerank_score = _to_float(metadata.get("rerank_score")) or 0.0

        # Hybrid score: lexical (0.5) + vector (0.3) + rerank (0.2)
        # Normalize lexical to 0-1 range (cap at 25 keyword hits)
        lexical_normalized = min(1.0, lexical_score / 25.0) if lexical_score > 0 else 0.0
        score = (
            lexical_normalized * 12.5  # Scale back to original score range (~0-12)
            + vector_score * 8.0       # Vector similarity contributes significantly
            + rerank_score * 5.0       # Reranker contributes if available
        )

        # Formula boost: if user asks a calculation question and chunk contains math
        _has_math = bool(
            "$" in text or "\\frac" in text or "\\sum" in text
            or any(c in text for c in "∑∫√∂∇≈≠≤≥±×÷")
            or re.search(r"[a-zA-Z]\s*[=]\s*[^=]", text)
        )
        _wants_calc = any(t in query_lower for t in ("calculate", "compute", "formula", "equation", "solve", "derive"))
        if _has_math and _wants_calc:
            score += 12  # Strong boost: user wants calculation, chunk has formulas
        elif _has_math:
            score += 3   # Mild boost: formulas are always high-value content

        score += _technical_query_relevance_boost(
            query_lower=query_lower,
            text=text,
            query_terms=query_terms,
        )

        # Heuristic boosts (preserved from original)
        if doc_type == "ocr":
            score += 4
        elif doc_type == "table":
            score += 2
        elif doc_type == "image":
            score += 2
        if broad_query:
            score += min(len(text) // 80, 10)
        if "pdf" in query_terms and source_name_lower.endswith(".pdf"):
            score += 8
        if source_name_lower.startswith("http://") or source_name_lower.startswith("https://"):
            score -= 1
        if source_type in {"file", "pdf"}:
            score += 2.0
        elif source_type == "web":
            score += 0.5
        score += _substantive_text_quality_boost(text=text)
        score += _query_coverage_boost(text=text, query_terms=query_terms)
        score += credibility_boost
        if _is_low_signal_chunk(text=text, lexical_score=lexical_score):
            score -= 10.0
        if target_hosts:
            if target_host_match:
                score += 42
            else:
                score -= 18

        scored_text.append(
            {
                "score": score,
                "source_id": source_id,
                "file_id": source_id,
                "source_key": source_key,
                "source_name": source_name,
                "source_url": source_url,
                "source_type": source_type,
                "credibility_tier": credibility_tier,
                "text": text[:1200],
                "lexical_score": lexical_score,
                "doc_type": doc_type,
                "page_label": page_label,
                "image_origin": image_by_source.get(source_key, {}).get("image_origin"),
                "highlight_boxes": highlight_boxes,
                "evidence_units": evidence_units,
                "unit_id": str(metadata.get("unit_id", "") or "").strip(),
                "char_start": metadata.get("char_start"),
                "char_end": metadata.get("char_end"),
                "match_quality": str(metadata.get("match_quality", "") or "").strip() or "estimated",
                "llm_trulens_score": _to_float(metadata.get("llm_trulens_score")) or 0.0,
                "rerank_score": _to_float(metadata.get("rerank_score")) or 0.0,
                "vector_score": (
                    _to_float(metadata.get("vector_score"))
                    or _to_float(metadata.get("score"))
                    or 0.0
                ),
                "is_exact_match": bool(metadata.get("is_exact_match", False)),
                "target_host_match": target_host_match,
            }
        )

    if not scored_text and not image_by_source:
        return []

    # Deduplicate near-identical chunks — include source + page so distinct
    # pages of the same document are never collapsed even when their opening
    # text is similar (common in textbooks that repeat definitions).
    _dedup_seen: set[str] = set()
    _deduped: list[dict[str, Any]] = []
    for item in scored_text:
        source_key = str(item.get("source_key", "") or "")
        page_label = str(item.get("page_label", "") or "")
        text_fingerprint = "".join(str(item.get("text", ""))[:200].lower().split())
        dedup_key = f"{source_key}|{page_label}|{text_fingerprint}"
        if dedup_key in _dedup_seen:
            continue
        _dedup_seen.add(dedup_key)
        _deduped.append(item)
    scored_text = _deduped

    if target_hosts:
        host_matched_text = [row for row in scored_text if bool(row.get("target_host_match"))]
        if host_matched_text:
            scored_text = host_matched_text
            image_by_source = {
                key: value
                for key, value in image_by_source.items()
                if bool(value.get("target_host_match"))
            }

    for item in scored_text:
        if item.get("image_origin"):
            continue
        source_key = str(item.get("source_key", ""))
        item["image_origin"] = image_by_source.get(source_key, {}).get("image_origin")

    if mode == "select" and selected_ids:
        use_broad_selected_context = (
            len(selected_ids) == 1
            and not target_hosts
            and len(query_terms) <= 2
        )
        if use_broad_selected_context:
            by_page: dict[str, list[dict[str, Any]]] = {}
            for item in scored_text:
                page_key = str(item.get("page_label", "") or "")
                by_page.setdefault(page_key, []).append(item)
            selected_text = []
            for page_key in sorted(by_page.keys(), key=_page_label_sort_key):
                rows = by_page.get(page_key, [])
                rows.sort(
                    key=lambda item: (
                        -int(item.get("score", 0) or 0),
                        -len(str(item.get("text", ""))),
                    )
                )
                if rows:
                    selected_text.append(rows[0])
                if len(selected_text) >= chunk_limit:
                    break
            if len(selected_text) < chunk_limit:
                seen_keys = {
                    (
                        str(item.get("source_key", "")),
                        str(item.get("page_label", "")),
                        str(item.get("unit_id", "")),
                        str(item.get("text", "")),
                    )
                    for item in selected_text
                }
                for item in _ranked_chunk_selection(scored_text, chunk_limit=chunk_limit * 2):
                    key = (
                        str(item.get("source_key", "")),
                        str(item.get("page_label", "")),
                        str(item.get("unit_id", "")),
                        str(item.get("text", "")),
                    )
                    if key in seen_keys:
                        continue
                    selected_text.append(item)
                    seen_keys.add(key)
                    if len(selected_text) >= chunk_limit:
                        break
        else:
            effective_chunk_limit = max(chunk_limit, min(len(selected_ids), 24))
            by_source: dict[str, list[dict[str, Any]]] = {}
            for item in scored_text:
                source_key = str(item.get("source_key", "") or "")
                if not source_key:
                    continue
                by_source.setdefault(source_key, []).append(item)
            mandatory_rows: list[dict[str, Any]] = []
            for source_key in selected_ids:
                rows = by_source.get(str(source_key), [])
                if not rows:
                    continue
                rows.sort(
                    key=lambda item: (
                        -int(item.get("score", 0) or 0),
                        _page_label_sort_key(item.get("page_label")),
                    )
                )
                mandatory_rows.append(rows[0])
            mandatory_keys = {
                (
                    str(item.get("source_key", "")),
                    str(item.get("page_label", "")),
                    str(item.get("unit_id", "")),
                    str(item.get("text", "")),
                )
                for item in mandatory_rows
            }
            ranked_rows = _ranked_chunk_selection(scored_text, chunk_limit=effective_chunk_limit * 2)
            selected_text = list(mandatory_rows)
            for item in ranked_rows:
                key = (
                    str(item.get("source_key", "")),
                    str(item.get("page_label", "")),
                    str(item.get("unit_id", "")),
                    str(item.get("text", "")),
                )
                if key in mandatory_keys:
                    continue
                selected_text.append(item)
                if len(selected_text) >= effective_chunk_limit:
                    break
    else:
        selected_text = _ranked_chunk_selection(scored_text, chunk_limit=chunk_limit)

    selected_sources = {str(item.get("source_key", "")) for item in selected_text}
    for source_key, image_payload in image_by_source.items():
        if source_key in selected_sources:
            continue
        selected_text.append(
            {
                "score": -1,
                "source_id": str(image_payload.get("source_id", "") or ""),
                "file_id": str(image_payload.get("source_id", "") or ""),
                "source_key": source_key,
                "source_name": str(image_payload.get("source_name", "") or "Indexed file"),
                "source_url": str(image_payload.get("source_url", "") or ""),
                "source_type": "image",
                "text": "Image evidence available for visual analysis.",
                "doc_type": str(image_payload.get("doc_type", "") or "thumbnail"),
                "page_label": str(image_payload.get("page_label", "") or ""),
                "image_origin": image_payload.get("image_origin"),
                "highlight_boxes": [],
                "unit_id": "",
                "char_start": 0,
                "char_end": 0,
                "match_quality": "estimated",
            }
        )

    return selected_text
