"""Product metadata overlays and suite sub-service definitions.

Responsibility: provide brand_slug, visibility, auth_kind, setup_mode,
scene_family, and sub-service lists consumed by the catalog builder to
enrich ConnectorDefinitionSchema for the frontend connector surface.
"""
from __future__ import annotations

from api.schemas.connector_definition.schema import ConnectorSubService

# ---------------------------------------------------------------------------
# Per-connector product metadata
# Maps connector_id → fields that enrich the raw tool profile.
# ---------------------------------------------------------------------------

PRODUCT_META: dict[str, dict] = {
    # ── Google suite services ─────────────────────────────────────────────────
    "gmail": {
        "brand_slug": "gmail",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "email",
        "suite_id": "google",
        "suite_label": "Google Suite",
        "service_order": 1,
    },
    "google_calendar": {
        "brand_slug": "google_calendar",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "api",
        "suite_id": "google",
        "suite_label": "Google Suite",
        "service_order": 2,
    },
    "google_workspace": {
        "brand_slug": "google_drive",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "document",
        "suite_id": "google",
        "suite_label": "Google Suite",
        "service_order": 3,
    },
    "google_analytics": {
        "brand_slug": "google_analytics",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "api",
        "suite_id": "google",
        "suite_label": "Google Suite",
        "service_order": 10,
    },
    "google_ads": {
        "brand_slug": "google_ads",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "api",
        "suite_id": "google",
        "suite_label": "Google Suite",
        "service_order": 20,
    },
    "google_maps": {
        "brand_slug": "google_maps",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
        "suite_id": "google",
        "suite_label": "Google Suite",
        "service_order": 30,
    },
    "google_api_hub": {
        "brand_slug": "google_cloud",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "api",
        "suite_id": "google",
        "suite_label": "Google Suite",
        "service_order": 40,
    },
    # ── Deprecated Playwright → redirects to API / Computer Use ─────────────
    "gmail_playwright": {"brand_slug": "gmail", "visibility": "internal", "auth_kind": "none", "setup_mode": "none", "scene_family": "email", "deprecated": True, "redirect_to": "gmail"},
    "playwright_browser": {"brand_slug": "browser", "visibility": "internal", "auth_kind": "none", "setup_mode": "none", "scene_family": "browser", "deprecated": True, "redirect_to": "computer_use_browser"},
    "playwright_contact_form": {"brand_slug": "browser", "visibility": "internal", "auth_kind": "none", "setup_mode": "none", "scene_family": "browser", "deprecated": True, "redirect_to": "computer_use_browser"},
    # ── Computer Use browser (replaces Playwright) ────────────────────────────
    "computer_use_browser": {"brand_slug": "browser", "visibility": "internal", "auth_kind": "none", "setup_mode": "none", "scene_family": "browser"},
    # ── Microsoft 365 ─────────────────────────────────────────────────────────
    "m365": {
        "brand_slug": "microsoft_365",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "email",
        "suite_id": "microsoft",
        "suite_label": "Microsoft 365",
        "service_order": 1,
    },
    # ── Standalone connectors ─────────────────────────────────────────────────
    "slack": {
        "brand_slug": "slack",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "chat",
    },
    "brave_search": {
        "brand_slug": "brave",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "browser",
    },
    "bing_search": {
        "brand_slug": "bing",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "browser",
    },
    "http_request": {
        "brand_slug": "http",
        "visibility": "user_facing",
        "auth_kind": "none",
        "setup_mode": "none",
        "scene_family": "api",
    },
    "email_validation": {
        "brand_slug": "email_validation",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
    },
    "invoice": {
        "brand_slug": "invoice",
        "visibility": "user_facing",
        "auth_kind": "none",
        "setup_mode": "none",
        "scene_family": "document",
    },
    "reddit": {
        "brand_slug": "reddit",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
    },
    "newsapi": {
        "brand_slug": "newsapi",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
    },
    "sec_edgar": {
        "brand_slug": "sec_edgar",
        "visibility": "user_facing",
        "auth_kind": "none",
        "setup_mode": "none",
        "scene_family": "document",
    },
    "page_monitor": {
        "brand_slug": "page_monitor",
        "visibility": "user_facing",
        "auth_kind": "none",
        "setup_mode": "none",
        "scene_family": "browser",
    },
    # ── Enterprise ─────────────────────────────────────────────────────────────
    "sap": {
        "brand_slug": "sap",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
    },
    # ── Productivity & Docs ─────────────────────────────────────────────────────
    "notion": {
        "brand_slug": "notion",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "document",
    },
    # ── CRM ────────────────────────────────────────────────────────────────────
    "hubspot": {
        "brand_slug": "hubspot",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "crm",
    },
    "salesforce": {
        "brand_slug": "salesforce",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "crm",
    },
    # ── Project Management ────────────────────────────────────────────────────
    "jira": {
        "brand_slug": "jira",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
    },
    "linear": {
        "brand_slug": "linear",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
    },
    "asana": {
        "brand_slug": "asana",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
    },
    "monday": {
        "brand_slug": "monday",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
    },
    "trello": {
        "brand_slug": "trello",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
    },
    # ── Spreadsheet / No-Code ─────────────────────────────────────────────────
    "airtable": {
        "brand_slug": "airtable",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "sheet",
    },
    # ── Support ───────────────────────────────────────────────────────────────
    "zendesk": {
        "brand_slug": "zendesk",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "support",
    },
    "intercom": {
        "brand_slug": "intercom",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "support",
    },
    # ── Commerce ──────────────────────────────────────────────────────────────
    "stripe": {
        "brand_slug": "stripe",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "commerce",
    },
    "shopify": {
        "brand_slug": "shopify",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "commerce",
    },
    # ── Communication ─────────────────────────────────────────────────────────
    "discord": {
        "brand_slug": "discord",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "chat",
    },
    "microsoft_teams": {
        "brand_slug": "microsoft_teams",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "chat",
        "suite_id": "microsoft",
        "suite_label": "Microsoft 365",
        "service_order": 10,
    },
    "twilio": {
        "brand_slug": "twilio",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "chat",
    },
    # ── Marketing ─────────────────────────────────────────────────────────────
    "mailchimp": {
        "brand_slug": "mailchimp",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "marketing",
    },
    "webflow": {
        "brand_slug": "webflow",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "marketing",
    },
    # ── Scheduling ────────────────────────────────────────────────────────────
    "calendly": {
        "brand_slug": "calendly",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "scheduling",
    },
    # ── E-Signatures ──────────────────────────────────────────────────────────
    "docusign": {
        "brand_slug": "docusign",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "document",
    },
    # ── Cloud Storage ─────────────────────────────────────────────────────────
    "dropbox": {
        "brand_slug": "dropbox",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "document",
    },
    "box": {
        "brand_slug": "box",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "document",
    },
    # ── Wiki / Knowledge Base ─────────────────────────────────────────────────
    "confluence": {
        "brand_slug": "confluence",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "document",
    },
    # ── Design ────────────────────────────────────────────────────────────────
    "figma": {
        "brand_slug": "figma",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "design",
    },
    # ── Database ──────────────────────────────────────────────────────────────
    "supabase": {
        "brand_slug": "supabase",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "database",
    },
    "postgresql": {
        "brand_slug": "postgresql",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "database",
    },
    "bigquery": {
        "brand_slug": "bigquery",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "database",
        "suite_id": "google",
        "suite_label": "Google",
        "service_order": 50,
    },
    # ── Accounting ────────────────────────────────────────────────────────────
    "quickbooks": {
        "brand_slug": "quickbooks",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "commerce",
    },
    "xero": {
        "brand_slug": "xero",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "commerce",
    },
    # ── Automation Bridges ────────────────────────────────────────────────────
    "zapier_webhooks": {
        "brand_slug": "zapier",
        "visibility": "user_facing",
        "auth_kind": "none",
        "setup_mode": "none",
        "scene_family": "api",
    },
    "make": {
        "brand_slug": "make",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
    },
    # ── Cloud / Infrastructure ────────────────────────────────────────────────
    "aws": {
        "brand_slug": "aws",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "cloud",
    },
    "cloudflare": {
        "brand_slug": "cloudflare",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "cloud",
    },
    "vercel": {
        "brand_slug": "vercel",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "cloud",
    },
    # ── Social ────────────────────────────────────────────────────────────────
    "twitter": {
        "brand_slug": "twitter",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "social",
    },
    "linkedin": {
        "brand_slug": "linkedin",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "social",
    },
    "youtube": {
        "brand_slug": "youtube",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "social",
        "suite_id": "google",
        "suite_label": "Google",
        "service_order": 60,
    },
    "spotify": {
        "brand_slug": "spotify",
        "visibility": "user_facing",
        "auth_kind": "oauth2",
        "setup_mode": "oauth_popup",
        "scene_family": "api",
    },
    # ── Developer Tools ───────────────────────────────────────────────────────
    "github": {
        "brand_slug": "github",
        "visibility": "user_facing",
        "auth_kind": "bearer",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
    },
    "openai": {
        "brand_slug": "openai",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "api",
    },
    "pinecone": {
        "brand_slug": "pinecone",
        "visibility": "user_facing",
        "auth_kind": "api_key",
        "setup_mode": "manual_credentials",
        "scene_family": "database",
    },
}


# ---------------------------------------------------------------------------
# Suite sub-service definitions
# ---------------------------------------------------------------------------

GOOGLE_SUB_SERVICES: list[ConnectorSubService] = [
    ConnectorSubService(
        id="gmail", label="Gmail",
        description="Send and read emails via Gmail API.",
        brand_slug="gmail", scene_family="email",
        required_scopes=[
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.readonly",
        ],
    ),
    ConnectorSubService(
        id="google_calendar", label="Google Calendar",
        description="Create and manage calendar events.",
        brand_slug="google_calendar", scene_family="api",
        required_scopes=["https://www.googleapis.com/auth/calendar"],
    ),
    ConnectorSubService(
        id="google_drive", label="Google Drive",
        description="Search, read, and manage files in Drive.",
        brand_slug="google_drive", scene_family="document",
        required_scopes=[
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.file",
        ],
    ),
    ConnectorSubService(
        id="google_docs", label="Google Docs",
        description="Read and create Google Docs documents.",
        brand_slug="google_docs", scene_family="document",
        required_scopes=["https://www.googleapis.com/auth/documents"],
    ),
    ConnectorSubService(
        id="google_sheets", label="Google Sheets",
        description="Read, write, and append data in spreadsheets.",
        brand_slug="google_sheets", scene_family="sheet",
        required_scopes=["https://www.googleapis.com/auth/spreadsheets"],
    ),
    ConnectorSubService(
        id="google_analytics", label="Google Analytics",
        description="Fetch GA4 traffic and conversion reports.",
        brand_slug="google_analytics", scene_family="api",
        required_scopes=["https://www.googleapis.com/auth/analytics.readonly"],
    ),
    ConnectorSubService(
        id="google_ads", label="Google Ads",
        description="Pull campaign performance data and manage bids.",
        brand_slug="google_ads", scene_family="api",
        required_scopes=["https://www.googleapis.com/auth/adwords"],
    ),
    ConnectorSubService(
        id="google_maps", label="Google Maps",
        description="Geocode addresses and search for nearby places.",
        brand_slug="google_maps", scene_family="api",
        required_scopes=[],
    ),
    ConnectorSubService(
        id="bigquery", label="BigQuery",
        description="Run SQL queries against BigQuery data warehouses.",
        brand_slug="bigquery", scene_family="database",
        required_scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
    ),
    ConnectorSubService(
        id="youtube", label="YouTube",
        description="Search videos, channel analytics, and playlist management.",
        brand_slug="youtube", scene_family="social",
        required_scopes=["https://www.googleapis.com/auth/youtube.readonly"],
    ),
]

M365_SUB_SERVICES: list[ConnectorSubService] = [
    ConnectorSubService(
        id="outlook", label="Outlook",
        description="Send and read emails via Microsoft Graph.",
        brand_slug="outlook", scene_family="email",
        required_scopes=["Mail.Send", "Mail.Read"],
    ),
    ConnectorSubService(
        id="microsoft_calendar", label="Microsoft Calendar",
        description="Create and manage calendar events.",
        brand_slug="microsoft_calendar", scene_family="api",
        required_scopes=["Calendars.ReadWrite"],
    ),
    ConnectorSubService(
        id="onedrive", label="OneDrive",
        description="Read and manage files in OneDrive.",
        brand_slug="onedrive", scene_family="document",
        required_scopes=["Files.ReadWrite"],
    ),
    ConnectorSubService(
        id="excel", label="Excel",
        description="Read and write Excel workbooks.",
        brand_slug="excel", scene_family="sheet",
        required_scopes=["Files.ReadWrite"],
    ),
    ConnectorSubService(
        id="word", label="Word",
        description="Read and create Word documents.",
        brand_slug="word", scene_family="document",
        required_scopes=["Files.ReadWrite"],
    ),
    ConnectorSubService(
        id="teams", label="Teams",
        description="Send messages to Microsoft Teams channels.",
        brand_slug="teams", scene_family="chat",
        required_scopes=["ChannelMessage.Send"],
    ),
]

SUITE_SUB_SERVICES: dict[str, list[ConnectorSubService]] = {
    "google": GOOGLE_SUB_SERVICES,
    "microsoft": M365_SUB_SERVICES,
}
