"""RAG Pipeline orchestrator — runs all 14 phases end-to-end.

Two main flows:
1. Ingestion: upload → classify → extract → normalize → chunk → embed → index → citation_prep
2. Query: retrieve → rerank → coverage → answer → citations → deliver

Usage:
    from api.services.rag.pipeline import ingest_file, query_group, query_file

    # Ingest a file
    source = await ingest_file("/path/to/report.pdf", group_id="marketing")

    # Query against a group
    result = await query_group("What are the pricing trends?", group_id="marketing")

    # Query a single file (chat upload)
    result = await query_file("Summarize this", source_id="abc123")
"""

from __future__ import annotations

import uuid
from typing import Any

from api.services.rag.types import (
    SourceRecord, RAGConfig, DeliveryPayload, IngestionStatus,
)
from api.services.rag.config import get_config
from api.services.rag.observability import StageTimer

# Phase imports
from api.services.rag import upload as phase_upload
from api.services.rag import classify as phase_classify
from api.services.rag import extract as phase_extract
from api.services.rag import normalize as phase_normalize
from api.services.rag import chunk as phase_chunk
from api.services.rag import embed as phase_embed
from api.services.rag import index as phase_index
from api.services.rag import citation_prep as phase_citation_prep
from api.services.rag import retrieve as phase_retrieve
from api.services.rag import rerank as phase_rerank
from api.services.rag import coverage as phase_coverage
from api.services.rag import answer as phase_answer
from api.services.rag import citations as phase_citations
from api.services.rag import deliver as phase_deliver


# ── Ingestion Flow ───────────────────────────────────────────────────────────

async def ingest_file(
    file_path: str,
    group_id: str = "",
    owner_id: str = "",
    config: RAGConfig | None = None,
    metadata: dict[str, Any] | None = None,
) -> SourceRecord:
    """Ingest a file through the full pipeline: upload → ... → citation_ready.

    Returns the SourceRecord after all phases complete.
    The source will have rag_ready=True and citation_ready=True.
    """
    cfg = config or get_config()
    trace_id = f"trace_{uuid.uuid4().hex[:12]}"

    # Phase 1: Upload
    with StageTimer(trace_id, "upload", ""):
        source = await phase_upload.upload_file(
            file_path, group_id=group_id, owner_id=owner_id, metadata=metadata,
        )

    # Read file data
    file_data = open(file_path, "rb").read()

    # Phase 2: Classify
    source.status = IngestionStatus.CLASSIFYING
    with StageTimer(trace_id, "classify", source.id):
        classification = await phase_classify.classify_source(source, file_data)
        source.processing_route = classification.processing_route

    # Phase 3: Extract
    source.status = IngestionStatus.EXTRACTING
    with StageTimer(trace_id, "extract", source.id):
        extraction = await phase_extract.extract_source(source, classification, file_data)

    # Phase 4: Normalize
    source.status = IngestionStatus.NORMALIZING
    with StageTimer(trace_id, "normalize", source.id):
        normalized = await phase_normalize.normalize_document(extraction)

    # Phase 5: Chunk
    source.status = IngestionStatus.CHUNKING
    with StageTimer(trace_id, "chunk", source.id):
        chunks = await phase_chunk.chunk_document(normalized, source, cfg)

    # Phase 6: Embed
    source.status = IngestionStatus.EMBEDDING
    with StageTimer(trace_id, "embed", source.id):
        embedded = await phase_embed.embed_chunks(chunks, cfg)

    # Phase 7: Index (sets rag_ready)
    source.status = IngestionStatus.INDEXING
    with StageTimer(trace_id, "index", source.id):
        indexed = await phase_index.index_chunks(embedded, source, cfg)
        await phase_index.mark_rag_ready(source)

    # Phase 8: Citation Prep (sets citation_ready)
    source.status = IngestionStatus.PREPARING_CITATIONS
    with StageTimer(trace_id, "citation_prep", source.id):
        anchors = await phase_citation_prep.prepare_citations(source, chunks, extraction)
        await phase_citation_prep.mark_citation_ready(source)

    source.status = IngestionStatus.CITATION_READY
    return source


async def ingest_url(
    url: str,
    group_id: str = "",
    owner_id: str = "",
    config: RAGConfig | None = None,
) -> SourceRecord:
    """Ingest a URL through the full pipeline."""
    cfg = config or get_config()
    trace_id = f"trace_{uuid.uuid4().hex[:12]}"

    with StageTimer(trace_id, "upload", ""):
        source = await phase_upload.upload_url(url, group_id=group_id, owner_id=owner_id)

    source.status = IngestionStatus.CLASSIFYING
    with StageTimer(trace_id, "classify", source.id):
        classification = await phase_classify.classify_source(source)

    source.status = IngestionStatus.EXTRACTING
    with StageTimer(trace_id, "extract", source.id):
        extraction = await phase_extract.extract_source(source, classification)

    source.status = IngestionStatus.NORMALIZING
    with StageTimer(trace_id, "normalize", source.id):
        normalized = await phase_normalize.normalize_document(extraction)

    source.status = IngestionStatus.CHUNKING
    with StageTimer(trace_id, "chunk", source.id):
        chunks = await phase_chunk.chunk_document(normalized, source, cfg)

    source.status = IngestionStatus.EMBEDDING
    with StageTimer(trace_id, "embed", source.id):
        embedded = await phase_embed.embed_chunks(chunks, cfg)

    source.status = IngestionStatus.INDEXING
    with StageTimer(trace_id, "index", source.id):
        indexed = await phase_index.index_chunks(embedded, source, cfg)
        await phase_index.mark_rag_ready(source)

    source.status = IngestionStatus.PREPARING_CITATIONS
    with StageTimer(trace_id, "citation_prep", source.id):
        anchors = await phase_citation_prep.prepare_citations(source, chunks, extraction)
        await phase_citation_prep.mark_citation_ready(source)

    source.status = IngestionStatus.CITATION_READY
    return source


async def ingest_chat_upload(
    file_data: bytes,
    filename: str,
    chat_id: str,
    owner_id: str = "",
    config: RAGConfig | None = None,
) -> SourceRecord:
    """Ingest a file uploaded via chat composer. Same pipeline, returns when rag_ready."""
    cfg = config or get_config()
    trace_id = f"trace_{uuid.uuid4().hex[:12]}"

    with StageTimer(trace_id, "upload", ""):
        source = await phase_upload.upload_from_chat(file_data, filename, chat_id, owner_id)

    source.status = IngestionStatus.CLASSIFYING
    with StageTimer(trace_id, "classify", source.id):
        classification = await phase_classify.classify_source(source, file_data)
        source.processing_route = classification.processing_route

    source.status = IngestionStatus.EXTRACTING
    with StageTimer(trace_id, "extract", source.id):
        extraction = await phase_extract.extract_source(source, classification, file_data)

    source.status = IngestionStatus.NORMALIZING
    with StageTimer(trace_id, "normalize", source.id):
        normalized = await phase_normalize.normalize_document(extraction)

    source.status = IngestionStatus.CHUNKING
    with StageTimer(trace_id, "chunk", source.id):
        chunks = await phase_chunk.chunk_document(normalized, source, cfg)

    source.status = IngestionStatus.EMBEDDING
    with StageTimer(trace_id, "embed", source.id):
        embedded = await phase_embed.embed_chunks(chunks, cfg)

    source.status = IngestionStatus.INDEXING
    with StageTimer(trace_id, "index", source.id):
        await phase_index.index_chunks(embedded, source, cfg)
        await phase_index.mark_rag_ready(source)

    # Citation prep runs after rag_ready — user can start querying immediately
    source.status = IngestionStatus.PREPARING_CITATIONS
    with StageTimer(trace_id, "citation_prep", source.id):
        await phase_citation_prep.prepare_citations(source, chunks, extraction)
        await phase_citation_prep.mark_citation_ready(source)

    source.status = IngestionStatus.CITATION_READY
    return source


# ── Query Flow ───────────────────────────────────────────────────────────────

async def query_group(
    question: str,
    group_id: str,
    owner_id: str = "",
    config: RAGConfig | None = None,
) -> DeliveryPayload:
    """Query against all files in a group. Returns answer with highlighted citations."""
    cfg = config or get_config()
    trace_id = f"trace_{uuid.uuid4().hex[:12]}"
    scope = phase_retrieve.RetrievalScope(group_id=group_id, owner_id=owner_id)

    return await _run_query(question, scope, f"group:{group_id}", cfg, trace_id)


async def query_file(
    question: str,
    source_id: str,
    owner_id: str = "",
    config: RAGConfig | None = None,
) -> DeliveryPayload:
    """Query against a single file. Returns answer with highlighted citations."""
    cfg = config or get_config()
    trace_id = f"trace_{uuid.uuid4().hex[:12]}"
    scope = phase_retrieve.RetrievalScope(source_ids=[source_id], owner_id=owner_id)

    return await _run_query(question, scope, f"file:{source_id}", cfg, trace_id)


async def query_sources(
    question: str,
    source_ids: list[str],
    owner_id: str = "",
    config: RAGConfig | None = None,
) -> DeliveryPayload:
    """Query against specific files. Returns answer with highlighted citations."""
    cfg = config or get_config()
    trace_id = f"trace_{uuid.uuid4().hex[:12]}"
    scope = phase_retrieve.RetrievalScope(source_ids=source_ids, owner_id=owner_id)

    return await _run_query(question, scope, f"sources:{len(source_ids)} files", cfg, trace_id)


async def _run_query(
    question: str,
    scope: phase_retrieve.RetrievalScope,
    scope_description: str,
    config: RAGConfig,
    trace_id: str,
) -> DeliveryPayload:
    """Internal: run the full query pipeline."""

    # Phase 9: Retrieve
    with StageTimer(trace_id, "retrieve", ""):
        retrieved = await phase_retrieve.retrieve(question, config, scope)

    if not retrieved:
        # No evidence found
        from api.services.rag.types import (
            GeneratedAnswer, CoverageResult, CoverageVerdict,
        )
        empty_answer = GeneratedAnswer(
            text="I couldn't find relevant information in the selected sources to answer this question.",
            grounded=True,
            coverage=CoverageResult(verdict=CoverageVerdict.INSUFFICIENT),
        )
        return await phase_deliver.deliver(empty_answer, [], [], scope_description, trace_id)

    # Phase 10: Rerank
    with StageTimer(trace_id, "rerank", ""):
        ranked = await phase_rerank.rerank(retrieved, question, config)

    # Phase 11: Coverage Check
    with StageTimer(trace_id, "coverage", ""):
        coverage_result = await phase_coverage.check_coverage(question, ranked, config)

    # Phase 12: Answer
    with StageTimer(trace_id, "answer", ""):
        answer = await phase_answer.generate_answer(question, ranked, coverage_result, config)

    # Phase 13: Citations
    with StageTimer(trace_id, "citations", ""):
        citation_list = await phase_citations.build_citations(answer, ranked)

    # Phase 14: Deliver
    with StageTimer(trace_id, "deliver", ""):
        payload = await phase_deliver.deliver(
            answer, citation_list, ranked, scope_description, trace_id,
        )

    return payload
