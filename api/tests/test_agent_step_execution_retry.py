from __future__ import annotations

from api.services.agent.orchestration.step_execution_sections.app import (
    _should_retry_transient_browser_failure,
)
from api.services.agent.planner import PlannedStep


def test_should_retry_transient_browser_failure_for_http2_error() -> None:
    step = PlannedStep(
        tool_id="browser.playwright.inspect",
        title="Inspect source",
        params={},
    )
    should_retry = _should_retry_transient_browser_failure(
        step=step,
        params={},
        exc=RuntimeError("Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR at https://example.com"),
    )
    assert should_retry is True


def test_should_not_retry_when_already_retried() -> None:
    step = PlannedStep(
        tool_id="browser.playwright.inspect",
        title="Inspect source",
        params={},
    )
    should_retry = _should_retry_transient_browser_failure(
        step=step,
        params={"__retry_attempted": True},
        exc=RuntimeError("Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR at https://example.com"),
    )
    assert should_retry is False


def test_should_not_retry_for_non_browser_tool() -> None:
    step = PlannedStep(
        tool_id="marketing.web_research",
        title="Research online",
        params={},
    )
    should_retry = _should_retry_transient_browser_failure(
        step=step,
        params={},
        exc=RuntimeError("net::ERR_HTTP2_PROTOCOL_ERROR"),
    )
    assert should_retry is False

