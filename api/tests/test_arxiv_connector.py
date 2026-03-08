from __future__ import annotations

import textwrap
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from api.services.agent.connectors.arxiv_connector import ArXivConnector, _has_academic_signal, _parse_arxiv_xml


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_atom(entries: list[dict]) -> bytes:
    """Build a minimal Atom feed from a list of {id, title, summary} dicts."""
    NS = "http://www.w3.org/2005/Atom"
    root = ET.Element(f"{{{NS}}}feed")
    for e in entries:
        entry = ET.SubElement(root, f"{{{NS}}}entry")
        id_el = ET.SubElement(entry, f"{{{NS}}}id")
        id_el.text = e.get("id", "https://arxiv.org/abs/2401.00001")
        title_el = ET.SubElement(entry, f"{{{NS}}}title")
        title_el.text = e.get("title", "Test Paper")
        summary_el = ET.SubElement(entry, f"{{{NS}}}summary")
        summary_el.text = e.get("summary", "A summary.")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# ── unit: signal detection ────────────────────────────────────────────────────

def test_has_academic_signal_true():
    assert _has_academic_signal("machine learning research paper")


def test_has_academic_signal_false():
    assert not _has_academic_signal("buy shoes online discount")


# ── unit: XML parser ─────────────────────────────────────────────────────────

def test_parse_arxiv_xml_returns_results():
    raw = _make_atom([
        {"id": "https://arxiv.org/abs/2401.00001", "title": "  Title A  ", "summary": "Summary A"},
        {"id": "https://arxiv.org/abs/2401.00002", "title": "Title B", "summary": "Summary B"},
    ])
    results = _parse_arxiv_xml(raw)
    assert len(results) == 2
    assert results[0]["title"] == "Title A"
    assert results[0]["url"] == "https://arxiv.org/abs/2401.00001"
    assert results[0]["source"] == "arxiv"


def test_parse_arxiv_xml_handles_bad_xml():
    results = _parse_arxiv_xml(b"not xml at all <<<")
    assert results == []


def test_parse_arxiv_xml_skips_missing_title():
    NS = "http://www.w3.org/2005/Atom"
    root = ET.Element(f"{{{NS}}}feed")
    entry = ET.SubElement(root, f"{{{NS}}}entry")
    id_el = ET.SubElement(entry, f"{{{NS}}}id")
    id_el.text = "https://arxiv.org/abs/0000"
    # no title element
    raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    results = _parse_arxiv_xml(raw)
    assert results == []


# ── unit: connector search_web shape ─────────────────────────────────────────

def test_arxiv_search_web_returns_dict_with_results():
    connector = ArXivConnector(settings={})
    raw = _make_atom([{"id": "https://arxiv.org/abs/2401.12345", "title": "LLM Survey", "summary": "Overview."}])

    # urlopen is imported locally inside search() so patch via urllib.request
    with patch("urllib.request.urlopen") as mock_open:
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = raw
        mock_open.return_value = mock_resp

        result = connector.search_web(query="large language model survey", count=5)

    assert isinstance(result, dict)
    assert "results" in result
    assert len(result["results"]) == 1
    assert result["results"][0]["source"] == "arxiv"


def test_arxiv_search_web_raises_on_non_retryable_error():
    connector = ArXivConnector(settings={})
    from urllib.error import HTTPError
    from api.services.agent.connectors.base import ConnectorError

    # A 500 wrapped in "arxiv request failed (500)" — not retryable (no leading space)
    with pytest.raises(ConnectorError):
        with patch("urllib.request.urlopen", side_effect=HTTPError(url=None, code=500, msg="Server Error", hdrs=None, fp=None)):
            connector.search_web(query="anything", count=4)


# ── unit: health_check ────────────────────────────────────────────────────────

def test_arxiv_health_check_ok():
    connector = ArXivConnector(settings={})
    health = connector.health_check()
    assert health.ok is True
    assert health.connector_id == "arxiv"
