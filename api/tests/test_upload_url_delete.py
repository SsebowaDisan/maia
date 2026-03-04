from __future__ import annotations

from types import SimpleNamespace

from api.services.upload import groups


def test_normalize_url_for_match_removes_fragment_and_trailing_root() -> None:
    assert (
        groups._normalize_url_for_match("https://AxonGroup.com/#overview")
        == "https://axongroup.com"
    )
    assert (
        groups._normalize_url_for_match("https://axongroup.com/about-axon/")
        == "https://axongroup.com/about-axon"
    )


def test_url_signatures_include_query_and_base_variants() -> None:
    signatures = groups._url_signatures("https://axongroup.com/about-axon?lang=en#section")
    assert "https://axongroup.com/about-axon?lang=en" in signatures
    assert "https://axongroup.com/about-axon" in signatures


def test_match_requested_urls_to_sources_uses_name_and_note_candidates() -> None:
    source_rows = [
        SimpleNamespace(
            id="src-1",
            name="https://axongroup.com/about-axon/",
            path="",
            note={},
        ),
        SimpleNamespace(
            id="src-2",
            name="About Axon page",
            path="",
            note={"source_url": "https://axongroup.com/products-and-solutions"},
        ),
    ]
    matched, unresolved = groups._match_requested_urls_to_sources(
        requested_urls=[
            "https://axongroup.com/about-axon",
            "https://axongroup.com/products-and-solutions/",
            "https://axongroup.com/contact",
        ],
        source_rows=source_rows,
    )

    assert matched["https://axongroup.com/about-axon"] == ["src-1"]
    assert matched["https://axongroup.com/products-and-solutions/"] == ["src-2"]
    assert unresolved == ["https://axongroup.com/contact"]

