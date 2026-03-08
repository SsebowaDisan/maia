from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse


def normalize_url_for_match(value: str, *, keep_query: bool = True) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    scheme = str(parsed.scheme or "").strip().lower()
    if scheme not in {"http", "https"}:
        return ""
    host = str(parsed.hostname or "").strip().lower()
    if not host:
        return ""
    try:
        port = parsed.port
    except Exception:
        port = None
    default_port = 80 if scheme == "http" else 443
    netloc = host if not port or port == default_port else f"{host}:{port}"
    path = str(parsed.path or "/").strip() or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    query = str(parsed.query or "").strip() if keep_query else ""
    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    if normalized.endswith("/") and path == "/" and not query:
        return normalized[:-1]
    return normalized


def url_signatures(value: str) -> set[str]:
    full = normalize_url_for_match(value, keep_query=True)
    if not full:
        return set()
    parsed = urlparse(full)
    base = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    if base.endswith("/") and parsed.path == "/":
        base = base[:-1]
    signatures = {full.lower(), base.lower()}
    if parsed.path in {"", "/"} and not parsed.query:
        signatures.add(f"{parsed.scheme}://{parsed.netloc}/".lower())
    return {item for item in signatures if item}


def source_url_candidates(source: Any) -> list[str]:
    values: list[str] = []
    name_value = str(getattr(source, "name", "") or "").strip()
    if name_value:
        values.append(name_value)
    path_value = str(getattr(source, "path", "") or "").strip()
    if path_value.startswith("http://") or path_value.startswith("https://"):
        values.append(path_value)
    note = getattr(source, "note", None)
    if isinstance(note, dict):
        for key in (
            "source_url",
            "url",
            "page_url",
            "canonical_url",
            "original_url",
            "link",
        ):
            value = str(note.get(key, "") or "").strip()
            if value:
                values.append(value)
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def match_requested_urls_to_sources(
    requested_urls: list[str],
    source_rows: list[Any],
) -> tuple[dict[str, list[str]], list[str]]:
    ordered_urls: list[str] = []
    requested_signatures: dict[str, set[str]] = {}
    for raw_url in requested_urls:
        value = str(raw_url or "").strip()
        if not value or value in requested_signatures:
            continue
        signatures = url_signatures(value)
        if not signatures:
            continue
        requested_signatures[value] = signatures
        ordered_urls.append(value)

    matched: dict[str, set[str]] = {url: set() for url in ordered_urls}
    for source in source_rows:
        source_id = str(getattr(source, "id", "") or "").strip()
        if not source_id:
            continue
        source_signatures: set[str] = set()
        for candidate in source_url_candidates(source):
            source_signatures.update(url_signatures(candidate))
        if not source_signatures:
            continue
        for raw_url, signatures in requested_signatures.items():
            if signatures.intersection(source_signatures):
                matched[raw_url].add(source_id)

    unresolved = [url for url in ordered_urls if not matched[url]]
    resolved = {
        url: sorted(source_ids)
        for url, source_ids in matched.items()
        if source_ids
    }
    return resolved, unresolved
