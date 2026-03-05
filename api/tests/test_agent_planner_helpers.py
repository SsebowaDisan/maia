from api.schemas import ChatRequest
from api.services.agent.planner_helpers import infer_intent_signals_from_text, intent_signals


def test_infer_intent_signals_detects_docs_sheets_and_web_research() -> None:
    signals = infer_intent_signals_from_text(
        message=(
            "Research online competitors, write notes in Google Docs, "
            "update the Google Sheets roadmap tracker, and provide a summary."
        ),
        agent_goal="Use latest web sources.",
    )
    assert signals["explicit_web_discovery"] is True
    assert signals["wants_docs_output"] is True
    assert signals["wants_sheets_output"] is True
    assert signals["wants_report"] is True


def test_intent_signals_extracts_url_and_email() -> None:
    request = ChatRequest(
        message="Inspect https://example.com and send to ops@example.com",
        agent_mode="company_agent",
    )
    signals = intent_signals(request)
    assert signals["url"] == "https://example.com"
    assert signals["recipient_email"] == "ops@example.com"
    assert signals["wants_send"] is True
