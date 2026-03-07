from __future__ import annotations

from api.services.agent.tools.registry import ToolRegistry


def test_tool_registry_excludes_contact_form_tool_when_specialist_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_CONTACT_FORM_ENABLED", "0")
    registry = ToolRegistry()

    tool_ids = {row.get("tool_id") for row in registry.list_tools() if isinstance(row, dict)}
    assert "browser.contact_form.send" not in tool_ids


def test_tool_registry_includes_contact_form_tool_when_specialist_enabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_AGENT_CONTACT_FORM_ENABLED", "1")
    registry = ToolRegistry()

    tool_ids = {row.get("tool_id") for row in registry.list_tools() if isinstance(row, dict)}
    assert "browser.contact_form.send" in tool_ids

