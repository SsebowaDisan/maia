from __future__ import annotations

from api.services.agent.connectors.browser_contact import contact_discovery


class _PageStub:
    def __init__(self, payload):
        self._payload = payload
        self.url = "https://example.com"

    def evaluate(self, _script: str):
        return self._payload

    def title(self) -> str:
        return "Example"


def test_collect_contact_channels_normalizes_duplicates() -> None:
    page = _PageStub(
        {
            "emails": ["sales@example.com", "Sales@example.com", " "],
            "phones": ["+1 617 555 0101", "+1 617 555 0101", ""],
        }
    )
    channels = contact_discovery.collect_contact_channels(page)

    assert channels["emails"] == ["sales@example.com"]
    assert channels["phones"] == ["+1 617 555 0101"]


def test_rank_navigation_candidates_without_llm_uses_default_order() -> None:
    original = contact_discovery.has_openai_credentials
    contact_discovery.has_openai_credentials = lambda: False
    try:
        ranked = contact_discovery.rank_navigation_candidates(
            [
                {"url": "https://example.com/a"},
                {"url": "https://example.com/b"},
                {"url": "https://example.com/c"},
            ],
            max_hops=2,
        )
    finally:
        contact_discovery.has_openai_credentials = original

    assert ranked == [0, 1]

