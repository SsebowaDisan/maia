from __future__ import annotations

import re
from typing import Any


def compact(text: str, max_len: int = 140) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= max_len else f"{clean[: max_len - 1].rstrip()}..."


def truncate_text(text: str, max_len: int = 1800) -> str:
    raw = str(text or "")
    return raw if len(raw) <= max_len else f"{raw[: max_len - 1].rstrip()}..."


def chunk_preserve_text(text: str, chunk_size: int = 220, limit: int = 8) -> list[str]:
    if not text:
        return []
    size = max(48, int(chunk_size or 220))
    chunks = [text[idx : idx + size] for idx in range(0, len(text), size)]
    return chunks[: max(1, int(limit or 8))]


def truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def extract_action_artifact_metadata(data: dict[str, Any] | None, *, step: int) -> dict[str, Any]:
    metadata: dict[str, Any] = {"step": step}
    if not isinstance(data, dict):
        return metadata
    for key in (
        "url",
        "document_url",
        "spreadsheet_url",
        "path",
        "pdf_path",
        "document_id",
        "spreadsheet_id",
    ):
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        metadata[key] = text[:320]
    copied = data.get("copied_snippets")
    if isinstance(copied, list):
        cleaned = [str(item).strip() for item in copied if str(item).strip()]
        if cleaned:
            metadata["copied_snippets"] = cleaned[:4]
    return metadata


EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def extract_first_email(*chunks: str) -> str:
    joined = " ".join(
        str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip()
    )
    match = EMAIL_RE.search(joined)
    return match.group(1).strip() if match else ""


def issue_fix_hint(issue: str) -> str:
    text = str(issue or "").lower()
    if "gmail_dwd_api_disabled" in text or "gmail api is not enabled" in text:
        return (
            "Enable Gmail API in the Google Cloud project used by the service account, "
            "then retry."
        )
    if "gmail_dwd_delegation_denied" in text or "domain-wide delegation" in text:
        return (
            "Verify Workspace Domain-Wide Delegation for the service-account client ID and "
            "scope `https://www.googleapis.com/auth/gmail.send`."
        )
    if "gmail_dwd_mailbox_unavailable" in text or (
        "mailbox" in text and "suspended" in text
    ):
        return "Confirm the impersonated mailbox exists and is active in Google Workspace."
    if "required role" in text and "admin" in text:
        return (
            "Switch to Company Agent > Full Access for this run, "
            "or set `agent.user_role` to `admin`/`owner`."
        )
    if (
        "google_api_http_error" in text
        or "invalid authentication credentials" in text
        or "oauth" in text
        or "refresh_token" in text
    ):
        return "Reconnect Google OAuth in Settings and verify required scopes, then retry."
    return ""
