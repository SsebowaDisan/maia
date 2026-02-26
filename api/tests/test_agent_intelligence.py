import pytest

from api.services.agent.intelligence import build_verification_report, derive_task_intelligence
from api.services.agent.models import AgentAction, AgentSource


@pytest.fixture(autouse=True)
def _disable_llm_intelligence_paths(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_LLM_INTENT_ENABLED", "0")
    monkeypatch.setenv("MAIA_AGENT_LLM_VERIFICATION_ENABLED", "0")


def _action(tool_id: str, status: str, summary: str) -> AgentAction:
    return AgentAction(
        tool_id=tool_id,
        action_class="execute" if tool_id.endswith(".send") else "read",
        status=status,  # type: ignore[arg-type]
        summary=summary,
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        metadata={},
    )


def test_derive_task_intelligence_extracts_url_and_email() -> None:
    task = derive_task_intelligence(
        message="Analyze https://axongroup.com and send report to ops@example.com",
        agent_goal=None,
    )
    assert task.target_url == "https://axongroup.com"
    assert task.target_host == "axongroup.com"
    assert task.delivery_email == "ops@example.com"
    assert task.requires_delivery is True
    assert task.requires_web_inspection is True
    assert task.requested_report is True


def test_derive_task_intelligence_treats_sent_as_delivery_intent() -> None:
    task = derive_task_intelligence(
        message="Analysis and write the report in docs, then sent the docs file to ops@example.com",
        agent_goal=None,
    )
    assert task.delivery_email == "ops@example.com"
    assert task.requires_delivery is True


def test_verification_report_marks_delivery_warning_on_failed_send() -> None:
    task = derive_task_intelligence(
        message="Analyze https://axongroup.com and send report to ops@example.com",
        agent_goal=None,
    )
    report = build_verification_report(
        task=task,
        planned_tool_ids=["browser.playwright.inspect", "report.generate", "gmail.send"],
        executed_steps=[
            {"tool_id": "browser.playwright.inspect", "status": "success"},
            {"tool_id": "report.generate", "status": "success"},
            {"tool_id": "gmail.send", "status": "failed"},
        ],
        actions=[
            _action("browser.playwright.inspect", "success", "ok"),
            _action("report.generate", "success", "ok"),
            _action(
                "gmail.send",
                "failed",
                "google_api_http_error: invalid authentication credentials",
            ),
        ],
        sources=[
            AgentSource(
                source_type="web",
                label="Axon Group",
                url="https://axongroup.com/products-and-solutions",
                score=0.9,
                metadata={},
            )
        ],
    )
    checks = report.get("checks") or []
    details = " ".join(str(item.get("detail") or "") for item in checks if isinstance(item, dict))
    assert "Reconnect Google OAuth in Settings and retry." in details
    assert float(report.get("score") or 0.0) < 100.0


def test_verification_report_marks_dwd_delegation_remediation_hint() -> None:
    task = derive_task_intelligence(
        message="Analyze https://axongroup.com and send report to ops@example.com",
        agent_goal=None,
    )
    report = build_verification_report(
        task=task,
        planned_tool_ids=["browser.playwright.inspect", "report.generate"],
        executed_steps=[
            {"tool_id": "browser.playwright.inspect", "status": "success"},
            {"tool_id": "report.generate", "status": "success"},
            {"tool_id": "mailer.report_send", "status": "failed"},
        ],
        actions=[
            _action("browser.playwright.inspect", "success", "ok"),
            _action("report.generate", "success", "ok"),
            _action(
                "mailer.report_send",
                "failed",
                "gmail_dwd_delegation_denied: Domain-wide delegation is not authorized.",
            ),
        ],
        sources=[
            AgentSource(
                source_type="web",
                label="Axon Group",
                url="https://axongroup.com/products-and-solutions",
                score=0.9,
                metadata={},
            )
        ],
    )
    checks = report.get("checks") or []
    details = " ".join(str(item.get("detail") or "") for item in checks if isinstance(item, dict))
    assert "domain-wide delegation" in details.lower()
    assert float(report.get("score") or 0.0) < 100.0


def test_verification_report_detects_contradiction_signals() -> None:
    task = derive_task_intelligence(
        message="Analyze company profile",
        agent_goal=None,
    )
    report = build_verification_report(
        task=task,
        planned_tool_ids=["marketing.web_research"],
        executed_steps=[
            {
                "tool_id": "marketing.web_research",
                "status": "success",
                "summary": "Collected evidence about employee count and locations",
            }
        ],
        actions=[_action("marketing.web_research", "success", "Collected source evidence.")],
        sources=[
            AgentSource(
                source_type="web",
                label="Source A",
                url="https://example.com/a",
                score=0.8,
                metadata={"excerpt": "Axon Group has 100 employees and 6 locations in Belgium."},
            ),
            AgentSource(
                source_type="web",
                label="Source B",
                url="https://example.com/b",
                score=0.8,
                metadata={"excerpt": "Axon Group has 250 employees and 6 locations in Belgium."},
            ),
        ],
    )
    contradictions = report.get("contradictions") or []
    assert isinstance(contradictions, list)
    assert len(contradictions) >= 1
    contradiction_check = next(
        (
            item
            for item in (report.get("checks") or [])
            if isinstance(item, dict) and str(item.get("name") or "") == "Contradiction scan"
        ),
        None,
    )
    assert isinstance(contradiction_check, dict)
    assert contradiction_check.get("status") == "warn"
