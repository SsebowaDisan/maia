from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def host_from_url(url: str) -> str:
    try:
        host = str(urlparse(str(url or "").strip()).hostname or "").strip().lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


def filter_sources_for_response_scope(
    *,
    sources: list[Any],
    settings: dict[str, Any],
) -> list[Any]:
    target_url = " ".join(str(settings.get("__task_target_url") or "").split()).strip()
    target_host = host_from_url(target_url)
    if not target_host:
        return sources
    scoped = [
        source
        for source in sources
        if not str(getattr(source, "url", "") or "").strip()
        or (
            host_from_url(str(getattr(source, "url", "") or "").strip()) == target_host
            or host_from_url(str(getattr(source, "url", "") or "").strip()).endswith(
                f".{target_host}"
            )
        )
    ]
    return scoped if scoped else sources
