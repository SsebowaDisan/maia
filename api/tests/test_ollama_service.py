from __future__ import annotations

import json

import httpx
import pytest

from api.services.ollama.errors import OllamaError
from api.services.ollama.service import OllamaService


def test_list_models_normalizes_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(
            status_code=200,
            json={
                "models": [
                    {"name": "llama3.2:3b", "size": 123_456_789, "digest": "sha256:a"},
                    {"name": "mistral:7b", "size": 987_654_321, "digest": "sha256:b"},
                ]
            },
        )

    service = OllamaService(
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(handler),
    )

    rows = service.list_models()

    assert len(rows) == 2
    assert rows[0]["name"] == "llama3.2:3b"
    assert rows[1]["name"] == "mistral:7b"


def test_pull_model_stream_reports_progress() -> None:
    stream_rows = [
        {"status": "pulling manifest"},
        {"status": "downloading", "total": 100, "completed": 25},
        {"status": "downloading", "total": 100, "completed": 100},
        {"status": "success"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/pull"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "llama3.2:3b"
        body = "\n".join(json.dumps(row) for row in stream_rows)
        return httpx.Response(status_code=200, text=body)

    progress_updates: list[dict[str, object]] = []
    service = OllamaService(
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(handler),
    )

    result = service.pull_model(
        model="llama3.2:3b",
        on_progress=lambda update: progress_updates.append(update),
    )

    assert result["model"] == "llama3.2:3b"
    assert result["completed"] is True
    assert progress_updates
    assert progress_updates[-1]["percent"] == 100.0


def test_list_models_raises_unreachable_when_connect_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        raise httpx.ConnectError("connection refused")

    service = OllamaService(
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(OllamaError) as exc_info:
        service.list_models()

    assert exc_info.value.code == "ollama_unreachable"
