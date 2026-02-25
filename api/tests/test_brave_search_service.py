from __future__ import annotations

import httpx
import pytest

from api.services.search.brave_search import BraveSearchService
from api.services.search.errors import BraveSearchError


def test_brave_web_search_normalizes_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Subscription-Token") == "brave_key"
        assert request.url.path.endswith("/res/v1/web/search")
        payload = {
            "web": {
                "results": [
                    {
                        "title": "Result A",
                        "url": "https://example.com/a",
                        "description": "Snippet A",
                    },
                    {
                        "title": "Result B",
                        "url": "https://example.com/b",
                        "description": "Snippet B",
                    },
                ]
            }
        }
        return httpx.Response(status_code=200, json=payload)

    transport = httpx.MockTransport(handler)
    service = BraveSearchService(api_key="brave_key", transport=transport, max_retries=0)

    result = service.web_search(query="maia ai")

    assert result["provider"] == "brave"
    assert result["query"] == "maia ai"
    assert result["total"] == 2
    assert len(result["results"]) == 2
    assert result["results"][0]["url"] == "https://example.com/a"


def test_brave_search_retries_on_5xx() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(status_code=503, json={"error": "temporary"})
        return httpx.Response(
            status_code=200,
            json={
                "web": {
                    "results": [
                        {"title": "Recovered", "url": "https://example.com/recovered", "description": "ok"}
                    ]
                }
            },
        )

    service = BraveSearchService(
        api_key="brave_key",
        transport=httpx.MockTransport(handler),
        max_retries=3,
    )

    result = service.web_search(query="retry test")

    assert attempts["count"] == 3
    assert result["total"] == 1


def test_brave_search_requires_key() -> None:
    with pytest.raises(BraveSearchError) as exc_info:
        BraveSearchService(api_key="")

    assert exc_info.value.code == "brave_api_key_missing"
