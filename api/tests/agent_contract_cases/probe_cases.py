from api.services.agent import llm_contracts
from api.services.agent.llm_contracts import propose_fact_probe_steps

def test_propose_fact_probe_steps_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_FACT_PROBE_ENABLED", "0")
    rows = propose_fact_probe_steps(
        contract={"required_facts": ["Find phone number"]},
        request_message="Find phone and send summary",
        target_url="https://example.com",
        existing_steps=[],
        allowed_tool_ids=["browser.playwright.inspect"],
    )
    assert rows == []


def test_propose_fact_probe_steps_parses_and_filters(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_FACT_PROBE_ENABLED", "1")
    monkeypatch.setattr(
        llm_contracts,
        "call_json_response",
        lambda **kwargs: {
            "steps": [
                {
                    "tool_id": "browser.playwright.inspect",
                    "title": "Inspect contact page for phone number",
                    "params": {"url": "https://example.com/contact"},
                },
                {"tool_id": "unknown.tool", "title": "ignore", "params": {}},
                "bad",
            ]
        },
    )
    rows = propose_fact_probe_steps(
        contract={"required_facts": ["Find phone number"]},
        request_message="Find phone and send summary",
        target_url="https://example.com",
        existing_steps=[{"tool_id": "marketing.web_research", "title": "Research", "params": {"query": "x"}}],
        allowed_tool_ids=["browser.playwright.inspect", "marketing.web_research"],
    )
    assert rows == [
        {
            "tool_id": "browser.playwright.inspect",
            "title": "Inspect contact page for phone number",
            "params": {"url": "https://example.com/contact"},
        }
    ]
