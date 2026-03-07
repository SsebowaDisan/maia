from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.services.agent.connectors.base import BaseConnector
from api.services.agent.connectors.plugin_manifest import ConnectorPluginManifest
from api.services.agent.connectors.plugin_manifest import connector_plugin_action_hints
from api.services.agent.connectors.plugin_manifest import connector_plugin_manifest
from api.services.agent.connectors.registry import ConnectorRegistry


def test_connector_plugin_manifest_known_profile_has_scene_and_graph_mapping() -> None:
    manifest = connector_plugin_manifest(connector_id="playwright_browser", enabled=True)
    payload = manifest.model_dump(mode="json")
    assert payload["connector_id"] == "playwright_browser"
    assert payload["enabled"] is True
    assert isinstance(payload["actions"], list) and payload["actions"]
    assert any(row["scene_type"] == "browser" for row in payload["scene_mapping"])
    assert any(row["node_type"] in {"browser_action", "research"} for row in payload["graph_mapping"])


def test_connector_plugin_manifest_fallback_profile_is_valid() -> None:
    manifest = connector_plugin_manifest(connector_id="custom_connector", enabled=False)
    payload = manifest.model_dump(mode="json")
    assert payload["connector_id"] == "custom_connector"
    assert payload["enabled"] is False
    assert payload["actions"][0]["action_id"] == "custom_connector.call"
    assert payload["graph_mapping"][0]["action_id"] == "custom_connector.call"


def test_connector_registry_plugin_manifests_uses_connector_health() -> None:
    class _StubConnectorOk(BaseConnector):
        connector_id = "stub_ok"

    class _StubConnectorFail(BaseConnector):
        connector_id = "stub_fail"

        def health_check(self):
            health = super().health_check()
            return type(health)(connector_id=self.connector_id, ok=False, message="missing key")

    registry = ConnectorRegistry()
    registry._factories = {
        "stub_ok": _StubConnectorOk,
        "stub_fail": _StubConnectorFail,
    }
    rows = registry.plugin_manifests(settings={})
    by_id = {row["connector_id"]: row for row in rows}
    assert by_id["stub_ok"]["enabled"] is True
    assert by_id["stub_fail"]["enabled"] is False


def test_connector_registry_plugin_manifest_returns_single_payload() -> None:
    class _StubConnector(BaseConnector):
        connector_id = "stub_single"

    registry = ConnectorRegistry()
    registry._factories = {"stub_single": _StubConnector}

    payload = registry.plugin_manifest("stub_single", settings={})
    assert payload["connector_id"] == "stub_single"
    assert payload["enabled"] is True
    assert payload["actions"][0]["action_id"] == "stub_single.call"


def test_connector_plugin_manifest_validation_rejects_unknown_mapped_action_ids() -> None:
    with pytest.raises(ValidationError, match="unknown action_ids"):
        ConnectorPluginManifest.model_validate(
            {
                "connector_id": "gmail",
                "label": "Gmail",
                "enabled": True,
                "actions": [{"action_id": "email.send", "title": "Send", "event_family": "email", "scene_type": "email"}],
                "scene_mapping": [{"scene_type": "email", "action_ids": ["email.missing"]}],
                "graph_mapping": [{"action_id": "email.send", "node_type": "email_draft"}],
            }
        )


def test_connector_plugin_manifest_validation_rejects_duplicate_action_ids() -> None:
    with pytest.raises(ValidationError, match="duplicate action_id"):
        ConnectorPluginManifest.model_validate(
            {
                "connector_id": "gmail",
                "label": "Gmail",
                "enabled": True,
                "actions": [
                    {"action_id": "email.send", "title": "Send", "event_family": "email", "scene_type": "email"},
                    {
                        "action_id": "email.send",
                        "title": "Send Duplicate",
                        "event_family": "email",
                        "scene_type": "email",
                    },
                ],
                "scene_mapping": [{"scene_type": "email", "action_ids": ["email.send"]}],
                "graph_mapping": [{"action_id": "email.send", "node_type": "email_draft"}],
            }
        )


def test_connector_plugin_action_hints_resolves_scene_and_graph_mappings() -> None:
    hints = connector_plugin_action_hints(
        connector_id="google_analytics",
        action_id="analytics.fetch_report",
    )
    assert hints["plugin_connector_id"] == "google_analytics"
    assert hints["plugin_connector_label"] == "Google Analytics"
    assert hints["plugin_action_id"] == "analytics.fetch_report"
    assert hints["plugin_scene_type"] == "api"
    assert hints["plugin_graph_node_type"] == "api_operation"
