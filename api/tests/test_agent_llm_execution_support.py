from api.services.agent import llm_execution_support
from api.services.agent.llm_execution_support import polish_email_content, suggest_failure_recovery


def test_suggest_failure_recovery_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RECOVERY_ENABLED", "0")
    hint = suggest_failure_recovery(
        request_message="Send report",
        tool_id="mailer.report_send",
        step_title="Send report",
        error_text="timeout",
        recent_steps=[],
    )
    assert hint == ""


def test_suggest_failure_recovery_parses_json(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_RECOVERY_ENABLED", "1")
    monkeypatch.setattr(
        llm_execution_support,
        "call_json_response",
        lambda **kwargs: {"recovery_hint": "Retry after validating recipient and mailer credentials."},
    )
    hint = suggest_failure_recovery(
        request_message="Send report",
        tool_id="mailer.report_send",
        step_title="Send report",
        error_text="invalid recipient",
        recent_steps=[],
    )
    assert "Retry" in hint


def test_polish_email_content_fallback(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_EMAIL_POLISH_ENABLED", "1")
    monkeypatch.setattr(llm_execution_support, "call_json_response", lambda **kwargs: None)
    result = polish_email_content(
        subject="Weekly report",
        body_text="Body",
        recipient="ops@example.com",
    )
    assert result["subject"] == "Weekly report"
    assert result["body_text"] == "Body"
