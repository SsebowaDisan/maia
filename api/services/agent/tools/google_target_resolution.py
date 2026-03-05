from __future__ import annotations

import re
from typing import Any

from api.services.google.resource_links import (
    GoogleResourceReference,
    analyze_google_resource_reference,
    first_google_link,
    normalize_link_aliases,
)

_SPACE_RE = re.compile(r"\s+")


def _clean_text(value: Any) -> str:
    return _SPACE_RE.sub(" ", str(value or "").strip())


def _normalize_alias(value: Any) -> str:
    return _clean_text(value).lower()


def _aliases(settings: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    return normalize_link_aliases((settings or {}).get("agent.google_workspace_link_aliases"))


def _reference_from_alias_row(row: dict[str, str]) -> GoogleResourceReference | None:
    resource_type = _clean_text(row.get("resource_type")).lower()
    resource_id = _clean_text(row.get("resource_id"))
    canonical_url = _clean_text(row.get("canonical_url"))
    if not resource_type or not resource_id:
        return None
    return GoogleResourceReference(
        resource_type=resource_type,
        resource_id=resource_id,
        canonical_url=canonical_url,
        label=_clean_text(row.get("alias")) or resource_type,
    )


def _match_prompt_alias(
    *,
    prompt: str,
    settings: dict[str, Any] | None,
    allowed_types: set[str],
) -> GoogleResourceReference | None:
    prompt_text = _normalize_alias(prompt)
    if not prompt_text:
        return None
    alias_map = _aliases(settings)
    best: tuple[int, GoogleResourceReference] | None = None
    for alias_key, row in alias_map.items():
        if alias_key not in prompt_text:
            continue
        ref = _reference_from_alias_row(row)
        if ref is None or ref.resource_type not in allowed_types:
            continue
        length = len(alias_key)
        if best is None or length > best[0]:
            best = (length, ref)
    return best[1] if best is not None else None


def resolve_sheet_reference(
    *,
    prompt: str,
    params: dict[str, Any],
    settings: dict[str, Any] | None,
) -> GoogleResourceReference | None:
    spreadsheet_id = _clean_text(params.get("spreadsheet_id"))
    if spreadsheet_id:
        return GoogleResourceReference(
            resource_type="google_sheet",
            resource_id=spreadsheet_id,
            canonical_url=f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
            label="Google Sheet",
        )
    for key in ("spreadsheet_url", "sheet_url", "url", "link"):
        parsed = analyze_google_resource_reference(params.get(key))
        if parsed and parsed.resource_type in {"google_sheet"}:
            return parsed
    alias_map = _aliases(settings)
    for key in ("spreadsheet_alias", "alias"):
        alias_key = _normalize_alias(params.get(key))
        if not alias_key:
            continue
        row = alias_map.get(alias_key)
        if not row:
            continue
        ref = _reference_from_alias_row(row)
        if ref and ref.resource_type == "google_sheet":
            return ref
    prompt_link = first_google_link(prompt)
    parsed_prompt = analyze_google_resource_reference(prompt_link)
    if parsed_prompt and parsed_prompt.resource_type == "google_sheet":
        return parsed_prompt
    return _match_prompt_alias(
        prompt=prompt,
        settings=settings,
        allowed_types={"google_sheet"},
    )


def resolve_ga4_reference(
    *,
    prompt: str,
    params: dict[str, Any],
    settings: dict[str, Any] | None,
) -> GoogleResourceReference | None:
    property_id = _clean_text(params.get("property_id"))
    if property_id:
        parsed = analyze_google_resource_reference(property_id)
        if parsed is not None and parsed.resource_type == "ga4_property":
            return parsed
        if property_id.isdigit():
            return GoogleResourceReference(
                resource_type="ga4_property",
                resource_id=property_id,
                canonical_url=f"https://analytics.google.com/analytics/web/#/p{property_id}",
                label="GA4 Property",
            )
    for key in ("property_url", "url", "link"):
        parsed = analyze_google_resource_reference(params.get(key))
        if parsed and parsed.resource_type == "ga4_property":
            return parsed
    alias_map = _aliases(settings)
    for key in ("property_alias", "alias"):
        alias_key = _normalize_alias(params.get(key))
        if not alias_key:
            continue
        row = alias_map.get(alias_key)
        if not row:
            continue
        ref = _reference_from_alias_row(row)
        if ref and ref.resource_type == "ga4_property":
            return ref
    prompt_link = first_google_link(prompt)
    parsed_prompt = analyze_google_resource_reference(prompt_link)
    if parsed_prompt and parsed_prompt.resource_type == "ga4_property":
        return parsed_prompt
    return _match_prompt_alias(
        prompt=prompt,
        settings=settings,
        allowed_types={"ga4_property"},
    )
