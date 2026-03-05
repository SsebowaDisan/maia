from __future__ import annotations

from typing import Iterable

BASE_PROFILE_SCOPES: tuple[str, ...] = (
    "openid",
    "email",
    "profile",
)

TOOL_SCOPE_MAP: dict[str, tuple[str, ...]] = {
    "gmail": (
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
    ),
    "google_calendar": (
        "https://www.googleapis.com/auth/calendar.events",
    ),
    "google_workspace": (
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/spreadsheets",
    ),
    "google_analytics": (
        "https://www.googleapis.com/auth/analytics.readonly",
    ),
}

CONNECTOR_SCOPE_MAP: dict[str, tuple[str, ...]] = {
    "gmail": TOOL_SCOPE_MAP["gmail"],
    "google_calendar": TOOL_SCOPE_MAP["google_calendar"],
    "google_workspace": TOOL_SCOPE_MAP["google_workspace"],
    "google_analytics": TOOL_SCOPE_MAP["google_analytics"],
}

DEFAULT_TOOL_IDS: tuple[str, ...] = tuple(TOOL_SCOPE_MAP.keys())
KNOWN_GMAIL_SUPER_SCOPE = "https://mail.google.com/"

GOOGLE_OAUTH_SERVICE_SCOPE_MAP: dict[str, tuple[str, ...]] = {
    "gmail": TOOL_SCOPE_MAP["gmail"],
    "drive": (
        "https://www.googleapis.com/auth/drive",
    ),
    "docs": (
        "https://www.googleapis.com/auth/documents",
    ),
    "sheets": (
        "https://www.googleapis.com/auth/spreadsheets",
    ),
    "analytics": (
        "https://www.googleapis.com/auth/analytics.readonly",
    ),
    "calendar": TOOL_SCOPE_MAP["google_calendar"],
}

GOOGLE_OAUTH_SERVICE_ALIASES: dict[str, tuple[str, ...]] = {
    "google_workspace": ("drive", "docs", "sheets"),
    "google_analytics": ("analytics",),
    "google_calendar": ("calendar",),
}

DEFAULT_GOOGLE_OAUTH_SERVICE_IDS: tuple[str, ...] = (
    "gmail",
    "drive",
    "docs",
    "sheets",
    "analytics",
)


def _dedupe(scopes: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for raw in scopes:
        scope = str(raw or "").strip()
        if not scope or scope in seen:
            continue
        seen.add(scope)
        rows.append(scope)
    return rows


def _normalize_service_id(raw: str) -> str:
    return str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")


def normalize_google_oauth_service_ids(service_ids: Iterable[str] | None) -> list[str]:
    if service_ids is None:
        return []
    expanded: list[str] = []
    for raw in service_ids:
        normalized = _normalize_service_id(str(raw or ""))
        if not normalized:
            continue
        if normalized in GOOGLE_OAUTH_SERVICE_SCOPE_MAP:
            expanded.append(normalized)
            continue
        alias_targets = GOOGLE_OAUTH_SERVICE_ALIASES.get(normalized)
        if alias_targets:
            expanded.extend(alias_targets)
    return _dedupe(expanded)


def invalid_google_oauth_service_ids(service_ids: Iterable[str] | None) -> list[str]:
    if service_ids is None:
        return []
    invalid: list[str] = []
    for raw in service_ids:
        normalized = _normalize_service_id(str(raw or ""))
        if not normalized:
            continue
        if normalized in GOOGLE_OAUTH_SERVICE_SCOPE_MAP:
            continue
        if normalized in GOOGLE_OAUTH_SERVICE_ALIASES:
            continue
        invalid.append(normalized)
    return _dedupe(invalid)


def expand_scopes_for_tool_ids(tool_ids: Iterable[str], *, include_base: bool = True) -> list[str]:
    resolved_tool_ids = [str(item or "").strip() for item in tool_ids if str(item or "").strip()]
    scopes: list[str] = []
    if include_base:
        scopes.extend(BASE_PROFILE_SCOPES)
    for tool_id in resolved_tool_ids:
        scopes.extend(TOOL_SCOPE_MAP.get(tool_id, ()))
    return _dedupe(scopes)


def scopes_from_service_ids(service_ids: Iterable[str], *, include_base: bool = True) -> list[str]:
    normalized_ids = normalize_google_oauth_service_ids(service_ids)
    scopes: list[str] = []
    if include_base:
        scopes.extend(BASE_PROFILE_SCOPES)
    for service_id in normalized_ids:
        scopes.extend(GOOGLE_OAUTH_SERVICE_SCOPE_MAP.get(service_id, ()))
    return _dedupe(scopes)


def default_oauth_scopes() -> list[str]:
    return expand_scopes_for_tool_ids(DEFAULT_TOOL_IDS, include_base=True)


def connector_required_scopes(connector_id: str) -> list[str]:
    return list(CONNECTOR_SCOPE_MAP.get(str(connector_id or "").strip(), ()))


def _scope_granted(required_scope: str, granted_scopes: set[str]) -> bool:
    if required_scope in granted_scopes:
        return True
    if required_scope.startswith("https://www.googleapis.com/auth/gmail.") and KNOWN_GMAIL_SUPER_SCOPE in granted_scopes:
        return True
    return False


def missing_scopes(*, required_scopes: Iterable[str], granted_scopes: Iterable[str]) -> list[str]:
    granted_set = {str(item or "").strip() for item in granted_scopes if str(item or "").strip()}
    missing: list[str] = []
    for raw in required_scopes:
        required = str(raw or "").strip()
        if not required:
            continue
        if _scope_granted(required, granted_set):
            continue
        missing.append(required)
    return _dedupe(missing)


def is_tool_scope_satisfied(tool_id: str, granted_scopes: Iterable[str]) -> bool:
    required = TOOL_SCOPE_MAP.get(str(tool_id or "").strip(), ())
    return len(missing_scopes(required_scopes=required, granted_scopes=granted_scopes)) == 0


def enabled_tool_ids_from_scopes(granted_scopes: Iterable[str]) -> list[str]:
    return [tool_id for tool_id in DEFAULT_TOOL_IDS if is_tool_scope_satisfied(tool_id, granted_scopes)]


def enabled_service_ids_from_scopes(granted_scopes: Iterable[str]) -> list[str]:
    resolved: list[str] = []
    for service_id, required in GOOGLE_OAUTH_SERVICE_SCOPE_MAP.items():
        if len(missing_scopes(required_scopes=required, granted_scopes=granted_scopes)) == 0:
            resolved.append(service_id)
    return resolved
