from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .errors import GmailDwdConfigError

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
DEFAULT_IMPERSONATE = "disan@micrurus.com"
SERVICE_ACCOUNT_REQUIRED_FIELDS = ("type", "client_email", "private_key", "token_uri")

_DOTENV_LOADED = False


@dataclass(frozen=True)
class GmailDwdConfig:
    service_account_info: dict[str, Any]
    impersonate_email: str
    from_email: str
    scope: str = GMAIL_SEND_SCOPE


def _load_dotenv_if_present() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    try:
        from dotenv import load_dotenv
    except Exception:
        _DOTENV_LOADED = True
        return

    candidates = [Path.cwd() / ".env"]
    try:
        candidates.append(Path(__file__).resolve().parents[5] / ".env")
    except Exception:
        pass

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists() and candidate.is_file():
            load_dotenv(dotenv_path=candidate, override=False)
            _DOTENV_LOADED = True
            break


def _resolve_env(env: Mapping[str, str] | None = None) -> Mapping[str, str]:
    if env is not None:
        return env
    _load_dotenv_if_present()
    return os.environ


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise GmailDwdConfigError(
            f"Service account JSON file was not found: {path}",
            code="gmail_dwd_sa_file_missing",
        )
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise GmailDwdConfigError(
            f"Failed to parse service account JSON file: {path}",
            code="gmail_dwd_sa_file_invalid_json",
        ) from exc
    if not isinstance(loaded, dict):
        raise GmailDwdConfigError(
            "Service account JSON must be an object.",
            code="gmail_dwd_sa_file_invalid",
        )
    return loaded


def _read_json_b64(value: str) -> dict[str, Any]:
    compact_value = "".join(value.split())
    try:
        decoded = base64.b64decode(compact_value.encode("utf-8"), validate=True)
    except Exception as exc:
        raise GmailDwdConfigError(
            "MAIA_GMAIL_SA_JSON_B64 is not valid base64.",
            code="gmail_dwd_sa_b64_invalid",
        ) from exc
    try:
        loaded = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise GmailDwdConfigError(
            "MAIA_GMAIL_SA_JSON_B64 does not decode to valid JSON.",
            code="gmail_dwd_sa_b64_invalid_json",
        ) from exc
    if not isinstance(loaded, dict):
        raise GmailDwdConfigError(
            "MAIA_GMAIL_SA_JSON_B64 must decode to a JSON object.",
            code="gmail_dwd_sa_b64_invalid",
        )
    return loaded


def _validate_service_account_info(info: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in SERVICE_ACCOUNT_REQUIRED_FIELDS if not str(info.get(field) or "").strip()]
    if missing:
        raise GmailDwdConfigError(
            "Service account JSON is missing required fields: " + ", ".join(missing),
            code="gmail_dwd_sa_missing_fields",
        )
    return info


def load_service_account_info(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    values = _resolve_env(env)
    sa_json_b64 = str(values.get("MAIA_GMAIL_SA_JSON_B64") or "").strip()
    sa_json_path = str(values.get("MAIA_GMAIL_SA_JSON_PATH") or "").strip()

    if sa_json_b64:
        return _validate_service_account_info(_read_json_b64(sa_json_b64))
    if sa_json_path:
        json_path = Path(sa_json_path)
        if not json_path.is_absolute():
            raise GmailDwdConfigError(
                "MAIA_GMAIL_SA_JSON_PATH must be an absolute path.",
                code="gmail_dwd_sa_path_not_absolute",
            )
        return _validate_service_account_info(_read_json_file(json_path))
    raise GmailDwdConfigError(
        "Missing Gmail DWD credentials. Set MAIA_GMAIL_SA_JSON_PATH or MAIA_GMAIL_SA_JSON_B64.",
        code="gmail_dwd_sa_missing",
    )


def get_impersonate_email(env: Mapping[str, str] | None = None) -> str:
    values = _resolve_env(env)
    impersonate_email = str(values.get("MAIA_GMAIL_IMPERSONATE") or DEFAULT_IMPERSONATE).strip()
    if not impersonate_email:
        raise GmailDwdConfigError(
            "MAIA_GMAIL_IMPERSONATE must not be empty.",
            code="gmail_dwd_impersonate_missing",
        )
    return impersonate_email


def get_from_email(env: Mapping[str, str] | None = None) -> str:
    values = _resolve_env(env)
    from_email = str(values.get("MAIA_GMAIL_FROM") or "").strip()
    if not from_email:
        from_email = get_impersonate_email(values)
    if not from_email:
        raise GmailDwdConfigError(
            "MAIA_GMAIL_FROM must not be empty.",
            code="gmail_dwd_from_missing",
        )
    return from_email


def load_gmail_dwd_config(env: Mapping[str, str] | None = None) -> GmailDwdConfig:
    values = _resolve_env(env)
    info = load_service_account_info(values)
    impersonate_email = get_impersonate_email(values)
    from_email = get_from_email(values)

    return GmailDwdConfig(
        service_account_info=info,
        impersonate_email=impersonate_email,
        from_email=from_email,
    )
