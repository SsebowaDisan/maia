"""HTTP Request node — makes outbound HTTP calls.

step_config:
    url: str           — target URL (supports {input_key} interpolation)
    method: str        — GET, POST, PUT, DELETE, PATCH (default GET)
    headers: dict      — optional request headers
    body: dict | str   — optional JSON body (POST/PUT/PATCH)
    timeout_s: int     — request timeout (default 30)
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import httpx

from api.schemas.workflow_definition import WorkflowStep
from api.services.workflows.nodes import register

logger = logging.getLogger(__name__)

_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MB cap on response body

# Blocked hostnames and IP ranges (SSRF protection)
_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "169.254.169.254"}
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),        # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),       # IPv6 link-local
]


def _check_ssrf(url: str) -> None:
    """Block requests to internal/private IP ranges and metadata endpoints."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().strip()

    if not hostname:
        raise ValueError("URL has no hostname")

    if hostname in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Blocked hostname: {hostname}")

    # Try to resolve as IP and check against blocked ranges
    try:
        addr = ipaddress.ip_address(hostname)
        for network in _BLOCKED_NETWORKS:
            if addr in network:
                raise ValueError(f"Blocked IP range: {hostname}")
    except ValueError as exc:
        if "Blocked" in str(exc):
            raise
        # hostname is a DNS name, not a raw IP — allow (DNS rebinding is a
        # known limitation; full protection requires a custom DNS resolver)


@register("http_request")
def handle_http_request(
    step: WorkflowStep,
    inputs: dict[str, Any],
    on_event: Optional[Callable] = None,
) -> Any:
    cfg = step.step_config
    url = _interpolate(cfg.get("url", ""), inputs)
    method = cfg.get("method", "GET").upper()
    headers = cfg.get("headers", {})
    body = cfg.get("body")
    timeout = cfg.get("timeout_s", 30)

    if not url:
        raise ValueError(f"Step {step.step_id}: http_request requires 'url' in step_config")

    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        raise ValueError(f"Step {step.step_id}: unsupported HTTP method '{method}'")

    _check_ssrf(url)

    # Interpolate body if it's a string template
    if isinstance(body, str):
        body = _interpolate(body, inputs)
    elif isinstance(body, dict):
        body = {k: _interpolate(str(v), inputs) if isinstance(v, str) else v for k, v in body.items()}

    with httpx.Client(timeout=timeout, max_redirects=5) as client:
        if method in ("POST", "PUT", "PATCH") and body:
            resp = client.request(method, url, headers=headers, json=body if isinstance(body, dict) else None,
                                  content=body if isinstance(body, str) else None)
        else:
            resp = client.request(method, url, headers=headers)

    # Check response size before reading body
    content_length = resp.headers.get("content-length")
    if content_length and int(content_length) > _MAX_RESPONSE_BYTES:
        raise ValueError(f"Step {step.step_id}: response too large ({content_length} bytes)")

    if not resp.is_success:
        return {
            "status_code": resp.status_code,
            "error": resp.text[:2000],
            "success": False,
        }

    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        return resp.text[:_MAX_RESPONSE_BYTES]


def _interpolate(template: str, inputs: dict[str, Any]) -> str:
    """Replace {key} placeholders with input values."""
    def replacer(m: re.Match) -> str:
        key = m.group(1)
        return str(inputs.get(key, m.group(0)))
    return re.sub(r"\{(\w+)\}", replacer, template)
