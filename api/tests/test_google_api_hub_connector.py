from __future__ import annotations

from api.services.agent.connectors.google_api_hub_connector import GoogleApiHubConnector


def test_google_api_hub_connector_uses_api_key_for_api_key_mode(monkeypatch) -> None:
    connector = GoogleApiHubConnector(settings={"GOOGLE_MAPS_API_KEY": "maps-key"})
    captured: dict[str, object] = {}

    def _fake_request_json(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(connector, "request_json", _fake_request_json)
    response = connector.call_json_api(
        base_url="https://maps.googleapis.com",
        path="maps/api/geocode/json",
        method="GET",
        query={"address": "Kampala"},
        auth_mode="api_key",
        api_key_envs=("GOOGLE_MAPS_API_KEY",),
    )
    assert response == {"ok": True}
    assert captured["url"] == "https://maps.googleapis.com/maps/api/geocode/json"
    params = captured["params"]
    assert isinstance(params, dict)
    assert params["key"] == "maps-key"


def test_google_api_hub_connector_uses_oauth_header(monkeypatch) -> None:
    connector = GoogleApiHubConnector(settings={})
    captured: dict[str, object] = {}

    def _fake_request_json(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(connector, "_oauth_token", lambda: "token-123")
    monkeypatch.setattr(connector, "request_json", _fake_request_json)
    _ = connector.call_json_api(
        base_url="https://gmail.googleapis.com",
        path="gmail/v1/users/me/messages",
        method="GET",
        query={},
        auth_mode="oauth",
    )
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer token-123"

