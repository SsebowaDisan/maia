from __future__ import annotations

import os
from typing import Any

from api.services.agent.auth.credentials import get_credential_store

import logging

from .base import BaseConnector
from .brave_search_connector import BraveSearchConnector
from .bing_search_connector import BingSearchConnector
from .email_validation_connector import EmailValidationConnector
from .google_ads_connector import GoogleAdsConnector
from .google_analytics_connector import GoogleAnalyticsConnector
from .google_api_hub_connector import GoogleApiHubConnector
from .google_calendar_connector import GoogleCalendarConnector
from .google_maps_connector import GoogleMapsConnector
from .google_workspace_connector import GoogleWorkspaceConnector
from .gmail_connector import GmailConnector
from .invoice_connector import InvoiceConnector
from .m365_connector import M365Connector
from .plugin_manifest import connector_plugin_manifest
from .slack_connector import SlackConnector

_logger = logging.getLogger(__name__)

# Deprecated Playwright connectors → route to API or Computer Use equivalents.
# Old IDs still resolve for backward compatibility but log a deprecation notice.
_DEPRECATED_REDIRECTS: dict[str, str] = {
    "gmail_playwright": "gmail",
    "playwright_browser": "computer_use_browser",
    "playwright_contact_form": "computer_use_browser",
}


def _env_flag(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


class ConnectorRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, type] = {
            "slack": SlackConnector,
            "google_ads": GoogleAdsConnector,
            "google_workspace": GoogleWorkspaceConnector,
            "google_maps": GoogleMapsConnector,
            "google_calendar": GoogleCalendarConnector,
            "google_analytics": GoogleAnalyticsConnector,
            "google_api_hub": GoogleApiHubConnector,
            "gmail": GmailConnector,
            "bing_search": BingSearchConnector,
            "brave_search": BraveSearchConnector,
            "email_validation": EmailValidationConnector,
            "m365": M365Connector,
            "invoice": InvoiceConnector,
        }
        # Computer Use browser connector — uses the CU agent loop instead of Playwright
        try:
            from .computer_use_browser_connector import ComputerUseBrowserConnector
            self._factories["computer_use_browser"] = ComputerUseBrowserConnector
        except ImportError:
            _logger.debug("ComputerUseBrowserConnector not available, browser tasks disabled")
        # Source federation connectors — enabled via environment flags (S1)
        if _env_flag("MAIA_ARXIV_ENABLED"):
            from .arxiv_connector import ArXivConnector
            self._factories["arxiv"] = ArXivConnector
        if _env_flag("MAIA_SEC_EDGAR_ENABLED"):
            from .sec_edgar_connector import SecEdgarConnector
            self._factories["sec_edgar"] = SecEdgarConnector
        if _env_flag("MAIA_NEWSAPI_ENABLED"):
            from .newsapi_connector import NewsAPIConnector
            self._factories["newsapi"] = NewsAPIConnector
        if _env_flag("MAIA_REDDIT_ENABLED"):
            from .reddit_connector import RedditConnector
            self._factories["reddit"] = RedditConnector

    def names(self) -> list[str]:
        # Include deprecated IDs so existing workflows still resolve
        all_ids = set(self._factories.keys()) | set(_DEPRECATED_REDIRECTS.keys())
        return sorted(all_ids)

    def build(self, connector_id: str, settings: dict[str, Any] | None = None) -> BaseConnector:
        # Handle deprecated Playwright connectors → redirect to new target
        if connector_id in _DEPRECATED_REDIRECTS:
            target = _DEPRECATED_REDIRECTS[connector_id]
            _logger.info("Connector '%s' is deprecated, routing to '%s'", connector_id, target)
            connector_id = target
        factory = self._factories.get(connector_id)
        if factory is None:
            raise KeyError(f"Unknown connector: {connector_id}")
        merged_settings = dict(settings or {})
        tenant_id = str(merged_settings.get("agent.tenant_id") or "")
        if tenant_id and "__agent_user_id" not in merged_settings:
            merged_settings["__agent_user_id"] = tenant_id
        if tenant_id:
            credential = get_credential_store().get(tenant_id=tenant_id, connector_id=connector_id)
            if credential:
                merged_settings.update(credential.values)
        return factory(settings=merged_settings)

    def health_report(self, settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        report: list[dict[str, Any]] = []
        for connector_id in self.names():
            connector = self.build(connector_id, settings=settings)
            report.append(connector.health_check().to_dict())
        return report

    def plugin_manifests(self, settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        manifests: list[dict[str, Any]] = []
        for connector_id in self.names():
            manifests.append(self.plugin_manifest(connector_id=connector_id, settings=settings))
        return manifests

    def plugin_manifest(self, connector_id: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        connector = self.build(connector_id, settings=settings)
        health = connector.health_check()
        manifest = connector_plugin_manifest(connector_id=connector_id, enabled=bool(health.ok))
        return manifest.model_dump(mode="json")


_registry: ConnectorRegistry | None = None


def get_connector_registry() -> ConnectorRegistry:
    global _registry
    if _registry is None:
        _registry = ConnectorRegistry()
    return _registry
