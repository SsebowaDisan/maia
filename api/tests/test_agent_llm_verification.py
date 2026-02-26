from api.services.agent import llm_verification
from api.services.agent.llm_verification import build_llm_verification_check
from api.services.agent.models import AgentAction, AgentSource


def test_build_llm_verification_check_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_VERIFICATION_ENABLED", "0")
    check = build_llm_verification_check(
        task={},
        executed_steps=[],
        actions=[],
        sources=[],
    )
    assert check is None


def test_build_llm_verification_check_parses_result(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_VERIFICATION_ENABLED", "1")
    monkeypatch.setattr(
        llm_verification,
        "call_json_response",
        lambda **kwargs: {"status": "warn", "detail": "Missing at least one primary source cross-check."},
    )
    check = build_llm_verification_check(
        task={"objective": "Analyze site"},
        executed_steps=[{"tool_id": "report.generate", "status": "success"}],
        actions=[
            AgentAction(
                tool_id="report.generate",
                action_class="draft",
                status="success",
                summary="ok",
                started_at="2026-01-01T00:00:00Z",
                ended_at="2026-01-01T00:00:01Z",
                metadata={},
            )
        ],
        sources=[AgentSource(source_type="web", label="A", url="https://example.com", score=0.9, metadata={})],
    )
    assert isinstance(check, dict)
    assert check.get("status") == "warn"
