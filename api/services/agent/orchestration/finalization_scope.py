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


def _metadata(source: Any) -> dict[str, Any]:
    payload = getattr(source, "metadata", None)
    return payload if isinstance(payload, dict) else {}


def _is_workspace_source(source: Any) -> bool:
    label = " ".join(str(getattr(source, "label", "") or "").split()).strip().lower()
    if label.startswith(("workspace.", "google sheets", "google docs")):
        return True
    metadata = _metadata(source)
    provider = " ".join(str(metadata.get("provider") or "").split()).strip().lower()
    if provider in {
        "google_sheets",
        "google_docs",
        "workspace_sheets",
        "workspace_docs",
        "workspace_tracker",
    }:
        return True
    source_url = " ".join(str(getattr(source, "url", "") or "").split()).strip().lower()
    if source_url and ("docs.google.com/spreadsheets" in source_url or "docs.google.com/document" in source_url):
        return True
    return False


def _workspace_sources_allowed(settings: dict[str, Any]) -> bool:
    if bool(settings.get("__include_workspace_sources_in_response")):
        return True
    intent_tags_raw = settings.get("__intent_tags")
    intent_tags = (
        {str(item).strip().lower() for item in intent_tags_raw if str(item).strip()}
        if isinstance(intent_tags_raw, list)
        else set()
    )
    return bool(intent_tags.intersection({"docs_write", "sheets_update"}))


def filter_sources_for_response_scope(
    *,
    sources: list[Any],
    settings: dict[str, Any],
) -> list[Any]:
    scoped_sources = list(sources or [])
    if not _workspace_sources_allowed(settings):
        scoped_sources = [source for source in scoped_sources if not _is_workspace_source(source)]

    target_url = " ".join(str(settings.get("__task_target_url") or "").split()).strip()
    target_host = host_from_url(target_url)
    if not target_host:
        return scoped_sources
    scoped = [
        source
        for source in scoped_sources
        if not str(getattr(source, "url", "") or "").strip()
        or (
            host_from_url(str(getattr(source, "url", "") or "").strip()) == target_host
            or host_from_url(str(getattr(source, "url", "") or "").strip()).endswith(
                f".{target_host}"
            )
        )
    ]
    return scoped if scoped else scoped_sources
