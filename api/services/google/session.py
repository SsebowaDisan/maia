from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from api.services.google.errors import GoogleApiError, GoogleServiceError, GoogleTokenError
from api.services.google.oauth_scopes import missing_scopes
from api.services.google.service_account import (
    DEFAULT_SERVICE_ACCOUNT_SCOPES,
    issue_service_account_access_token,
    resolve_google_auth_mode,
)
from api.services.google.store import GoogleTokenRecord


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_http_error_message(exc: HTTPError) -> str:
    try:
        detail = exc.read().decode("utf-8", errors="ignore")
    except Exception:
        detail = ""
    return detail[:300] if detail else f"HTTP {exc.code}"


class GoogleAuthSession:
    """Authenticated request helper with automatic refresh and typed errors."""

    def __init__(
        self,
        *,
        user_id: str,
        run_id: str | None = None,
        fallback_tokens: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> None:
        self.user_id = user_id
        self.run_id = run_id
        from api.services.google.auth import get_google_oauth_manager

        self.oauth = get_google_oauth_manager()
        self.fallback_tokens = dict(fallback_tokens or {})
        self.settings = dict(settings or {})

    def _service_account_scopes(self) -> list[str]:
        raw = self.fallback_tokens.get("scopes")
        if isinstance(raw, list):
            scopes = [str(item).strip() for item in raw if str(item).strip()]
            if scopes:
                return scopes
        return list(DEFAULT_SERVICE_ACCOUNT_SCOPES)

    def _service_account_access_token(self) -> str:
        return issue_service_account_access_token(
            settings=self.settings,
            scopes=self._service_account_scopes(),
        )

    def get_tokens(self) -> GoogleTokenRecord | None:
        record = self.oauth.tokens.get_tokens(user_id=self.user_id)
        if record:
            return record
        access_token = str(self.fallback_tokens.get("access_token") or "").strip()
        if not access_token:
            return None
        scopes = self.fallback_tokens.get("scopes")
        scope_list = [str(item).strip() for item in scopes if str(item).strip()] if isinstance(scopes, list) else []
        return GoogleTokenRecord(
            user_id=self.user_id,
            access_token=access_token,
            refresh_token=str(self.fallback_tokens.get("refresh_token") or "").strip(),
            token_type=str(self.fallback_tokens.get("token_type") or "Bearer"),
            scopes=scope_list,
            expires_at=str(self.fallback_tokens.get("expires_at")) if self.fallback_tokens.get("expires_at") else None,
            id_token=str(self.fallback_tokens.get("id_token")) if self.fallback_tokens.get("id_token") else None,
            email=str(self.fallback_tokens.get("email")) if self.fallback_tokens.get("email") else None,
            date_updated=_utc_now().isoformat(),
        )

    def require_access_token(self) -> str:
        auth_mode = resolve_google_auth_mode(settings=self.settings)
        if auth_mode == "service_account":
            try:
                return self._service_account_access_token()
            except GoogleTokenError:
                # Resilient fallback: if service-account minting fails but OAuth is connected
                # for this user, continue with the OAuth token instead of hard failing.
                try:
                    record = self.oauth.ensure_valid_tokens(user_id=self.user_id)
                except GoogleTokenError:
                    raise
                access_token = str(getattr(record, "access_token", "") or "").strip()
                if access_token:
                    return access_token
                raise GoogleTokenError(
                    code="google_tokens_missing",
                    message=(
                        "Service-account token minting failed and no OAuth access token is available. "
                        "Reconnect Google OAuth or repair service-account credentials."
                    ),
                    status_code=401,
                )
        try:
            record = self.oauth.ensure_valid_tokens(user_id=self.user_id)
            return record.access_token
        except GoogleTokenError:
            fallback = self.get_tokens()
            if fallback and fallback.access_token:
                return fallback.access_token
            raise GoogleTokenError(
                code="google_tokens_missing",
                message=(
                    "Google OAuth token is missing or expired. Connect Google OAuth in Settings, "
                    "or switch auth mode to service_account."
                ),
                status_code=401,
            )

    def current_scopes(self) -> list[str]:
        auth_mode = resolve_google_auth_mode(settings=self.settings)
        if auth_mode == "service_account":
            return self._service_account_scopes()
        record = self.get_tokens()
        if record is None:
            return []
        return [str(item).strip() for item in (record.scopes or []) if str(item).strip()]

    def require_scopes(self, required_scopes: list[str], *, reason: str = "Google tool access") -> None:
        # Service account tokens are minted with all requested scopes at JWT issuance time;
        # there is no per-call OAuth grant to validate against.
        if resolve_google_auth_mode(settings=self.settings) == "service_account":
            return
        normalized_required = [str(item).strip() for item in required_scopes if str(item).strip()]
        if not normalized_required:
            return
        missing = missing_scopes(required_scopes=normalized_required, granted_scopes=self.current_scopes())
        if not missing:
            return
        raise GoogleTokenError(
            code="google_scopes_missing",
            message=(
                f"{reason} is missing required OAuth scopes: {', '.join(missing)}. "
                "Reconnect Google and grant the requested tool permissions."
            ),
            status_code=403,
        )

    def _build_headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        final_headers = dict(headers or {})
        final_headers.setdefault("Authorization", f"Bearer {self.require_access_token()}")
        return final_headers

    def request_json(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
        retry_on_unauthorized: bool = True,
    ) -> dict[str, Any]:
        target_url = url
        if params:
            query = urlencode({key: value for key, value in params.items() if value is not None})
            target_url = f"{url}?{query}" if query else url
        data = None
        final_headers = self._build_headers(headers=headers)
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            final_headers.setdefault("Content-Type", "application/json")
        request = Request(target_url, data=data, method=method.upper(), headers=final_headers)
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            if exc.code in (401, 403) and retry_on_unauthorized:
                try:
                    self.oauth.refresh_tokens(user_id=self.user_id)
                except GoogleServiceError:
                    pass
                return self.request_json(
                    method=method,
                    url=url,
                    params=params,
                    payload=payload,
                    headers=headers,
                    timeout=timeout,
                    retry_on_unauthorized=False,
                )
            raise GoogleApiError(
                code="google_api_http_error",
                message=f"Google API request failed: {_safe_http_error_message(exc)}",
                status_code=exc.code if 400 <= exc.code <= 599 else 502,
                details={"url": url, "method": method.upper()},
            ) from exc
        except GoogleServiceError:
            raise
        except Exception as exc:
            raise GoogleApiError(
                code="google_api_request_error",
                message=f"Google API request failed: {exc}",
                status_code=502,
                details={"url": url, "method": method.upper()},
            ) from exc
        if not raw:
            return {}
        try:
            payload_obj = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise GoogleApiError(
                code="google_api_invalid_json",
                message=f"Google API returned invalid JSON: {exc}",
                status_code=502,
                details={"url": url, "method": method.upper()},
            ) from exc
        if not isinstance(payload_obj, dict):
            raise GoogleApiError(
                code="google_api_invalid_payload",
                message="Google API returned unexpected payload shape.",
                status_code=502,
                details={"url": url, "method": method.upper()},
            )
        return payload_obj

    def request_bytes(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> bytes:
        target_url = url
        if params:
            query = urlencode({key: value for key, value in params.items() if value is not None})
            target_url = f"{url}?{query}" if query else url
        final_headers = self._build_headers(headers=headers)
        request = Request(target_url, method=method.upper(), headers=final_headers)
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as exc:
            raise GoogleApiError(
                code="google_api_http_error",
                message=f"Google API binary request failed: {_safe_http_error_message(exc)}",
                status_code=exc.code if 400 <= exc.code <= 599 else 502,
                details={"url": url, "method": method.upper()},
            ) from exc
        except Exception as exc:
            raise GoogleApiError(
                code="google_api_request_error",
                message=f"Google API binary request failed: {exc}",
                status_code=502,
                details={"url": url, "method": method.upper()},
            ) from exc
