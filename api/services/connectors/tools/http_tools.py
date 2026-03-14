"""HTTP connector tool handlers — http.get and http.post.

Responsibility: generic HTTP request tools, no auth required.
These are the simplest built-in tools and serve as the reference
implementation for the handler interface.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _make_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    final_headers = dict(headers or {})
    if body is not None:
        final_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=body, method=method.upper(), headers=final_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")[:400]
        return {"status": exc.code, "error": detail, "data": None}
    except Exception as exc:
        return {"status": 0, "error": str(exc)[:300], "data": None}

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        data = raw.decode("utf-8", errors="replace")[:4000]

    return {"status": status, "data": data, "error": None}


def _http_get(params: dict[str, Any], credentials: dict[str, Any], timeout_seconds: int, **_kw: Any) -> dict[str, Any]:
    url = str(params.get("url") or "").strip()
    if not url:
        raise ValueError("http.get requires 'url' parameter.")
    raw_headers = params.get("headers") or {}
    headers = {str(k): str(v) for k, v in raw_headers.items()} if isinstance(raw_headers, dict) else {}
    return _make_request("GET", url, headers=headers, timeout_seconds=timeout_seconds)


def _http_post(params: dict[str, Any], credentials: dict[str, Any], timeout_seconds: int, **_kw: Any) -> dict[str, Any]:
    url = str(params.get("url") or "").strip()
    if not url:
        raise ValueError("http.post requires 'url' parameter.")
    body_obj = params.get("body") or {}
    body = json.dumps(body_obj).encode()
    raw_headers = params.get("headers") or {}
    headers = {str(k): str(v) for k, v in raw_headers.items()} if isinstance(raw_headers, dict) else {}
    return _make_request("POST", url, headers=headers, body=body, timeout_seconds=timeout_seconds)


def register(registry: dict) -> None:
    """Register all HTTP tool handlers into the provided registry dict."""
    registry["http.get"] = _http_get
    registry["http.post"] = _http_post
