from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlparse


def _normalize_host(url: str) -> str:
    try:
        host = str(urlparse(str(url or "").strip()).hostname or "").strip().lower()
    except Exception:
        host = ""
    return host


def _parse_domain_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        items = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return []
        items = [part.strip() for part in text.replace(";", ",").split(",")]
    domains: list[str] = []
    for item in items:
        domain = str(item or "").strip().lower()
        if not domain:
            continue
        if domain.startswith("*."):
            domain = domain[2:]
        if domain and domain not in domains:
            domains.append(domain)
    return domains[:80]


def _parse_headers(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        candidate = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            candidate = parsed if isinstance(parsed, dict) else {}
        except Exception:
            candidate = {}
    else:
        candidate = {}
    headers: dict[str, str] = {}
    for key, value in candidate.items():
        header_key = " ".join(str(key or "").split()).strip()[:120]
        header_value = " ".join(str(value or "").split()).strip()[:320]
        if not header_key or not header_value:
            continue
        headers[header_key] = header_value
        if len(headers) >= 16:
            break
    return headers


def _parse_cookies(raw: Any, *, host: str, secure: bool) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        candidate = raw
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            candidate = parsed if isinstance(parsed, list) else []
        except Exception:
            candidate = []
    else:
        candidate = []
    cookies: list[dict[str, Any]] = []
    for row in candidate:
        if not isinstance(row, dict):
            continue
        name = " ".join(str(row.get("name") or "").split()).strip()[:120]
        value = str(row.get("value") or "")[:2048]
        if not name or value == "":
            continue
        domain = " ".join(str(row.get("domain") or host).split()).strip().lower()[:180]
        if not domain:
            continue
        cookie = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": " ".join(str(row.get("path") or "/").split()).strip() or "/",
            "secure": bool(row.get("secure")) if "secure" in row else secure,
            "httpOnly": bool(row.get("httpOnly")),
        }
        expires = row.get("expires")
        if isinstance(expires, (int, float)) and float(expires) > 0:
            cookie["expires"] = float(expires)
        cookies.append(cookie)
        if len(cookies) >= 20:
            break
    return cookies


def build_trusted_site_overrides(*, settings: dict[str, Any], url: str) -> dict[str, Any]:
    safe_settings = settings if isinstance(settings, dict) else {}
    host = _normalize_host(url)
    if not host:
        return {"trusted": False, "host": "", "headers": {}, "cookies": []}
    configured_domains = (
        safe_settings.get("browser.trusted_site_domains")
        or safe_settings.get("trusted_site_domains")
        or os.getenv("MAIA_TRUSTED_SITE_DOMAINS", "")
    )
    domains = _parse_domain_list(configured_domains)
    trusted = any(host == domain or host.endswith(f".{domain}") for domain in domains)
    if not trusted:
        return {"trusted": False, "host": host, "headers": {}, "cookies": []}
    raw_headers = (
        safe_settings.get("browser.trusted_site_headers")
        or safe_settings.get("trusted_site_headers")
        or os.getenv("MAIA_TRUSTED_SITE_HEADERS_JSON", "")
    )
    headers = _parse_headers(raw_headers)
    raw_cookies = (
        safe_settings.get("browser.trusted_site_cookies")
        or safe_settings.get("trusted_site_cookies")
        or os.getenv("MAIA_TRUSTED_SITE_COOKIES_JSON", "")
    )
    secure = str(urlparse(str(url or "")).scheme).lower() == "https"
    cookies = _parse_cookies(raw_cookies, host=host, secure=secure)
    return {
        "trusted": True,
        "host": host,
        "headers": headers,
        "cookies": cookies,
    }


__all__ = ["build_trusted_site_overrides"]
