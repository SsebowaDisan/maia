"""RAG Pipeline Phase 6: Embed — vectorize chunks via OpenAI embedding API."""

from __future__ import annotations

# Load .env before reading os.environ
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    pass

import logging
import os
from dataclasses import fields

import httpx

from api.services.rag.types import Chunk, EmbeddedChunk, RAGConfig

logger = logging.getLogger(__name__)

_OPENAI_EMBED_URL = os.environ.get("MAIA_RAG_EMBEDDING_BASE_URL", "https://api.openai.com/v1") + "/embeddings"
_BATCH_SIZE = 100
_MAX_RETRIES = 1  # Only 1 retry — don't waste time on auth errors


def _chunk_to_embedded(chunk: Chunk, embedding: list[float], model: str) -> EmbeddedChunk:
    """Promote a Chunk to an EmbeddedChunk, copying all fields."""
    # Copy every Chunk field into kwargs for EmbeddedChunk
    chunk_fields = {f.name: getattr(chunk, f.name) for f in fields(Chunk)}
    return EmbeddedChunk(
        **chunk_fields,
        embedding=embedding,
        embedding_model=model,
        embedding_version="1",
    )


async def _call_openai_embeddings(
    texts: list[str],
    model: str,
    api_key: str,
    dimensions: int,
) -> list[list[float]]:
    """Call OpenAI embeddings endpoint for a batch of texts."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict = {
        "input": texts,
        "model": model,
    }
    # text-embedding-3-* models support the dimensions parameter
    if "embedding-3" in model and dimensions and dimensions > 0:
        payload["dimensions"] = dimensions

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(_OPENAI_EMBED_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    # OpenAI returns embeddings sorted by index
    embeddings = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
    return embeddings


# ── Public API ──────────────────────────────────────────────────────────────


async def embed_chunks(
    chunks: list[Chunk],
    config: RAGConfig,
) -> list[EmbeddedChunk]:
    """Embed all chunks via OpenAI text-embedding API.

    - Batches in groups of 100 for efficiency
    - Retries up to 2x per batch on transient failure
    - Skips chunks on persistent failure (logs warning)
    """
    if not chunks:
        return []

    api_key = os.environ.get("MAIA_RAG_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("No API key set — using empty embeddings (keyword-only retrieval)")
        return [_chunk_to_embedded(c, [], config.embedding_model or "none") for c in chunks]

    model = config.embedding_model
    dimensions = config.embedding_dimensions
    results: list[EmbeddedChunk] = []

    # Process in batches
    for batch_start in range(0, len(chunks), _BATCH_SIZE):
        batch = chunks[batch_start : batch_start + _BATCH_SIZE]
        texts = [c.text for c in batch]

        embeddings: list[list[float]] | None = None
        last_error: Exception | None = None

        for attempt in range(_MAX_RETRIES + 1):
            try:
                embeddings = await _call_openai_embeddings(texts, model, api_key, dimensions)
                break
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code if exc.response else 0
                logger.warning(
                    "Embedding batch %d–%d attempt %d failed (HTTP %d): %s",
                    batch_start, batch_start + len(batch), attempt + 1, status_code, exc,
                )
                # Don't retry on auth/permission errors — they'll never succeed
                if status_code in (401, 403, 404, 422):
                    break
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning(
                    "Embedding batch %d–%d attempt %d failed: %s",
                    batch_start, batch_start + len(batch), attempt + 1, exc,
                )

        if embeddings is None:
            # Persistent failure — use empty vectors so keyword search still works
            logger.warning(
                "Embedding batch %d–%d failed after %d retries; using empty vectors for keyword-only retrieval: %s",
                batch_start,
                batch_start + len(batch),
                _MAX_RETRIES + 1,
                last_error,
            )
            embeddings = [[] for _ in batch]

        for chunk, emb in zip(batch, embeddings):
            results.append(_chunk_to_embedded(chunk, emb, model))

    return results
