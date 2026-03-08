from __future__ import annotations

from unittest.mock import patch

import pytest

from api.services.agent.connectors.newsapi_connector import NewsAPIConnector, _normalize_article


# ── unit: article normalization ───────────────────────────────────────────────

def test_normalize_article_full():
    article = {
        "title": "Big News Today",
        "url": "https://reuters.com/article/big-news",
        "description": "Something happened.",
        "publishedAt": "2024-06-01T10:00:00Z",
        "source": {"name": "Reuters"},
    }
    result = _normalize_article(article)
    assert result is not None
    assert result["url"] == "https://reuters.com/article/big-news"
    assert result["title"] == "Big News Today"
    assert result["source"] == "newsapi"
    assert "Reuters" in result["description"] or "Something happened" in result["description"]


def test_normalize_article_missing_url_returns_none():
    result = _normalize_article({"title": "No URL"})
    assert result is None


def test_normalize_article_missing_title_returns_none():
    result = _normalize_article({"url": "https://example.com"})
    assert result is None


# ── unit: connector search_web shape ─────────────────────────────────────────

def _mock_newsapi_response(articles: list[dict]) -> dict:
    return {"status": "ok", "totalResults": len(articles), "articles": articles}


def test_newsapi_search_web_with_key_returns_results():
    connector = NewsAPIConnector(settings={"NEWSAPI_API_KEY": "test_key"})
    articles = [
        {
            "title": "Tech Breakthrough",
            "url": "https://techcrunch.com/article",
            "description": "A big leap.",
            "publishedAt": "2024-01-01T00:00:00Z",
            "source": {"name": "TechCrunch"},
        }
    ]
    with patch.object(connector, "request_json", return_value=_mock_newsapi_response(articles)):
        result = connector.search_web(query="tech breakthrough 2024", count=5)

    assert isinstance(result, dict)
    assert "results" in result
    assert len(result["results"]) == 1
    assert result["results"][0]["source"] == "newsapi"


def test_newsapi_search_web_no_key_raises():
    from api.services.agent.connectors.base import ConnectorError
    connector = NewsAPIConnector(settings={})
    with pytest.raises(ConnectorError):
        connector.search_web(query="anything", count=5)


def test_newsapi_search_web_bad_status_returns_empty():
    connector = NewsAPIConnector(settings={"NEWSAPI_API_KEY": "test_key"})
    with patch.object(connector, "request_json", return_value={"status": "error", "articles": []}):
        result = connector.search_web(query="anything", count=5)
    assert result.get("results") == []


# ── unit: health_check ────────────────────────────────────────────────────────

def test_newsapi_health_check_ok_with_key():
    connector = NewsAPIConnector(settings={"NEWSAPI_API_KEY": "some_key"})
    health = connector.health_check()
    assert health.ok is True


def test_newsapi_health_check_missing_key():
    connector = NewsAPIConnector(settings={})
    health = connector.health_check()
    assert health.ok is False
