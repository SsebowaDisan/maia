from types import SimpleNamespace

from api.services.agent.orchestration.finalization_scope import filter_sources_for_response_scope


def _source(*, label: str, url: str, metadata: dict | None = None):
    return SimpleNamespace(label=label, url=url, metadata=metadata or {})


def test_filter_sources_excludes_workspace_sources_by_default() -> None:
    scoped = filter_sources_for_response_scope(
        sources=[
            _source(
                label="workspace.sheets.track_step",
                url="https://docs.google.com/spreadsheets/d/abc",
                metadata={"provider": "google_sheets"},
            ),
            _source(label="Axon Group", url="https://axongroup.com/"),
        ],
        settings={},
    )
    urls = [str(item.url or "") for item in scoped]
    assert "https://docs.google.com/spreadsheets/d/abc" not in urls
    assert "https://axongroup.com/" in urls


def test_filter_sources_keeps_workspace_sources_when_intent_requests_docs_or_sheets() -> None:
    scoped = filter_sources_for_response_scope(
        sources=[
            _source(
                label="workspace.docs.research_notes",
                url="https://docs.google.com/document/d/abc",
                metadata={"provider": "google_docs"},
            )
        ],
        settings={"__intent_tags": ["docs_write"]},
    )
    assert len(scoped) == 1
    assert str(scoped[0].url or "").startswith("https://docs.google.com/document/")
