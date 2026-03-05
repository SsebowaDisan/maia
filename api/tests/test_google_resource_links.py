from __future__ import annotations

from api.services.google.resource_links import (
    analyze_google_resource_reference,
    first_google_link,
    normalize_link_aliases,
)


def test_analyze_google_doc_link() -> None:
    parsed = analyze_google_resource_reference(
        "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz123456/edit?usp=sharing"
    )
    assert parsed is not None
    assert parsed.resource_type == "google_doc"
    assert parsed.resource_id == "1AbCdEfGhIjKlMnOpQrStUvWxYz123456"
    assert "/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz123456/" in parsed.canonical_url


def test_analyze_google_sheet_link() -> None:
    parsed = analyze_google_resource_reference(
        "https://docs.google.com/spreadsheets/d/17xYzAbCdEfGhIjKlMnOpQrStUvWx123456/edit#gid=0"
    )
    assert parsed is not None
    assert parsed.resource_type == "google_sheet"
    assert parsed.resource_id == "17xYzAbCdEfGhIjKlMnOpQrStUvWx123456"


def test_analyze_ga4_link_from_fragment() -> None:
    parsed = analyze_google_resource_reference(
        "https://analytics.google.com/analytics/web/#/p123456789/reports/intelligenthome"
    )
    assert parsed is not None
    assert parsed.resource_type == "ga4_property"
    assert parsed.resource_id == "123456789"


def test_analyze_numeric_value_as_ga4_property() -> None:
    parsed = analyze_google_resource_reference("123456789")
    assert parsed is not None
    assert parsed.resource_type == "ga4_property"
    assert parsed.resource_id == "123456789"


def test_first_google_link_extracts_first_url() -> None:
    text = (
        "use this sheet https://docs.google.com/spreadsheets/d/17xYzAbCdEfGhIjKlMnOpQrStUvWx123456/edit "
        "and this doc https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz123456/edit"
    )
    assert first_google_link(text).startswith("https://docs.google.com/spreadsheets/")


def test_normalize_link_aliases_drops_invalid_rows() -> None:
    payload = {
        "Quarterly Sheet": {
            "resource_type": "google_sheet",
            "resource_id": "17xYzAbCdEfGhIjKlMnOpQrStUvWx123456",
            "canonical_url": "https://docs.google.com/spreadsheets/d/17xYzAbCdEfGhIjKlMnOpQrStUvWx123456/edit",
        },
        "Invalid": {"resource_type": "", "resource_id": ""},
        "Other": "skip",
    }
    normalized = normalize_link_aliases(payload)
    assert list(normalized.keys()) == ["quarterly sheet"]
    assert normalized["quarterly sheet"]["resource_type"] == "google_sheet"
