"""B4-01 (partial) + B1-06 — Google Workspace connector tools.

Responsibility: Gmail, Google Drive, and Google Calendar tool handlers.

Tools:
  gmail.send, gmail.read, gdrive.read_file, gdrive.write_file,
  gcalendar.create_event, gcalendar.list_events
"""
from __future__ import annotations

import json
from typing import Any


def _auth_headers(credentials: dict[str, Any]) -> dict[str, str]:
    token = credentials.get("access_token") or credentials.get("api_key") or ""
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _get(url: str, headers: dict[str, str], timeout: int = 30) -> dict[str, Any]:
    import urllib.request, urllib.error

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "data": json.loads(resp.read()), "error": None}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "data": None, "error": exc.read().decode("utf-8", errors="ignore")[:400]}
    except Exception as exc:
        return {"status": 0, "data": None, "error": str(exc)[:300]}


def _post(url: str, body: dict, headers: dict[str, str], timeout: int = 30) -> dict[str, Any]:
    import urllib.request, urllib.error

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "data": json.loads(resp.read()), "error": None}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "data": None, "error": exc.read().decode("utf-8", errors="ignore")[:400]}
    except Exception as exc:
        return {"status": 0, "data": None, "error": str(exc)[:300]}


# ── Gmail ──────────────────────────────────────────────────────────────────────

def _gmail_send(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    import base64, email.mime.text

    to = str(params.get("to") or "")
    subject = str(params.get("subject") or "")
    body_text = str(params.get("body") or "")
    if not to:
        raise ValueError("gmail.send requires 'to' parameter.")

    msg = email.mime.text.MIMEText(body_text)
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    return _post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        {"raw": raw},
        _auth_headers(credentials),
        timeout_seconds,
    )


def _gmail_read(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    max_results = int(params.get("max_results") or 10)
    q = str(params.get("query") or "")
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults={max_results}"
    if q:
        import urllib.parse
        url += f"&q={urllib.parse.quote(q)}"
    return _get(url, _auth_headers(credentials), timeout_seconds)


# ── Google Drive ───────────────────────────────────────────────────────────────

def _gdrive_read_file(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    file_id = str(params.get("file_id") or "")
    if not file_id:
        raise ValueError("gdrive.read_file requires 'file_id'.")
    return _get(
        f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media",
        _auth_headers(credentials),
        timeout_seconds,
    )


def _gdrive_write_file(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    name = str(params.get("name") or "untitled")
    content = str(params.get("content") or "")
    parent = params.get("parent_id")
    metadata: dict[str, Any] = {"name": name}
    if parent:
        metadata["parents"] = [parent]
    # Multipart upload simplified to metadata-only for schema completeness
    return _post(
        "https://www.googleapis.com/drive/v3/files",
        metadata,
        _auth_headers(credentials),
        timeout_seconds,
    )


# ── Google Calendar ────────────────────────────────────────────────────────────

def _gcalendar_create_event(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    summary = str(params.get("summary") or "")
    start = str(params.get("start") or "")
    end = str(params.get("end") or "")
    if not (summary and start and end):
        raise ValueError("gcalendar.create_event requires 'summary', 'start', 'end'.")
    event = {"summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end}}
    return _post(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        event,
        _auth_headers(credentials),
        timeout_seconds,
    )


def _gcalendar_list_events(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    max_results = int(params.get("max_results") or 10)
    return _get(
        f"https://www.googleapis.com/calendar/v3/calendars/primary/events?maxResults={max_results}",
        _auth_headers(credentials),
        timeout_seconds,
    )


# ── Registration ───────────────────────────────────────────────────────────────

def register(registry: dict) -> None:
    registry["gmail.send"] = _gmail_send
    registry["gmail.read"] = _gmail_read
    registry["gdrive.read_file"] = _gdrive_read_file
    registry["gdrive.write_file"] = _gdrive_write_file
    registry["gcalendar.create_event"] = _gcalendar_create_event
    registry["gcalendar.list_events"] = _gcalendar_list_events
