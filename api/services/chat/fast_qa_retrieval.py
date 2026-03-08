from __future__ import annotations

import re
from typing import Any

from sqlmodel import Session, select

from ktem.db.models import engine

from api.context import ApiContext

from .fast_qa_retrieval_helpers import (
    _extract_highlight_boxes,
    _extract_query_terms,
    _extract_target_hosts,
    _matches_target_hosts,
    _page_label_sort_key,
    _ranked_chunk_selection,
    _to_float,
)


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

        rel_stmt = (
            select(IndexTable.target_id, IndexTable.source_id)
            .where(
                IndexTable.relation_type == "document",
                IndexTable.source_id.in_(source_ids),
            )
            .limit(max(chunk_limit * 18, source_scan * 4))
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
        score = sum(lowered.count(term) for term in query_terms)
        score += 4 * sum(source_name_lower.count(term) for term in query_terms)
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
        if target_hosts:
            if target_host_match:
                score += 42
            else:
                score -= 18

        scored_text.append(
            {
                "score": score,
                "source_id": source_id,
                "source_key": source_key,
                "source_name": source_name,
                "source_url": source_url,
                "text": text[:1200],
                "doc_type": doc_type,
                "page_label": page_label,
                "image_origin": image_by_source.get(source_key, {}).get("image_origin"),
                "highlight_boxes": highlight_boxes,
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
            scored_text.sort(
                key=lambda item: (
                    item.get("source_name", ""),
                    _page_label_sort_key(item.get("page_label")),
                    -len(str(item.get("text", ""))),
                )
            )
            selected_text = scored_text[: chunk_limit * 2]
        else:
            selected_text = _ranked_chunk_selection(scored_text, chunk_limit=chunk_limit)
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
                "source_key": source_key,
                "source_name": str(image_payload.get("source_name", "") or "Indexed file"),
                "source_url": str(image_payload.get("source_url", "") or ""),
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
