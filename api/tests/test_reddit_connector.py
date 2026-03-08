from __future__ import annotations

from unittest.mock import patch

import pytest

from api.services.agent.connectors.reddit_connector import RedditConnector, _normalize_post


# ── unit: post normalization ──────────────────────────────────────────────────

def test_normalize_post_link_post():
    # _normalize_post takes the inner "data" dict directly
    post_data = {
        "title": "Great Discussion Thread",
        "url": "https://reddit.com/r/technology/comments/abc123",
        "selftext": "Some content here",
        "permalink": "/r/technology/comments/abc123/great_discussion/",
        "subreddit_name_prefixed": "r/technology",
        "score": 450,
    }
    result = _normalize_post(post_data)
    assert result is not None
    assert result["source"] == "reddit"
    assert result["title"] == "Great Discussion Thread"
    assert "reddit.com" in result["url"]


def test_normalize_post_missing_title_returns_none():
    post_data = {"permalink": "/r/test/comments/abc"}
    result = _normalize_post(post_data)
    assert result is None


def test_normalize_post_empty_data_returns_none():
    result = _normalize_post({})
    assert result is None


# ── unit: connector search_web shape ─────────────────────────────────────────

def _mock_reddit_response(posts: list[dict]) -> dict:
    return {"data": {"children": posts}}


def test_reddit_search_web_returns_results():
    connector = RedditConnector(settings={})
    # Reddit API format: list of {data: {title, permalink, ...}} children
    posts = [
        {
            "data": {
                "title": "Interesting AI Discussion",
                "url": "https://reddit.com/r/MachineLearning/comments/xyz789",
                "selftext": "This is a thread about AI.",
                "permalink": "/r/MachineLearning/comments/xyz789/interesting_ai/",
                "subreddit_name_prefixed": "r/MachineLearning",
                "score": 1200,
            }
        }
    ]
    # request_json returns {"data": {"children": [{"data": {...}}]}}
    with patch.object(connector, "request_json", return_value={"data": {"children": posts}}):
        result = connector.search_web(query="AI machine learning trends", count=5)

    assert isinstance(result, dict)
    assert "results" in result
    assert len(result["results"]) == 1
    assert result["results"][0]["source"] == "reddit"


def test_reddit_search_web_bad_response_returns_empty():
    connector = RedditConnector(settings={})
    with patch.object(connector, "request_json", return_value={"error": "not found"}):
        result = connector.search_web(query="anything", count=5)
    assert isinstance(result, dict)
    assert result.get("results") == []


def test_reddit_search_web_network_error_returns_empty():
    connector = RedditConnector(settings={})
    from api.services.agent.connectors.base import ConnectorError
    with patch.object(connector, "request_json", side_effect=ConnectorError("429 rate limit")):
        result = connector.search_web(query="anything", count=5)
    assert isinstance(result, dict)
    assert result.get("results") == []


# ── unit: health_check ────────────────────────────────────────────────────────

def test_reddit_health_check_ok():
    connector = RedditConnector(settings={})
    health = connector.health_check()
    assert health.ok is True
    assert health.connector_id == "reddit"
