from __future__ import annotations

from typing import Any, Mapping

from .config import (
    GMAIL_SEND_SCOPE,
    GmailDwdConfig,
    get_impersonate_email,
    load_service_account_info,
)
from .errors import GmailDwdConfigError, map_gmail_send_exception

try:
    from google.oauth2 import service_account
except Exception:  # pragma: no cover - exercised through runtime import guard
    service_account = None

try:
    from googleapiclient.discovery import build as gmail_discovery_build
except Exception:  # pragma: no cover - exercised through runtime import guard
    gmail_discovery_build = None


def _build_service(
    *,
    service_account_info: dict[str, Any],
    impersonate_email: str,
    scope: str,
) -> Any:
    if service_account is None or gmail_discovery_build is None:
        raise GmailDwdConfigError(
            "Missing Google client dependencies. Install `google-auth` and "
            "`google-api-python-client`.",
            code="gmail_dwd_dependency_missing",
        )

    try:
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=[scope],
        )
        delegated = creds.with_subject(impersonate_email)
        return gmail_discovery_build(
            "gmail",
            "v1",
            credentials=delegated,
            cache_discovery=False,
        )
    except GmailDwdConfigError:
        raise
    except Exception as exc:
        raise map_gmail_send_exception(exc, impersonate_email=impersonate_email) from exc


def build_gmail_service(env: Mapping[str, str] | None = None) -> Any:
    impersonate_email = get_impersonate_email(env)
    service_account_info = load_service_account_info(env)
    return _build_service(
        service_account_info=service_account_info,
        impersonate_email=impersonate_email,
        scope=GMAIL_SEND_SCOPE,
    )


def get_gmail_service(config: GmailDwdConfig) -> Any:
    return _build_service(
        service_account_info=config.service_account_info,
        impersonate_email=config.impersonate_email,
        scope=config.scope,
    )


class GmailDwdClient:
    def __init__(self, *, config: GmailDwdConfig, service: Any | None = None) -> None:
        self.config = config
        self._service = service

    @property
    def service(self) -> Any:
        if self._service is None:
            self._service = get_gmail_service(self.config)
        return self._service

    def send_raw(self, raw_message: str) -> dict[str, Any]:
        try:
            response = (
                self.service.users()
                .messages()
                .send(userId="me", body={"raw": raw_message})
                .execute()
            )
            return dict(response or {})
        except Exception as exc:
            raise map_gmail_send_exception(exc, impersonate_email=self.config.impersonate_email) from exc
