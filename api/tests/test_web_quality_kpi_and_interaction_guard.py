from __future__ import annotations

from unittest.mock import patch

from api.services.agent.orchestration.web_evidence import (
    record_web_evidence,
    summarize_web_evidence,
)
from api.services.agent.orchestration.web_kpi import (
    evaluate_web_kpi_gate,
    record_web_kpi,
    summarize_web_kpi,
)
from api.services.agent.tools.browser_interaction_guard import assess_browser_interactions
from api.services.agent.tools.web_quality import compute_quality_score, quality_band


def test_web_quality_score_penalizes_blocked_pages() -> None:
    clear_score = compute_quality_score(
        render_quality="high",
        content_density=0.72,
        extraction_confidence=0.83,
        schema_coverage=0.92,
        evidence_count=4,
        blocked_signal=False,
    )
    blocked_score = compute_quality_score(
        render_quality="blocked",
        content_density=0.72,
        extraction_confidence=0.83,
        schema_coverage=0.92,
        evidence_count=4,
        blocked_signal=True,
    )
    assert clear_score > blocked_score
    assert quality_band(blocked_score) in {"blocked", "low"}


def test_web_kpi_rollup_tracks_success_and_failures() -> None:
    settings: dict[str, object] = {}
    record_web_kpi(
        settings=settings,  # type: ignore[arg-type]
        tool_id="web.extract.structured",
        status="success",
        duration_seconds=1.2,
        data={
            "quality_score": 0.82,
            "content_density": 0.66,
            "blocked_signal": False,
            "provider_requested": "brave_search",
            "provider": "brave_search",
        },
    )
    record_web_kpi(
        settings=settings,  # type: ignore[arg-type]
        tool_id="browser.playwright.inspect",
        status="failed",
        duration_seconds=2.1,
        data={},
    )
    summary = summarize_web_kpi(settings)  # type: ignore[arg-type]
    assert int(summary.get("web_steps_total") or 0) == 2
    assert int(summary.get("web_steps_success") or 0) == 1
    assert int(summary.get("web_steps_failed") or 0) == 1
    assert float(summary.get("avg_quality_score") or 0.0) > 0.0


def test_web_kpi_gate_reports_threshold_failures() -> None:
    settings: dict[str, object] = {
        "agent.web_kpi.enforce_gate": True,
        "agent.web_kpi.min_steps": 3,
        "agent.web_kpi.min_success_rate": 0.9,
        "agent.web_kpi.min_avg_quality": 0.8,
    }
    record_web_kpi(
        settings=settings,  # type: ignore[arg-type]
        tool_id="marketing.web_research",
        status="success",
        duration_seconds=1.0,
        data={"quality_score": 0.62},
    )
    summary = summarize_web_kpi(settings)  # type: ignore[arg-type]
    gate = evaluate_web_kpi_gate(settings=settings, summary=summary)  # type: ignore[arg-type]
    assert gate["gate_enforced"] is True
    assert gate["ready_for_scale"] is False
    assert len(gate["failed_checks"]) >= 1


def test_web_evidence_summary_tracks_citation_readiness() -> None:
    settings: dict[str, object] = {}
    record_web_evidence(
        settings=settings,  # type: ignore[arg-type]
        tool_id="web.extract.structured",
        status="success",
        data={
            "url": "https://example.com",
            "quality_score": 0.8,
            "evidence": [{"field": "title", "quote": "Example domain title", "url": "https://example.com"}],
        },
        sources=[],
    )
    summary = summarize_web_evidence(settings)  # type: ignore[arg-type]
    assert int(summary.get("web_evidence_total") or 0) == 1
    assert bool(summary.get("citations_ready")) is True


def test_browser_interaction_guard_respects_llm_decisions() -> None:
    with patch(
        "api.services.agent.tools.browser_interaction_guard.call_json_response",
        return_value={
            "actions": [
                {
                    "index": 1,
                    "allow": True,
                    "reason": "Needed for navigation",
                    "type": "click",
                    "selector": "a[href='/about']",
                    "value": "",
                },
                {
                    "index": 2,
                    "allow": False,
                    "reason": "Potentially submits external data",
                    "type": "fill",
                    "selector": "textarea[name='message']",
                    "value": "secret",
                },
            ],
            "policy_note": "Allowed 1, blocked 1.",
        },
    ):
        decision = assess_browser_interactions(
            prompt="Inspect the company website and gather evidence.",
            url="https://example.com",
            actions=[
                {"type": "click", "selector": "a[href='/about']"},
                {"type": "fill", "selector": "textarea[name='message']", "value": "secret"},
            ],
        )
    assert len(decision.get("allowed_actions") or []) == 1
    assert len(decision.get("blocked_actions") or []) == 1
