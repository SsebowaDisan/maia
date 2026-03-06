from api.schemas import ChatRequest
from api.services.agent import planner_helpers as helpers_module
from api.services.agent.planner_helpers import (
    infer_intent_signals_from_text,
    intent_signals,
    sanitize_search_query,
)


def test_infer_intent_signals_uses_llm_output_for_docs_sheets_and_research(monkeypatch) -> None:
    helpers_module._infer_intent_signals_cached.cache_clear()
    monkeypatch.setattr(
        helpers_module,
        "enrich_task_intelligence",
        lambda **kwargs: {
            "routing_mode": "online_research",
            "requested_report": True,
            "wants_docs_output": True,
            "wants_sheets_output": True,
            "wants_highlight_extract": False,
            "wants_file_scope": False,
            "requires_delivery": False,
            "requires_attachment_delivery": False,
            "requires_contact_form_submission": False,
        },
    )
    monkeypatch.setattr(
        helpers_module,
        "classify_intent_tags",
        lambda **kwargs: ["report_generation", "docs_write", "sheets_update"],
    )
    signals = infer_intent_signals_from_text(
        message="Research online competitors and publish outputs.",
        agent_goal="Use external sources and provide workspace deliverables.",
    )
    assert signals["explicit_web_discovery"] is True
    assert signals["wants_docs_output"] is True
    assert signals["wants_sheets_output"] is True
    assert signals["wants_report"] is True


def test_intent_signals_extracts_url_and_email(monkeypatch) -> None:
    helpers_module._infer_intent_signals_cached.cache_clear()
    monkeypatch.setattr(
        helpers_module,
        "enrich_task_intelligence",
        lambda **kwargs: {
            "routing_mode": "url_scrape",
            "requires_delivery": True,
            "requires_web_inspection": True,
        },
    )
    monkeypatch.setattr(helpers_module, "classify_intent_tags", lambda **kwargs: ["email_delivery"])
    request = ChatRequest(
        message="Inspect https://example.com and send to ops@example.com",
        agent_mode="company_agent",
    )
    signals = intent_signals(request)
    assert signals["url"] == "https://example.com"
    assert signals["recipient_email"] == "ops@example.com"
    assert signals["wants_send"] is True


def test_intent_signals_relies_on_llm_for_contact_form_detection(monkeypatch) -> None:
    helpers_module._infer_intent_signals_cached.cache_clear()
    monkeypatch.setattr(
        helpers_module,
        "enrich_task_intelligence",
        lambda **kwargs: {
            "routing_mode": "url_scrape",
            "requires_web_inspection": True,
            "requires_contact_form_submission": True,
        },
    )
    monkeypatch.setattr(
        helpers_module,
        "classify_intent_tags",
        lambda **kwargs: ["web_research", "contact_form_submission"],
    )
    signals = infer_intent_signals_from_text(
        message=(
            "Analyze https://axongroup.com/ and send them a message asking about services and office hours."
        ),
        agent_goal="",
    )
    assert signals["url"] == "https://axongroup.com/"
    assert signals["wants_contact_form"] is True
    assert signals["wants_send"] is True


def test_intent_signals_without_llm_contact_flag_does_not_assume_contact_form(monkeypatch) -> None:
    helpers_module._infer_intent_signals_cached.cache_clear()
    monkeypatch.setattr(
        helpers_module,
        "enrich_task_intelligence",
        lambda **kwargs: {
            "routing_mode": "url_scrape",
            "requires_web_inspection": True,
        },
    )
    monkeypatch.setattr(helpers_module, "classify_intent_tags", lambda **kwargs: ["web_research"])
    signals = infer_intent_signals_from_text(
        message=(
            "Analyze https://axongroup.com/ and send them a message asking about services and office hours."
        ),
        agent_goal="",
    )
    assert signals["url"] == "https://axongroup.com/"
    assert signals["wants_contact_form"] is False


def test_sanitize_search_query_strips_planning_context_labels() -> None:
    raw = (
        "Do deep research on renewable energy transition trends in 2025.\n"
        "Contract objective: Validate market growth assumptions.\n"
        "Success checks: Include at least 10 cited external sources.\n"
        "Conversation context: prior chat snippets.\n"
    )

    query = sanitize_search_query(raw)

    lowered = query.lower()
    assert query.startswith("Do deep research on renewable energy transition trends in 2025.")
    assert "contract objective:" not in lowered
    assert "success checks:" not in lowered
    assert "conversation context:" not in lowered
