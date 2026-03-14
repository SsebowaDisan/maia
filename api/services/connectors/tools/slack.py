"""B1-06 / B4-02 — Slack connector tools.

Tools: slack.send_message, slack.read_channel, slack.list_channels
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def _post_json(url: str, payload: dict, token: str, timeout: int = 30) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": exc.read().decode("utf-8", errors="ignore")[:300]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def _get_json(url: str, token: str, timeout: int = 30) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:300]}


def _slack_send_message(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    token = str(credentials.get("api_key") or credentials.get("access_token") or "")
    channel = str(params.get("channel") or "")
    text = str(params.get("text") or "")
    if not channel:
        raise ValueError("slack.send_message requires 'channel'.")
    return _post_json(
        "https://slack.com/api/chat.postMessage",
        {"channel": channel, "text": text},
        token,
        timeout_seconds,
    )


def _slack_read_channel(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    token = str(credentials.get("api_key") or credentials.get("access_token") or "")
    channel = str(params.get("channel") or "")
    limit = int(params.get("limit") or 20)
    if not channel:
        raise ValueError("slack.read_channel requires 'channel'.")
    return _get_json(
        f"https://slack.com/api/conversations.history?channel={channel}&limit={limit}",
        token,
        timeout_seconds,
    )


def _slack_list_channels(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    token = str(credentials.get("api_key") or credentials.get("access_token") or "")
    limit = int(params.get("limit") or 100)
    return _get_json(
        f"https://slack.com/api/conversations.list?limit={limit}",
        token,
        timeout_seconds,
    )


def register(registry: dict) -> None:
    registry["slack.send_message"] = _slack_send_message
    registry["slack.read_channel"] = _slack_read_channel
    registry["slack.list_channels"] = _slack_list_channels
