from __future__ import annotations

from typing import Any

from api.services.google.auth import GoogleAuthSession
from api.services.google.errors import GoogleServiceError

from .base import BaseConnector, ConnectorError, ConnectorHealth


class GoogleApiHubConnector(BaseConnector):
    connector_id = "google_api_hub"

    def _session(self) -> GoogleAuthSession:
        user_id = str(
            self.settings.get("__agent_user_id")
            or self.settings.get("agent.tenant_id")
            or "default"
        )
        run_id = str(self.settings.get("__agent_run_id") or "").strip() or None
        fallback = {
            "access_token": self._read_secret("GOOGLE_WORKSPACE_ACCESS_TOKEN")
            or self._read_secret("GOOGLE_OAUTH_ACCESS_TOKEN"),
            "refresh_token": self._read_secret("GOOGLE_WORKSPACE_REFRESH_TOKEN"),
            "token_type": "Bearer",
        }
        return GoogleAuthSession(
            user_id=user_id,
            run_id=run_id,
            fallback_tokens=fallback,
            settings=self.settings,
        )

    def _oauth_token(self) -> str:
        try:
            token = self._session().require_access_token()
        except GoogleServiceError as exc:
            raise ConnectorError(str(exc)) from exc
        if not token:
            raise ConnectorError(
                "Google OAuth token is missing. Connect Google account in Settings."
            )
        return token

    def _read_api_key(self, names: tuple[str, ...]) -> str:
        for name in names:
            value = self._read_secret(name)
            if value:
                return value
        raise ConnectorError(
            "Google API key missing. Configure one of: " + ", ".join(names)
        )

    def health_check(self) -> ConnectorHealth:
        try:
            self._oauth_token()
        except ConnectorError as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        return ConnectorHealth(self.connector_id, True, "configured")

    def call_json_api(
        self,
        *,
        base_url: str,
        path: str,
        method: str,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        auth_mode: str,
        api_key_envs: tuple[str, ...] = (),
    ) -> Any:
        clean_base = str(base_url or "").strip().rstrip("/")
        clean_path = str(path or "").strip()
        if not clean_base:
            raise ConnectorError("base_url is required.")
        if not clean_path:
            raise ConnectorError("path is required.")
        target_url = (
            clean_path
            if clean_path.startswith("http://") or clean_path.startswith("https://")
            else f"{clean_base}/{clean_path.lstrip('/')}"
        )
        method_upper = str(method or "GET").strip().upper() or "GET"
        query_rows = dict(query or {})
        headers: dict[str, str] = {}
        if auth_mode == "oauth":
            headers["Authorization"] = f"Bearer {self._oauth_token()}"
        elif auth_mode == "api_key":
            api_key = self._read_api_key(api_key_envs or ("GOOGLE_MAPS_API_KEY",))
            query_rows.setdefault("key", api_key)
        elif auth_mode == "none":
            pass
        else:
            raise ConnectorError(f"Unsupported auth_mode: {auth_mode}")

        payload = body if method_upper in ("POST", "PUT", "PATCH", "DELETE") else None
        return self.request_json(
            method=method_upper,
            url=target_url,
            headers=headers,
            params=query_rows,
            payload=payload if isinstance(payload, dict) else None,
            timeout_seconds=30,
        )
