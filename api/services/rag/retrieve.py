"""RAG Pipeline Phase 9: Retrieve — find evidence chunks for a query.

Implements hybrid retrieval: vector similarity (via the index module) combined
with keyword matching (BM25-style). Results are merged using the configured
hybrid_weight and returned with their CitationAnchors attached.

The RetrievalScope dataclass controls which chunks are searched (by group,
specific sources, or owner). This enforces data isolation.
"""

from __future__ import annotations

import logging
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field

import httpx

from api.services.rag.types import (
    Chunk,
    RAGConfig,
    RetrievedEvidence,
)
from api.services.rag.index import search as vector_search, _get_collection
from api.services.rag.citation_prep import get_anchors

logger = logging.getLogger(__name__)

# ── Retrieval Scope ─────────────────────────────────────────────────────────


@dataclass
class RetrievalScope:
    """Controls which chunks are searched. Enforces data isolation."""
    group_id: str = ""
    source_ids: list[str] = field(default_factory=list)
    owner_id: str = ""


# ── Embedding ───────────────────────────────────────────────────────────────

async def _get_embedding(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """Call embedding API. Falls back to zero vector if embedding provider is unavailable."""
    api_key = os.environ.get("MAIA_RAG_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        logger.warning("No API key set; returning zero vector for keyword-only retrieval")
        return [0.0] * 1536

    embed_url = os.environ.get("MAIA_RAG_EMBEDDING_BASE_URL", os.environ.get("OPENAI_BASE_URL", os.environ.get("OPENAI_API_BASE", "")))
    if not embed_url:
        return [0.0] * 1536

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                embed_url + "/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": model, "input": text},
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
    except Exception as exc:
        logger.warning("Embedding API failed (%s); using keyword-only retrieval", exc)
        return [0.0] * 1536


# ── BM25-style keyword matching ────────────────────────────────────────────

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "about", "between",
    "through", "after", "before", "above", "below", "and", "or", "but",
    "not", "if", "then", "than", "that", "this", "it", "its", "what",
    "which", "who", "whom", "how", "when", "where", "why",
})


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenize, remove stop words and short tokens."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    avg_dl: float,
    doc_count: int,
    df: dict[str, int],
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """Compute BM25 score for a single document against a query."""
    if not query_tokens or not doc_tokens:
        return 0.0

    dl = len(doc_tokens)
    doc_tf = Counter(doc_tokens)
    score = 0.0

    for qt in query_tokens:
        if qt not in doc_tf:
            continue
        tf = doc_tf[qt]
        n = df.get(qt, 0)
        # IDF with smoothing
        idf = math.log((doc_count - n + 0.5) / (n + 0.5) + 1.0)
        # TF normalization
        tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(avg_dl, 1.0)))
        score += idf * tf_norm

    return score


def _keyword_search(
    query: str,
    filters: dict[str, str],
    source_ids_filter: list[str] | None,
    top_k: int,
) -> list[tuple[Chunk, float]]:
    """BM25-style keyword search over the in-memory store.

    Returns (Chunk, normalized_score) tuples sorted by descending score.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # Gather candidate chunks from ChromaDB matching filters
    from api.services.rag.index import _build_where_clause

    where = _build_where_clause(filters) if filters else None
    collection = _get_collection()

    results = collection.get(
        where=where,
        include=["documents", "metadatas"],
        limit=top_k if top_k > 0 else 10000,
    )

    candidates: list[tuple[str, Chunk, list[str]]] = []
    for i, doc_id in enumerate(results.get("ids", [])):
        text = results["documents"][i] if results.get("documents") else ""
        meta = results["metadatas"][i] if results.get("metadatas") else {}

        if source_ids_filter and meta.get("source_id", "") not in source_ids_filter:
            continue

        import json as _json
        heading_path = []
        try:
            heading_path = _json.loads(meta.get("heading_path", "[]"))
        except Exception:
            pass

        chunk = Chunk(
            id=doc_id,
            source_id=meta.get("source_id", ""),
            text=text,
            page_start=int(meta.get("page_start", 0)),
            page_end=int(meta.get("page_end", 0)),
            char_start=int(meta.get("char_start", 0)),
            char_end=int(meta.get("char_end", 0)),
            heading_path=heading_path,
            chunk_type=meta.get("chunk_type", "text"),
            group_id=meta.get("group_id", ""),
            owner_id=meta.get("owner_id", ""),
            filename=meta.get("filename", ""),
            source_type=meta.get("source_type", ""),
        )
        doc_tokens = _tokenize(text)
        candidates.append((doc_id, chunk, doc_tokens))

    if not candidates:
        return []

    # Compute document frequencies
    doc_count = len(candidates)
    df: dict[str, int] = Counter()
    total_tokens = 0
    for _, _, tokens in candidates:
        total_tokens += len(tokens)
        for t in set(tokens):
            df[t] += 1
    avg_dl = total_tokens / max(doc_count, 1)

    # Score each candidate
    scored: list[tuple[Chunk, float]] = []
    for _, chunk, tokens in candidates:
        score = _bm25_score(query_tokens, tokens, avg_dl, doc_count, df)
        if score > 0:
            scored.append((chunk, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    # Normalize scores to 0-1 range
    if scored:
        max_score = scored[0][1]
        if max_score > 0:
            scored = [(c, s / max_score) for c, s in scored]

    return scored[:top_k]


# ── Public API ──────────────────────────────────────────────────────────────

async def retrieve(
    query: str,
    config: RAGConfig,
    scope: RetrievalScope,
) -> list[RetrievedEvidence]:
    """Phase 9: Retrieve evidence chunks for a query using hybrid search.

    Combines vector similarity search with BM25 keyword matching. The
    hybrid_weight config parameter controls the blend (1.0 = pure vector,
    0.0 = pure keyword).

    Each result has its CitationAnchors attached from the citation_prep store.

    Parameters
    ----------
    query : the user's natural language question
    config : pipeline configuration (top_k, hybrid_weight, embedding_model)
    scope : data isolation filters (group_id, source_ids, owner_id)

    Returns
    -------
    List of RetrievedEvidence sorted by score, length up to (config.top_k or 10000).
    """
    # Build metadata filters from scope
    filters: dict[str, str] = {}
    if scope.group_id:
        filters["group_id"] = scope.group_id
    if scope.owner_id:
        filters["owner_id"] = scope.owner_id

    # Source IDs are handled separately since index.search only supports
    # single-value filters, not list membership
    source_ids_filter = scope.source_ids if scope.source_ids else None

    # ── Vector search ───────────────────────────────────────────────────
    query_embedding = await _get_embedding(query, config.embedding_model)

    vector_results: list[tuple[Chunk, float]] = []
    if source_ids_filter:
        # Run a search per source_id and merge (index only supports single-value)
        for sid in source_ids_filter:
            sid_filters = {**filters, "source_id": sid}
            hits = vector_search(query_embedding, top_k=(config.top_k or 10000), filters=sid_filters)
            vector_results.extend(hits)
        # Re-sort and truncate
        vector_results.sort(key=lambda x: x[1], reverse=True)
        vector_results = vector_results[: (config.top_k or 10000)]
    else:
        vector_results = vector_search(query_embedding, top_k=(config.top_k or 10000), filters=filters)

    # ── Keyword search ──────────────────────────────────────────────────
    keyword_results = _keyword_search(query, filters, source_ids_filter, (config.top_k or 10000))

    # ── Hybrid merge ────────────────────────────────────────────────────
    # Build chunk_id → scores maps
    vector_scores: dict[str, tuple[Chunk, float]] = {}
    for chunk, score in vector_results:
        vector_scores[chunk.id] = (chunk, score)

    keyword_scores: dict[str, tuple[Chunk, float]] = {}
    for chunk, score in keyword_results:
        keyword_scores[chunk.id] = (chunk, score)

    # All unique chunk IDs
    all_ids = set(vector_scores.keys()) | set(keyword_scores.keys())

    merged: list[tuple[Chunk, float, str]] = []
    w_vec = config.hybrid_weight
    w_key = 1.0 - w_vec

    for cid in all_ids:
        v_entry = vector_scores.get(cid)
        k_entry = keyword_scores.get(cid)

        v_score = v_entry[1] if v_entry else 0.0
        k_score = k_entry[1] if k_entry else 0.0

        combined = w_vec * v_score + w_key * k_score

        # Pick the chunk object from whichever search found it
        chunk = v_entry[0] if v_entry else k_entry[0]  # type: ignore[index]

        # Determine match type
        if v_entry and k_entry:
            match_type = "hybrid"
        elif v_entry:
            match_type = "vector"
        else:
            match_type = "keyword"

        merged.append((chunk, combined, match_type))

    merged.sort(key=lambda x: x[1], reverse=True)
    merged = merged[: (config.top_k or 10000)]

    # ── Build RetrievedEvidence with anchors ────────────────────────────
    results: list[RetrievedEvidence] = []
    for chunk, score, match_type in merged:
        anchors = get_anchors(chunk.id)
        results.append(
            RetrievedEvidence(
                chunk=chunk,
                score=score,
                match_type=match_type,
                anchors=anchors,
            )
        )

    logger.info(
        "Retrieved %d evidence chunks for query (vector=%d, keyword=%d, merged=%d)",
        len(results),
        len(vector_results),
        len(keyword_results),
        len(merged),
    )

    return results
