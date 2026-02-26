from __future__ import annotations

import base64
from email import policy
from email.parser import BytesParser
from unittest.mock import MagicMock, patch

import pytest

from maia.integrations.gmail_dwd.client import GmailDwdClient, get_gmail_service
from maia.integrations.gmail_dwd.config import GmailDwdConfig, load_gmail_dwd_config
from maia.integrations.gmail_dwd.errors import GmailDwdConfigError
from maia.integrations.gmail_dwd.mime_builder import build_rfc2822_message, encode_base64url


def _sample_config() -> GmailDwdConfig:
    return GmailDwdConfig(
        service_account_info={
            "type": "service_account",
            "client_email": "svc-account@example.iam.gserviceaccount.com",
            "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        impersonate_email="disan@micrurus.com",
        from_email="disan@micrurus.com",
    )


def test_build_rfc2822_message_contains_headers_alternative_and_attachment() -> None:
    message_bytes = build_rfc2822_message(
        from_email="disan@micrurus.com",
        to_email="ssebowadisan1@gmail.com",
        subject="Maia DWD Test",
        body_text="Plain text body",
        body_html="<p><strong>HTML body</strong></p>",
        attachments=[("report.txt", b"test attachment", "text/plain")],
    )
    parsed = BytesParser(policy=policy.default).parsebytes(message_bytes)

    assert parsed["From"] == "disan@micrurus.com"
    assert parsed["To"] == "ssebowadisan1@gmail.com"
    assert parsed["Subject"] == "Maia DWD Test"
    assert parsed["Date"]
    assert parsed["Message-ID"]
    assert parsed.is_multipart()

    parts = list(parsed.walk())
    plain_parts = [p for p in parts if p.get_content_type() == "text/plain" and p.get_filename() is None]
    html_parts = [p for p in parts if p.get_content_type() == "text/html"]
    attachments = [p for p in parts if p.get_filename() == "report.txt"]

    assert plain_parts
    assert html_parts
    assert attachments


def test_encode_base64url_round_trip() -> None:
    raw = b"maia-gmail-dwd:+/="
    encoded = encode_base64url(raw)
    decoded = base64.urlsafe_b64decode(encoded.encode("utf-8"))
    assert decoded == raw


def test_get_gmail_service_uses_delegated_credentials() -> None:
    config = _sample_config()
    base_credentials = MagicMock()
    delegated_credentials = MagicMock()
    base_credentials.with_subject.return_value = delegated_credentials

    fake_service_account = MagicMock()
    fake_service_account.Credentials.from_service_account_info.return_value = base_credentials

    with (
        patch("maia.integrations.gmail_dwd.client.service_account", fake_service_account),
        patch("maia.integrations.gmail_dwd.client.gmail_discovery_build", return_value="gmail-service") as build_mock,
    ):
        service = get_gmail_service(config)

    assert service == "gmail-service"
    fake_service_account.Credentials.from_service_account_info.assert_called_once_with(
        config.service_account_info,
        scopes=[config.scope],
    )
    base_credentials.with_subject.assert_called_once_with("disan@micrurus.com")
    build_mock.assert_called_once_with(
        "gmail",
        "v1",
        credentials=delegated_credentials,
        cache_discovery=False,
    )


def test_client_send_raw_calls_gmail_api_with_expected_payload_shape() -> None:
    config = _sample_config()
    service = MagicMock()
    send_mock = service.users.return_value.messages.return_value.send
    send_mock.return_value.execute.return_value = {"id": "msg-123", "threadId": "thr-1"}

    client = GmailDwdClient(config=config, service=service)
    response = client.send_raw("abc123")

    send_mock.assert_called_once_with(userId="me", body={"raw": "abc123"})
    assert response["id"] == "msg-123"
    assert response["threadId"] == "thr-1"


def test_load_config_requires_absolute_sa_json_path() -> None:
    with pytest.raises(GmailDwdConfigError) as exc_info:
        load_gmail_dwd_config({"MAIA_GMAIL_SA_JSON_PATH": "relative/service-account.json"})
    assert exc_info.value.code == "gmail_dwd_sa_path_not_absolute"
