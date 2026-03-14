"""B1-06 — Notion connector tools.

Tools: notion.read_page, notion.create_page, notion.update_page
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

_NOTION_VERSION = "2022-06-28"


def _headers(credentials: dict) -> dict[str, str]:
    token = str(credentials.get("api_key") or credentials.get("access_token") or "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": _NOTION_VERSION,
    }


def _get(url: str, creds: dict, timeout: int) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=_headers(creds))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "data": json.loads(resp.read()), "error": None}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "data": None, "error": exc.read().decode("utf-8", errors="ignore")[:300]}
    except Exception as exc:
        return {"status": 0, "data": None, "error": str(exc)[:300]}


def _patch(url: str, body: dict, creds: dict, timeout: int) -> dict[str, Any]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={**_headers(creds), "Content-Type": "application/json"}, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "data": json.loads(resp.read()), "error": None}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "data": None, "error": exc.read().decode("utf-8", errors="ignore")[:300]}
    except Exception as exc:
        return {"status": 0, "data": None, "error": str(exc)[:300]}


def _post(url: str, body: dict, creds: dict, timeout: int) -> dict[str, Any]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(creds), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "data": json.loads(resp.read()), "error": None}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "data": None, "error": exc.read().decode("utf-8", errors="ignore")[:300]}
    except Exception as exc:
        return {"status": 0, "data": None, "error": str(exc)[:300]}


def _notion_read_page(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    page_id = str(params.get("page_id") or "")
    if not page_id:
        raise ValueError("notion.read_page requires 'page_id'.")
    return _get(f"https://api.notion.com/v1/pages/{page_id}", credentials, timeout_seconds)


def _notion_create_page(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    parent_id = str(params.get("parent_id") or "")
    title = str(params.get("title") or "Untitled")
    content = str(params.get("content") or "")
    if not parent_id:
        raise ValueError("notion.create_page requires 'parent_id'.")
    body = {
        "parent": {"page_id": parent_id},
        "properties": {"title": {"title": [{"text": {"content": title}}]}},
        "children": [{"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": [{"text": {"content": content}}]}}] if content else [],
    }
    return _post("https://api.notion.com/v1/pages", body, credentials, timeout_seconds)


def _notion_update_page(params: dict, credentials: dict, timeout_seconds: int = 30, **_kw: Any) -> dict:
    page_id = str(params.get("page_id") or "")
    properties = dict(params.get("properties") or {})
    if not page_id:
        raise ValueError("notion.update_page requires 'page_id'.")
    return _patch(f"https://api.notion.com/v1/pages/{page_id}", {"properties": properties}, credentials, timeout_seconds)


def register(registry: dict) -> None:
    registry["notion.read_page"] = _notion_read_page
    registry["notion.create_page"] = _notion_create_page
    registry["notion.update_page"] = _notion_update_page
