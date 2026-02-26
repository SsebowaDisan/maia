from __future__ import annotations

import base64
import json

import pytest

from maia.integrations.gmail_dwd.config import (
    get_from_email,
    get_impersonate_email,
    load_service_account_info,
)
from maia.integrations.gmail_dwd.errors import GmailDwdConfigError


def _sample_service_account_info() -> dict[str, str]:
    return {
        "type": "service_account",
        "client_email": "mailer@example.iam.gserviceaccount.com",
        "private_key": "-----BEGIN PRIVATE KEY-----\nfake\n-----END PRIVATE KEY-----\n",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def test_load_service_account_info_from_b64() -> None:
    payload = _sample_service_account_info()
    encoded = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")

    loaded = load_service_account_info({"MAIA_GMAIL_SA_JSON_B64": encoded})

    assert loaded["type"] == "service_account"
    assert loaded["client_email"] == payload["client_email"]


def test_load_service_account_info_raises_on_invalid_b64() -> None:
    with pytest.raises(GmailDwdConfigError) as exc_info:
        load_service_account_info({"MAIA_GMAIL_SA_JSON_B64": "not-base64%%"})
    assert exc_info.value.code == "gmail_dwd_sa_b64_invalid"


def test_load_service_account_info_raises_on_invalid_json() -> None:
    encoded = base64.b64encode(b'{"type":').decode("utf-8")
    with pytest.raises(GmailDwdConfigError) as exc_info:
        load_service_account_info({"MAIA_GMAIL_SA_JSON_B64": encoded})
    assert exc_info.value.code == "gmail_dwd_sa_b64_invalid_json"


def test_load_service_account_info_prefers_b64_over_path(tmp_path) -> None:
    file_payload = _sample_service_account_info()
    file_payload["client_email"] = "from-path@example.iam.gserviceaccount.com"
    sa_path = tmp_path / "sa.json"
    sa_path.write_text(json.dumps(file_payload), encoding="utf-8")

    b64_payload = _sample_service_account_info()
    b64_payload["client_email"] = "from-b64@example.iam.gserviceaccount.com"
    encoded = base64.b64encode(json.dumps(b64_payload).encode("utf-8")).decode("utf-8")

    loaded = load_service_account_info(
        {
            "MAIA_GMAIL_SA_JSON_B64": encoded,
            "MAIA_GMAIL_SA_JSON_PATH": str(sa_path.resolve()),
        }
    )
    assert loaded["client_email"] == "from-b64@example.iam.gserviceaccount.com"


def test_get_sender_defaults_to_impersonate() -> None:
    env = {"MAIA_GMAIL_IMPERSONATE": "disan@micrurus.com"}
    assert get_impersonate_email(env) == "disan@micrurus.com"
    assert get_from_email(env) == "disan@micrurus.com"
