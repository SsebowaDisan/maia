from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from api.services.agent.connectors.sec_edgar_connector import (
    SecEdgarConnector,
    _has_financial_signal,
    _normalize_hit,
)


# ── unit: signal detection ────────────────────────────────────────────────────

def test_has_financial_signal_true():
    assert _has_financial_signal("Apple 10-K annual report earnings 2023")


def test_has_financial_signal_false():
    assert not _has_financial_signal("how to bake a cake recipe")


# ── unit: hit normalization ───────────────────────────────────────────────────

def test_normalize_hit_minimal():
    hit = {
        "_id": "0001234567890",
        "form_type": "10-K",
        "file_date": "2023-01-15",
        "entity_name": "ACME Corp",
    }
    result = _normalize_hit(hit)
    assert result is not None
    assert result["source"] == "sec_edgar"
    assert "ACME Corp" in result["title"]
    assert "10-K" in result["title"]
    assert result["url"].startswith("https://www.sec.gov/Archives/edgar/data/")


def test_normalize_hit_missing_accession_returns_none():
    result = _normalize_hit({"form_type": "10-K"})
    assert result is None


def test_normalize_hit_display_names_list():
    hit = {
        "_id": "0009876543210",
        "display_names": ["Tesla Inc"],
        "form_type": "10-Q",
        "file_date": "2024-04-01",
    }
    result = _normalize_hit(hit)
    assert result is not None
    assert "Tesla Inc" in result["title"]


# ── unit: connector search_web shape ─────────────────────────────────────────

def _mock_edgar_response(hits: list[dict]) -> dict:
    return {"hits": {"hits": [{"_source": h} for h in hits]}}


def test_sec_edgar_search_web_returns_results():
    connector = SecEdgarConnector(settings={})
    raw_hits = [
        {
            "_id": "0001193125231234",
            "form_type": "10-K",
            "file_date": "2023-03-01",
            "entity_name": "BigCo",
            "period_of_report": "2022-12-31",
        }
    ]
    with patch.object(connector, "request_json", return_value=_mock_edgar_response(raw_hits)):
        result = connector.search_web(query="BigCo annual report", count=5)

    assert isinstance(result, dict)
    assert "results" in result
    assert len(result["results"]) == 1
    assert result["results"][0]["source"] == "sec_edgar"


def test_sec_edgar_search_web_returns_empty_on_error():
    connector = SecEdgarConnector(settings={})
    from api.services.agent.connectors.base import ConnectorError

    with patch.object(connector, "request_json", side_effect=ConnectorError("network error")):
        result = connector.search_web(query="anything", count=4)

    assert isinstance(result, dict)
    assert result.get("results") == []


# ── unit: health_check ────────────────────────────────────────────────────────

def test_sec_edgar_health_check_ok():
    connector = SecEdgarConnector(settings={})
    health = connector.health_check()
    assert health.ok is True
    assert health.connector_id == "sec_edgar"
