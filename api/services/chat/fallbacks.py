from __future__ import annotations

import re

from sqlmodel import Session, select

from ktem.db.models import engine

from api.context import ApiContext

from .pipeline import default_llm_name, llm_name_uses_placeholder_key


def fallback_answer_from_exception(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "api key" in lowered or "api_key_invalid" in lowered:
        return (
            "LLM is not configured with a valid API key yet. "
            "File indexing works, but chat generation is currently using fallback mode. "
            "Set a valid LLM key in settings to enable full AI answers."
        )
    if llm_name_uses_placeholder_key(default_llm_name()):
        return (
            "LLM is not configured with a valid API key yet. "
            "File indexing works, but chat generation is currently using fallback mode. "
            "Set a valid LLM key in settings to enable full AI answers."
        )

    return (
        "The chat model is currently unavailable. "
        "Please try again shortly or configure a valid LLM in settings."
    )


def build_extractive_timeout_answer(
    context: ApiContext,
    user_id: str,
) -> tuple[str, str]:
    """Return a local extractive fallback answer when full generation times out."""
    try:
        index = context.get_index(None)
        Source = index._resources["Source"]
        IndexTable = index._resources["Index"]
        doc_store = index._resources["DocStore"]
    except Exception:
        return (
            "The request timed out, and no local fallback context was available.",
            "",
        )

    with Session(engine) as session:
        stmt = select(Source).order_by(Source.date_created.desc())  # type: ignore[attr-defined]
        if index.config.get("private", False):
            stmt = stmt.where(Source.user == user_id)
        source_row = session.execute(stmt).first()
        if not source_row:
            return (
                "The request timed out. No indexed files were found for fallback answering.",
                "",
            )
        source = source_row[0]
        source_id = source.id
        source_name = str(source.name)

        doc_id_stmt = (
            select(IndexTable.target_id)
            .where(
                IndexTable.source_id == source_id,
                IndexTable.relation_type == "document",
            )
            .limit(8)
        )
        doc_ids = [str(row[0]) for row in session.execute(doc_id_stmt).all()]

    if not doc_ids:
        return (
            f"The request timed out. I found file '{source_name}', but no indexed text chunks were available.",
            "",
        )

    try:
        docs = doc_store.get(doc_ids)
    except Exception:
        docs = []

    texts: list[str] = []
    for doc in docs or []:
        text = getattr(doc, "text", "") or ""
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            texts.append(text)
        if len(" ".join(texts)) >= 1200:
            break

    if not texts:
        return (
            f"The request timed out. I found file '{source_name}', but could not extract readable text for fallback answering.",
            "",
        )

    snippet = " ".join(texts)[:1200].strip()
    answer = (
        f"I could not finish full model generation in time. "
        f"Based on the latest indexed file '{source_name}', the content indicates: {snippet}"
    )
    info_html = (
        "<details class='evidence' id='evidence-1' open>"
        "<summary><i>Fallback retrieval</i></summary>"
        f"<div><b>Source:</b> [1] {source_name}</div>"
        f"<div><b>Extract:</b> {snippet}</div>"
        "</details>"
    )
    return answer, info_html
