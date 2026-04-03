from __future__ import annotations

import asyncio
import sys
import types

import pytest

if "chromadb" not in sys.modules:
    chromadb_stub = types.ModuleType("chromadb")
    chromadb_stub.ClientAPI = object
    chromadb_stub.Collection = object
    chromadb_stub.PersistentClient = lambda *args, **kwargs: None
    sys.modules["chromadb"] = chromadb_stub

from api.services.rag import retrieve as rag_retrieve
from api.services.rag.types import Chunk, RAGConfig


def _sample_chunk() -> Chunk:
    return Chunk(
        id="chunk-1",
        source_id="source-1",
        text="Sample evidence text",
        page_start=0,
        page_end=0,
        char_start=0,
        char_end=20,
    )


def test_get_embedding_includes_dimensions_for_embedding_3(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_RAG_API_KEY", "test-key")
    monkeypatch.setenv("MAIA_RAG_EMBEDDING_BASE_URL", "https://example.com/v1")

    captured_payload: dict = {}

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    class _FakeAsyncClient:
        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def post(self, url: str, headers: dict, json: dict) -> _FakeResponse:
            captured_payload["url"] = url
            captured_payload["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(rag_retrieve.httpx, "AsyncClient", lambda timeout=30.0: _FakeAsyncClient())

    output = asyncio.run(
        rag_retrieve._get_embedding(
            "test query",
            model="text-embedding-3-large",
            dimensions=384,
        )
    )

    assert output == [0.1, 0.2, 0.3]
    assert captured_payload["url"] == "https://example.com/v1/embeddings"
    assert captured_payload["json"]["model"] == "text-embedding-3-large"
    assert captured_payload["json"]["dimensions"] == 384


def test_retrieve_dimension_mismatch_falls_back_to_keyword(monkeypatch) -> None:
    config = RAGConfig(
        embedding_model="text-embedding-3-large",
        embedding_dimensions=384,
        top_k=10,
        hybrid_weight=0.7,
    )
    scope = rag_retrieve.RetrievalScope()
    keyword_chunk = _sample_chunk()

    async def _fake_embedding(text: str, model: str, dimensions: int) -> list[float]:
        assert model == "text-embedding-3-large"
        assert dimensions == 384
        return [0.12, 0.23, 0.34]

    def _raise_mismatch(*args, **kwargs):
        raise RuntimeError("Embedding dimension 3072 does not match collection dimensionality 384")

    monkeypatch.setattr(rag_retrieve, "_get_embedding", _fake_embedding)
    monkeypatch.setattr(rag_retrieve, "vector_search", _raise_mismatch)
    monkeypatch.setattr(rag_retrieve, "_keyword_search", lambda *args, **kwargs: [(keyword_chunk, 1.0)])
    monkeypatch.setattr(rag_retrieve, "get_anchors", lambda _chunk_id: [])

    results = asyncio.run(rag_retrieve.retrieve("what is this about", config, scope))

    assert len(results) == 1
    assert results[0].chunk.id == "chunk-1"
    assert results[0].match_type == "keyword"
    assert results[0].score == pytest.approx(0.3)
