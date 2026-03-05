from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

GOOGLE_DOC_PATTERN = re.compile(r"/document/d/([a-zA-Z0-9_-]{16,})")
GOOGLE_SHEET_PATTERN = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]{16,})")
GOOGLE_DRIVE_FILE_PATTERN = re.compile(r"/file/d/([a-zA-Z0-9_-]{16,})")
GA4_PROPERTIES_PATTERN = re.compile(r"/properties/(\d{4,})")
GA4_PROPERTY_SHORT_PATTERN = re.compile(r"/p(\d{4,})")
GENERIC_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
POSSIBLE_DRIVE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{16,}$")
POSSIBLE_GA4_PROPERTY_PATTERN = re.compile(r"^\d{4,}$")


@dataclass(frozen=True)
class GoogleResourceReference:
    resource_type: str
    resource_id: str
    canonical_url: str
    label: str

    def to_dict(self) -> dict[str, str]:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "canonical_url": self.canonical_url,
            "label": self.label,
        }


def _clean_url(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    return text.rstrip(").,;!?")


def _from_google_doc(url: str) -> GoogleResourceReference | None:
    match = GOOGLE_DOC_PATTERN.search(url)
    if not match:
        return None
    doc_id = match.group(1)
    return GoogleResourceReference(
        resource_type="google_doc",
        resource_id=doc_id,
        canonical_url=f"https://docs.google.com/document/d/{doc_id}/edit",
        label="Google Doc",
    )


def _from_google_sheet(url: str) -> GoogleResourceReference | None:
    match = GOOGLE_SHEET_PATTERN.search(url)
    if not match:
        return None
    spreadsheet_id = match.group(1)
    return GoogleResourceReference(
        resource_type="google_sheet",
        resource_id=spreadsheet_id,
        canonical_url=f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        label="Google Sheet",
    )


def _from_google_drive_file(url: str) -> GoogleResourceReference | None:
    match = GOOGLE_DRIVE_FILE_PATTERN.search(url)
    if not match:
        return None
    file_id = match.group(1)
    return GoogleResourceReference(
        resource_type="google_drive_file",
        resource_id=file_id,
        canonical_url=f"https://drive.google.com/file/d/{file_id}/view",
        label="Google Drive File",
    )


def _from_ga4_url(url: str) -> GoogleResourceReference | None:
    parsed = urlparse(url)
    path = parsed.path or ""
    fragment = parsed.fragment or ""
    query = parse_qs(parsed.query or "")

    for key in ("property_id", "propertyId", "property"):
        values = query.get(key) or []
        for value in values:
            token = str(value or "").strip()
            if POSSIBLE_GA4_PROPERTY_PATTERN.fullmatch(token):
                return GoogleResourceReference(
                    resource_type="ga4_property",
                    resource_id=token,
                    canonical_url=f"https://analytics.google.com/analytics/web/#/p{token}",
                    label="GA4 Property",
                )

    for matcher in (GA4_PROPERTIES_PATTERN, GA4_PROPERTY_SHORT_PATTERN):
        match = matcher.search(path) or matcher.search(fragment)
        if match:
            property_id = match.group(1)
            return GoogleResourceReference(
                resource_type="ga4_property",
                resource_id=property_id,
                canonical_url=f"https://analytics.google.com/analytics/web/#/p{property_id}",
                label="GA4 Property",
            )
    return None


def analyze_google_resource_reference(raw: Any) -> GoogleResourceReference | None:
    value = str(raw or "").strip()
    if not value:
        return None

    url = _clean_url(value)
    lowered = url.lower()
    if lowered.startswith("http://") or lowered.startswith("https://"):
        parsers = (
            _from_google_doc,
            _from_google_sheet,
            _from_google_drive_file,
            _from_ga4_url,
        )
        for parser in parsers:
            parsed = parser(url)
            if parsed is not None:
                return parsed
        return None

    if POSSIBLE_GA4_PROPERTY_PATTERN.fullmatch(value):
        return GoogleResourceReference(
            resource_type="ga4_property",
            resource_id=value,
            canonical_url=f"https://analytics.google.com/analytics/web/#/p{value}",
            label="GA4 Property",
        )
    if POSSIBLE_DRIVE_ID_PATTERN.fullmatch(value):
        return GoogleResourceReference(
            resource_type="google_drive_file",
            resource_id=value,
            canonical_url=f"https://drive.google.com/file/d/{value}/view",
            label="Google Drive File",
        )
    return None


def first_google_link(text: Any) -> str:
    joined = str(text or "")
    match = GENERIC_URL_PATTERN.search(joined)
    return _clean_url(match.group(0)) if match else ""


def normalize_link_aliases(raw: Any) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, dict[str, str]] = {}
    for key, value in list(raw.items())[:200]:
        alias = " ".join(str(key or "").split()).strip()
        if not alias:
            continue
        alias_key = alias.lower()
        if not isinstance(value, dict):
            continue
        resource_type = " ".join(str(value.get("resource_type") or "").split()).strip().lower()
        resource_id = " ".join(str(value.get("resource_id") or "").split()).strip()
        canonical_url = " ".join(str(value.get("canonical_url") or "").split()).strip()
        if not resource_type or not resource_id:
            continue
        normalized[alias_key] = {
            "alias": alias,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "canonical_url": canonical_url,
        }
    return normalized
