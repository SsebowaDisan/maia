from __future__ import annotations

from api.services.agent.orchestration.step_planner_sections import app as planner_app
from api.services.agent.orchestration.step_planner_sections import (
    intent_enrichment as enrichment_module,
)
from api.services.agent.planner import PlannedStep


class _RegistryStub:
    def __init__(self, rows):
        self._rows = rows

    def list_tools(self):
        return list(self._rows)


def test_extract_available_tool_ids_reads_registry_rows() -> None:
    registry = _RegistryStub(
        [
            {"tool_id": "browser.playwright.inspect"},
            {"tool_id": "report.generate"},
            {"tool_id": "browser.contact_form.send"},
        ]
    )

    available = planner_app._extract_available_tool_ids(registry)

    assert "browser.playwright.inspect" in available
    assert "report.generate" in available
    assert "browser.contact_form.send" in available


def test_filter_steps_by_available_tools_removes_unavailable_specialist_steps() -> None:
    steps = [
        PlannedStep(tool_id="browser.playwright.inspect", title="Inspect", params={}),
        PlannedStep(tool_id="browser.contact_form.send", title="Contact", params={}),
        PlannedStep(tool_id="report.generate", title="Report", params={}),
    ]

    filtered = planner_app._filter_steps_by_available_tools(
        steps=steps,
        available_tool_ids={"browser.playwright.inspect", "report.generate"},
    )

    assert [step.tool_id for step in filtered] == [
        "browser.playwright.inspect",
        "report.generate",
    ]


def test_contact_form_capability_gate_prefers_runtime_setting_over_env(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_CONTACT_FORM_ENABLED", "1")

    enabled = enrichment_module._contact_form_capability_enabled(
        {"__contact_form_capability_enabled": False}
    )

    assert enabled is False

