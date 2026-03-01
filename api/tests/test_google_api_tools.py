from __future__ import annotations

from unittest.mock import patch

from api.services.agent.google_api_catalog import GOOGLE_API_TOOL_IDS
from api.services.agent.policy import get_capability_matrix
from api.services.agent.tools.base import ToolExecutionContext
from api.services.agent.tools.google_api_tools import build_google_api_tools


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        user_id="u1",
        tenant_id="t1",
        conversation_id="c1",
        run_id="run-abc123",
        mode="company_agent",
        settings={},
    )


class _GoogleApiHubStub:
    def call_json_api(self, **kwargs):
        return {
            "ok": True,
            "method": kwargs.get("method"),
            "path": kwargs.get("path"),
            "base_url": kwargs.get("base_url"),
        }


class _RegistryStub:
    def build(self, connector_id: str, settings=None):
        assert connector_id == "google_api_hub"
        return _GoogleApiHubStub()


def test_google_api_tools_catalog_is_registered() -> None:
    tools = build_google_api_tools()
    tool_ids = {tool.metadata.tool_id for tool in tools}
    assert "google.api.bigquery" in tool_ids
    assert "google.api.google_sheets" in tool_ids
    assert "google.api.pagespeed_insights" in tool_ids


def test_google_api_tool_executes_and_emits_trace_events() -> None:
    tools = build_google_api_tools()
    tool = next(item for item in tools if item.metadata.tool_id == "google.api.bigquery")
    with patch(
        "api.services.agent.tools.google_api_tools.get_connector_registry",
        return_value=_RegistryStub(),
    ):
        result = tool.execute(
            context=_context(),
            prompt="",
            params={
                "method": "POST",
                "path": "bigquery/v2/projects/demo/queries",
                "body": {"query": "SELECT 1"},
            },
        )
    assert result.data["tool_id"] == "google.api.bigquery"
    assert result.data["method"] == "POST"
    assert result.data["scene_surface"] == "system"
    event_types = [event.event_type for event in result.events]
    assert "api_call_started" in event_types
    assert "api_call_completed" in event_types
    started_event = next(event for event in result.events if event.event_type == "api_call_started")
    assert started_event.data["scene_surface"] == "system"


def test_google_api_tool_sets_document_surface_for_docs_domain() -> None:
    tools = build_google_api_tools()
    tool = next(item for item in tools if item.metadata.tool_id == "google.api.google_sheets")
    with patch(
        "api.services.agent.tools.google_api_tools.get_connector_registry",
        return_value=_RegistryStub(),
    ):
        result = tool.execute(
            context=_context(),
            prompt="",
            params={"method": "GET", "path": "v4/spreadsheets"},
        )
    assert result.data["scene_surface"] == "document"
    started_event = next(event for event in result.events if event.event_type == "api_call_started")
    assert started_event.data["scene_surface"] == "document"


def test_policy_and_catalog_cover_same_google_api_tool_ids() -> None:
    policy_ids = {
        item.tool_id
        for item in get_capability_matrix()
        if item.tool_id.startswith("google.api.")
    }
    assert GOOGLE_API_TOOL_IDS.issubset(policy_ids)
