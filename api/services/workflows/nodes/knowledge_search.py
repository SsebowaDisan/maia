"""Knowledge Search node — retrieves documents from the RAG index.

step_config:
    query_key: str        — input key containing the search query
    top_k: int            — max results to return (default 5, max 20)
    retrieval_mode: str   — "hybrid" (default), "vector", or "text"
    include_metadata: bool — include source file names and page numbers (default true)
    score_threshold: float — minimum relevance score 0.0-1.0 (default 0.0)

Returns a dict with:
    results: list[dict]  — matched passages with text, score, source metadata
    count: int           — number of results returned
    query: str           — the resolved query string
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from decouple import config as decouple_config
from api.schemas.workflow_definition import WorkflowStep
from api.services.workflows.nodes import register

logger = logging.getLogger(__name__)

# New RAG pipeline (feature flag)
_USE_NEW_RAG = decouple_config("MAIA_USE_NEW_RAG", default="false", cast=str).lower() == "true"

_MAX_TOP_K = 20
_DEFAULT_TOP_K = 5


@register("knowledge_search")
def handle_knowledge_search(
    step: WorkflowStep,
    inputs: dict[str, Any],
    on_event: Optional[Callable] = None,
) -> dict[str, Any]:
    cfg = step.step_config
    query_key = str(cfg.get("query_key", "query"))
    top_k = min(int(cfg.get("top_k", _DEFAULT_TOP_K)), _MAX_TOP_K)
    retrieval_mode = str(cfg.get("retrieval_mode", "hybrid"))
    include_metadata = bool(cfg.get("include_metadata", True))
    score_threshold = float(cfg.get("score_threshold", 0.0))

    query = str(inputs.get(query_key, "")).strip()
    if not query:
        return {"results": [], "count": 0, "query": "", "error": "Empty query"}

    if on_event:
        on_event({"event_type": "knowledge_search_started", "query": query[:200], "top_k": top_k})

    # Novelty check — warn if topic is already well-covered
    novelty = _check_query_novelty(query)
    if novelty and on_event:
        on_event({"event_type": "knowledge_search_novelty", **novelty})

    if _USE_NEW_RAG:
        import asyncio
        from api.services.rag.bridge import run_rag_query_bridge
        try:
            rag_result = asyncio.get_event_loop().run_until_complete(
                run_rag_query_bridge(question=query, source_ids=[])
            )
            # Extract chunks from result for workflow
            chunks = rag_result.get("chunks") or rag_result.get("results") or []
            if chunks:
                formatted = _format_results(chunks, include_metadata)
                if on_event:
                    on_event({"event_type": "knowledge_search_completed", "count": len(formatted)})
                return {"results": formatted, "count": len(formatted), "query": query, "novelty": novelty or {}}
        except Exception as exc:
            logger.warning("New RAG pipeline failed in knowledge_search, falling back: %s", exc)
        # Fall through to old retrieval

    try:
        results = _run_retrieval(query, top_k, retrieval_mode, score_threshold)
    except Exception as exc:
        logger.warning("Knowledge search failed: %s", exc, exc_info=True)
        return {"results": [], "count": 0, "query": query, "error": str(exc)[:300]}

    formatted = _format_results(results, include_metadata)

    if on_event:
        on_event({"event_type": "knowledge_search_completed", "count": len(formatted)})

    return {"results": formatted, "count": len(formatted), "query": query, "novelty": novelty or {}}


def _run_retrieval(
    query: str,
    top_k: int,
    retrieval_mode: str,
    score_threshold: float,
) -> list[dict[str, Any]]:
    """Execute retrieval against the file index via get_retriever_pipelines."""
    try:
        from api.context import get_context
        ctx = get_context()
    except Exception:
        return _fallback_retrieval(ctx=None, query=query, top_k=top_k)

    try:
        index = ctx.get_index()
    except Exception:
        return _fallback_retrieval(ctx=ctx, query=query, top_k=top_k)

    # Build retrieval settings matching the index's expected format
    prefix = f"index.options.{index.id}."
    settings = {
        f"{prefix}retrieval_mode": retrieval_mode,
        f"{prefix}num_retrieval": top_k,
    }

    try:
        retrievers = index.get_retriever_pipelines(
            settings=settings,
            user_id=0,
            selected=None,
        )
    except Exception:
        return _fallback_retrieval(ctx=ctx, query=query, top_k=top_k)

    if not retrievers:
        return _fallback_retrieval(ctx=ctx, query=query, top_k=top_k)

    # Run all retriever pipelines and merge results
    all_docs: list[Any] = []
    for retriever in retrievers:
        try:
            docs = retriever(text=query)
            if docs:
                all_docs.extend(docs)
        except Exception as exc:
            logger.debug("Retriever %s failed: %s", type(retriever).__name__, exc)

    if not all_docs:
        return _fallback_retrieval(ctx=ctx, query=query, top_k=top_k)

    # Deduplicate by text content, keep highest score
    seen: dict[str, dict[str, Any]] = {}
    for doc in all_docs:
        text = str(getattr(doc, "text", "") or getattr(doc, "content", ""))
        score = float(getattr(doc, "score", 0.0) or 0.0)
        metadata = getattr(doc, "metadata", {}) or {}
        key = text[:200]
        if key not in seen or score > seen[key].get("score", 0):
            seen[key] = {
                "text": text,
                "score": round(score, 4),
                "doc_id": str(getattr(doc, "doc_id", "") or ""),
                "source": str(metadata.get("file_name", "") or ""),
                "page": metadata.get("page_label"),
            }

    results = sorted(seen.values(), key=lambda r: r["score"], reverse=True)

    if score_threshold > 0:
        results = [r for r in results if r["score"] >= score_threshold]

    return results[:top_k]


def _fallback_retrieval(
    *,
    ctx: Any,
    query: str,
    top_k: int,
) -> list[dict[str, Any]]:
    """Fallback using fast_qa_retrieval when the pipeline isn't available."""
    try:
        from api.services.chat.fast_qa_retrieval import load_recent_chunks_for_fast_qa

        if ctx is None:
            from api.context import get_context
            ctx = get_context()

        chunks = load_recent_chunks_for_fast_qa(
            context=ctx,
            user_id="system",
            selected_payload={},
            query=query,
            max_sources=48,
            max_chunks=top_k,
        )
        return [
            {
                "text": str(c.get("text", "")),
                "score": round(float(c.get("score", 0.0)), 4),
                "doc_id": str(c.get("doc_id", "")),
                "source": str(c.get("source", "")),
                "page": c.get("page_label"),
            }
            for c in (chunks or [])[:top_k]
        ]
    except Exception as exc:
        logger.debug("Fallback retrieval failed: %s", exc)
        return []


def _format_results(
    results: list[dict[str, Any]],
    include_metadata: bool,
) -> list[dict[str, Any]]:
    """Format results for downstream consumption."""
    formatted: list[dict[str, Any]] = []
    for r in results:
        entry: dict[str, Any] = {"text": r.get("text", ""), "score": r.get("score", 0.0)}
        if include_metadata:
            if r.get("source"):
                entry["source"] = r["source"]
            if r.get("page") is not None:
                entry["page"] = r["page"]
            if r.get("doc_id"):
                entry["doc_id"] = r["doc_id"]
        formatted.append(entry)
    return formatted


def _check_query_novelty(query: str) -> dict[str, Any] | None:
    """Run novelty check against RAG index. Returns None if unavailable."""
    try:
        from api.services.agent.reasoning.novelty_check import check_novelty

        def _rag_search(q: str, top_k: int) -> list[dict[str, Any]]:
            results = _run_retrieval(q, top_k, "hybrid", 0.0)
            return results

        return check_novelty(topic=query, rag_search=_rag_search, top_k=5)
    except Exception:
        return None
