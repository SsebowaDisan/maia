"""RAG Pipeline Phase 7: Index — store chunks in ChromaDB.

Persistent vector store that survives restarts. Handles 10,000+ files.
Supports metadata filtering by group_id, owner_id, source_id, source_type.

ChromaDB stores:
  - Embedding vectors for similarity search
  - Full text for keyword search
  - Metadata for group/owner/source filtering
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

import chromadb

from api.services.rag.types import (
    EmbeddedChunk,
    IndexedChunk,
    RAGConfig,
    SourceRecord,
)

logger = logging.getLogger(__name__)

# ── ChromaDB client ──────────────────────────────────────────────────────────

_CHROMA_PERSIST_DIR = os.environ.get(
    "MAIA_RAG_CHROMA_DIR",
    str(Path("D:/maia-data/rag_index") if Path("D:/").exists() else Path("ktem_app_data/rag_index")),
)

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None

_COLLECTION_NAME = "maia_rag_chunks"


def _get_collection() -> chromadb.Collection:
    """Get or create the ChromaDB collection. Lazy initialization."""
    global _client, _collection

    if _collection is not None:
        return _collection

    persist_dir = Path(_CHROMA_PERSIST_DIR)
    persist_dir.mkdir(parents=True, exist_ok=True)

    _client = chromadb.PersistentClient(path=str(persist_dir))
    _collection = _client.get_or_create_collection(
        name=_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    logger.info(
        "ChromaDB initialized: dir=%s, collection=%s, count=%d",
        persist_dir, _COLLECTION_NAME, _collection.count(),
    )
    return _collection


# ── Store operations ─────────────────────────────────────────────────────────

def store_chunk(chunk: IndexedChunk) -> None:
    """Add a single chunk to ChromaDB."""
    collection = _get_collection()

    metadata = {
        "source_id": chunk.source_id or "",
        "group_id": chunk.group_id or "",
        "owner_id": chunk.owner_id or "",
        "filename": chunk.filename or "",
        "source_type": chunk.source_type or "",
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "char_start": chunk.char_start,
        "char_end": chunk.char_end,
        "chunk_type": chunk.chunk_type or "text",
        "heading_path": json.dumps(chunk.heading_path) if chunk.heading_path else "[]",
        "indexed_at": chunk.indexed_at or datetime.now(timezone.utc).isoformat(),
    }

    # ChromaDB needs at least a 1-element embedding or None
    embedding = chunk.embedding if chunk.embedding and len(chunk.embedding) > 0 else None

    collection.upsert(
        ids=[chunk.index_id],
        documents=[chunk.text],
        metadatas=[metadata],
        embeddings=[embedding] if embedding else None,
    )


def search(
    query_embedding: list[float],
    top_k: int = 10,
    filters: dict[str, str] | None = None,
) -> list[tuple[IndexedChunk, float]]:
    """Search ChromaDB by embedding similarity with metadata filters.

    Parameters
    ----------
    query_embedding : embedding vector for the query
    top_k : number of results to return (0 = all)
    filters : dict of metadata key→value to pre-filter.
              Supported: source_id, group_id, owner_id, source_type, filename

    Returns
    -------
    List of (IndexedChunk, score) tuples sorted by descending score.
    """
    collection = _get_collection()

    if collection.count() == 0:
        return []

    # Build ChromaDB where clause
    where_clause = _build_where_clause(filters)

    n_results = top_k if top_k > 0 else min(collection.count(), 10000)

    # Query ChromaDB
    has_embeddings = query_embedding and len(query_embedding) > 0 and any(v != 0 for v in query_embedding)

    if has_embeddings:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where_clause if where_clause else None,
            include=["documents", "metadatas", "distances"],
        )
    else:
        # No embeddings — get all matching documents for keyword search
        results = collection.get(
            where=where_clause if where_clause else None,
            include=["documents", "metadatas"],
            limit=n_results,
        )
        # Convert get() format to query() format for uniform processing
        results = {
            "ids": [results["ids"]],
            "documents": [results["documents"]],
            "metadatas": [results["metadatas"]],
            "distances": [([0.5] * len(results["ids"]))],  # default score
        }

    # Convert results to IndexedChunk objects
    chunks: list[tuple[IndexedChunk, float]] = []

    if not results["ids"] or not results["ids"][0]:
        return chunks

    for i, doc_id in enumerate(results["ids"][0]):
        metadata = results["metadatas"][0][i] if results["metadatas"] else {}
        text = results["documents"][0][i] if results["documents"] else ""
        distance = results["distances"][0][i] if results["distances"] else 0.5

        # ChromaDB cosine distance → similarity score (1 - distance)
        score = max(0.0, 1.0 - distance) if has_embeddings else 0.5

        heading_path = []
        try:
            heading_path = json.loads(metadata.get("heading_path", "[]"))
        except Exception:
            pass

        chunk = IndexedChunk(
            id=doc_id,
            source_id=metadata.get("source_id", ""),
            text=text,
            page_start=int(metadata.get("page_start", 0)),
            page_end=int(metadata.get("page_end", 0)),
            char_start=int(metadata.get("char_start", 0)),
            char_end=int(metadata.get("char_end", 0)),
            heading_path=heading_path,
            chunk_type=metadata.get("chunk_type", "text"),
            group_id=metadata.get("group_id", ""),
            owner_id=metadata.get("owner_id", ""),
            filename=metadata.get("filename", ""),
            source_type=metadata.get("source_type", ""),
            index_id=doc_id,
            indexed_at=metadata.get("indexed_at", ""),
        )
        chunks.append((chunk, score))

    # Sort by score descending
    chunks.sort(key=lambda x: x[1], reverse=True)
    return chunks


def _build_where_clause(filters: dict[str, str] | None) -> dict | None:
    """Build ChromaDB where clause from filters dict."""
    if not filters:
        return None

    conditions = []
    for key, value in filters.items():
        if value and key in ("source_id", "group_id", "owner_id", "source_type", "filename"):
            conditions.append({key: {"$eq": value}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def delete_source(source_id: str) -> int:
    """Remove all chunks for a given source_id."""
    collection = _get_collection()

    # Get all IDs with this source_id
    results = collection.get(
        where={"source_id": {"$eq": source_id}},
        include=[],
    )

    if not results["ids"]:
        return 0

    collection.delete(ids=results["ids"])
    count = len(results["ids"])
    logger.info("Deleted %d chunks for source %s", count, source_id)
    return count


def get_store_size() -> int:
    """Return the total number of chunks in ChromaDB."""
    collection = _get_collection()
    return collection.count()


def clear_store() -> None:
    """Clear the entire collection. Useful for tests."""
    global _collection
    if _client:
        try:
            _client.delete_collection(_COLLECTION_NAME)
        except Exception:
            pass
    _collection = None


# ── Promote EmbeddedChunk → IndexedChunk ────────────────────────────────────


def _embedded_to_indexed(chunk: EmbeddedChunk, index_id: str) -> IndexedChunk:
    """Promote an EmbeddedChunk to an IndexedChunk, copying all fields."""
    embedded_fields = {f.name: getattr(chunk, f.name) for f in fields(EmbeddedChunk)}
    return IndexedChunk(
        **embedded_fields,
        index_id=index_id,
        indexed_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Public API ──────────────────────────────────────────────────────────────


async def index_chunks(
    chunks: list[EmbeddedChunk],
    source: SourceRecord,
    config: RAGConfig,
) -> list[IndexedChunk]:
    """Write embedded chunks to ChromaDB.

    Each chunk is stored with metadata (source_id, group_id, owner_id,
    page, heading_path, source_type) so retrieval can pre-filter by group.

    Does NOT set source.rag_ready — call mark_rag_ready() after confirming
    all chunks are stored.
    """
    indexed: list[IndexedChunk] = []

    for i, chunk in enumerate(chunks):
        index_id = f"{source.id}::{i}"
        ic = _embedded_to_indexed(chunk, index_id)

        # Ensure group metadata is set from source
        if not ic.group_id:
            ic.group_id = source.group_id
        if not ic.owner_id:
            ic.owner_id = source.owner_id
        if not ic.filename:
            ic.filename = source.filename
        if not ic.source_type:
            ic.source_type = (
                source.source_type.value
                if hasattr(source.source_type, "value")
                else str(source.source_type)
            )

        # Store file path in metadata for page-image rendering later
        if source.upload_url:
            ic.metadata = ic.metadata or {}
            ic.metadata["file_path"] = source.upload_url

        store_chunk(ic)
        indexed.append(ic)

    logger.info(
        "Indexed %d chunks for source %s (total store: %d)",
        len(indexed),
        source.id,
        get_store_size(),
    )
    return indexed


async def mark_rag_ready(source: SourceRecord) -> None:
    """ONLY this phase sets rag_ready = True on the source record."""
    source.rag_ready = True
    source.updated_at = datetime.now(timezone.utc).isoformat()
    logger.info("Source %s marked rag_ready", source.id)
