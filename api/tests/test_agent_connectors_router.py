from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.routers.agent_api import connectors


def test_connector_plugins_returns_registry_manifest_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _StubRegistry:
        def plugin_manifests(self, settings=None):
            captured["settings"] = settings or {}
            return [{"connector_id": "gmail", "enabled": True, "actions": []}]

    monkeypatch.setattr("api.routers.agent_api.connectors.get_connector_registry", lambda: _StubRegistry())
    monkeypatch.setattr("api.routers.agent_api.connectors.get_context", lambda: object())
    monkeypatch.setattr(
        "api.routers.agent_api.connectors.load_user_settings",
        lambda _context, user_id: {"agent.tenant_id": f"tenant-{user_id}"},
    )

    rows = connectors.connector_plugins(user_id="user-1")
    assert rows[0]["connector_id"] == "gmail"
    assert captured["settings"] == {"agent.tenant_id": "tenant-user-1"}


def test_connector_plugin_returns_single_manifest_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _StubRegistry:
        def names(self):
            return ["gmail"]

        def plugin_manifest(self, connector_id: str, settings=None):
            captured["connector_id"] = connector_id
            captured["settings"] = settings or {}
            return {"connector_id": connector_id, "enabled": True, "actions": []}

    monkeypatch.setattr("api.routers.agent_api.connectors.get_connector_registry", lambda: _StubRegistry())
    monkeypatch.setattr("api.routers.agent_api.connectors.get_context", lambda: object())
    monkeypatch.setattr(
        "api.routers.agent_api.connectors.load_user_settings",
        lambda _context, user_id: {"agent.tenant_id": f"tenant-{user_id}"},
    )

    payload = connectors.connector_plugin("gmail", user_id="user-2")
    assert payload["connector_id"] == "gmail"
    assert captured["connector_id"] == "gmail"
    assert captured["settings"] == {"agent.tenant_id": "tenant-user-2"}


def test_connector_plugin_raises_404_for_unknown_connector(monkeypatch) -> None:
    class _StubRegistry:
        def names(self):
            return ["gmail"]

    monkeypatch.setattr("api.routers.agent_api.connectors.get_connector_registry", lambda: _StubRegistry())
    with pytest.raises(HTTPException) as exc_info:
        connectors.connector_plugin("unknown", user_id="user-3")
    assert exc_info.value.status_code == 404
