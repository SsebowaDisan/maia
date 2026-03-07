from __future__ import annotations

from typing import Any

from api.services.agent.auth.credentials import get_credential_store

from .base import BaseConnector
from .brave_search_connector import BraveSearchConnector
from .bing_search_connector import BingSearchConnector
from .browser_contact_connector import BrowserContactConnector
from .browser_connector import BrowserConnector
from .email_validation_connector import EmailValidationConnector
from .google_ads_connector import GoogleAdsConnector
from .google_analytics_connector import GoogleAnalyticsConnector
from .google_api_hub_connector import GoogleApiHubConnector
from .google_calendar_connector import GoogleCalendarConnector
from .google_maps_connector import GoogleMapsConnector
from .google_workspace_connector import GoogleWorkspaceConnector
from .gmail_connector import GmailConnector
from .gmail_playwright_connector import GmailPlaywrightConnector
from .invoice_connector import InvoiceConnector
from .m365_connector import M365Connector
from .plugin_manifest import connector_plugin_manifest
from .slack_connector import SlackConnector


class ConnectorRegistry:
    def __init__(self) -> None:
        self._factories = {
            "slack": SlackConnector,
            "google_ads": GoogleAdsConnector,
            "google_workspace": GoogleWorkspaceConnector,
            "google_maps": GoogleMapsConnector,
            "google_calendar": GoogleCalendarConnector,
            "google_analytics": GoogleAnalyticsConnector,
            "google_api_hub": GoogleApiHubConnector,
            "gmail": GmailConnector,
            "gmail_playwright": GmailPlaywrightConnector,
            "bing_search": BingSearchConnector,
            "brave_search": BraveSearchConnector,
            "playwright_browser": BrowserConnector,
            "playwright_contact_form": BrowserContactConnector,
            "email_validation": EmailValidationConnector,
            "m365": M365Connector,
            "invoice": InvoiceConnector,
        }

    def names(self) -> list[str]:
        return sorted(self._factories.keys())

    def build(self, connector_id: str, settings: dict[str, Any] | None = None) -> BaseConnector:
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
