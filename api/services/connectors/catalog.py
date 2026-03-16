"""ConnectorCatalog — maps the existing ConnectorRegistry to ConnectorDefinitionSchema.

Responsibility: bridge between the agent-execution connector registry
(api/services/agent/connectors/registry.py) and the platform-level
ConnectorDefinitionSchema used by the API, marketplace, and agent builder.
"""
from __future__ import annotations

from api.schemas.connector_definition import (
    ApiKeyAuthConfig,
    ConnectorCategory,
    ConnectorDefinitionSchema,
    NoAuthConfig,
    OAuth2AuthConfig,
    ToolActionClass,
    ToolParameter,
    ToolParameterType,
    ToolSchema,
)

# ---------------------------------------------------------------------------
# Static connector profiles
# Each entry maps a connector_id → enough metadata to build a
# ConnectorDefinitionSchema.  Only the fields that differ from defaults are set.
# ---------------------------------------------------------------------------

_PROFILES: dict[str, dict] = {
    "gmail": {
        "name": "Gmail",
        "description": "Read and send Gmail messages on behalf of the user.",
        "category": ConnectorCategory.email,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            revoke_url="https://oauth2.googleapis.com/revoke",
            scopes=[
                "https://www.googleapis.com/auth/gmail.send",
                "https://www.googleapis.com/auth/gmail.readonly",
            ],
        ),
        "tags": ["google", "email"],
        "tools": [
            ToolSchema(
                id="gmail.send",
                name="Send email",
                description="Compose and send an email via Gmail.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="to", type=ToolParameterType.string, description="Recipient email address"),
                    ToolParameter(name="subject", type=ToolParameterType.string, description="Email subject line"),
                    ToolParameter(name="body", type=ToolParameterType.string, description="Plain-text email body"),
                    ToolParameter(name="cc", type=ToolParameterType.string, description="CC recipients", required=False),
                ],
            ),
            ToolSchema(
                id="gmail.draft",
                name="Create draft",
                description="Save an email as a draft in Gmail without sending it.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="to", type=ToolParameterType.string, description="Recipient email address"),
                    ToolParameter(name="subject", type=ToolParameterType.string, description="Email subject line"),
                    ToolParameter(name="body", type=ToolParameterType.string, description="Plain-text email body"),
                    ToolParameter(name="cc", type=ToolParameterType.string, description="CC recipients", required=False),
                ],
            ),
            ToolSchema(
                id="gmail.search",
                name="Search emails",
                description="Search Gmail messages using a query string.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="query", type=ToolParameterType.string, description="Gmail search query, e.g. 'subject:invoice from:vendor'"),
                    ToolParameter(name="max_results", type=ToolParameterType.integer, description="Maximum messages to return", required=False, default=10),
                ],
            ),
            ToolSchema(
                id="gmail.read",
                name="Read inbox",
                description="Search and read Gmail messages.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="query", type=ToolParameterType.string, description="Gmail search query, e.g. 'from:alice'"),
                    ToolParameter(name="max_results", type=ToolParameterType.integer, description="Maximum messages to return", required=False, default=10),
                ],
            ),
        ],
    },
    "google_calendar": {
        "name": "Google Calendar",
        "description": "Create and list Google Calendar events.",
        "category": ConnectorCategory.calendar,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/calendar"],
        ),
        "tags": ["google", "calendar"],
        "tools": [
            ToolSchema(
                id="gcalendar.create_event",
                name="Create event",
                description="Create a new Google Calendar event.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="title", type=ToolParameterType.string, description="Event title"),
                    ToolParameter(name="start", type=ToolParameterType.string, description="Start datetime ISO 8601"),
                    ToolParameter(name="end", type=ToolParameterType.string, description="End datetime ISO 8601"),
                    ToolParameter(name="description", type=ToolParameterType.string, description="Event description", required=False),
                ],
            ),
            ToolSchema(
                id="gcalendar.list_events",
                name="List events",
                description="List upcoming Google Calendar events.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="max_results", type=ToolParameterType.integer, description="Max events to return", required=False, default=10),
                    ToolParameter(name="time_min", type=ToolParameterType.string, description="Start of search window (ISO 8601)", required=False),
                ],
            ),
        ],
    },
    "google_workspace": {
        "name": "Google Workspace",
        "description": "Access Google Drive, Docs, and Sheets.",
        "category": ConnectorCategory.storage,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/drive.file",
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/documents",
            ],
        ),
        "tags": ["google", "drive", "sheets", "docs"],
        "tools": [
            ToolSchema(
                id="gdrive.read_file",
                name="Read file",
                description="Read the contents of a Google Drive file.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="file_id", type=ToolParameterType.string, description="Google Drive file ID"),
                ],
            ),
            ToolSchema(
                id="workspace.drive.search",
                name="Search Drive",
                description="Search Google Drive for files by name or type.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="query", type=ToolParameterType.string, description="Search query, e.g. 'CRM tracker'"),
                    ToolParameter(name="max_results", type=ToolParameterType.integer, description="Max files to return", required=False, default=10),
                ],
            ),
            ToolSchema(
                id="workspace.sheets.read",
                name="Read sheet",
                description="Read rows from a Google Sheets spreadsheet.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="spreadsheet_id", type=ToolParameterType.string, description="Spreadsheet ID or URL"),
                    ToolParameter(name="range", type=ToolParameterType.string, description="A1 notation range, e.g. 'Sheet1!A1:Z100'", required=False),
                ],
            ),
            ToolSchema(
                id="workspace.sheets.append",
                name="Append row",
                description="Append a row to a Google Sheets spreadsheet.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="spreadsheet_id", type=ToolParameterType.string, description="Spreadsheet ID or URL"),
                    ToolParameter(name="values", type=ToolParameterType.array, description="List of cell values for the new row"),
                    ToolParameter(name="sheet_name", type=ToolParameterType.string, description="Sheet tab name", required=False, default="Sheet1"),
                ],
            ),
            ToolSchema(
                id="workspace.sheets.update",
                name="Update cell",
                description="Update a specific cell or range in a Google Sheet.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="spreadsheet_id", type=ToolParameterType.string, description="Spreadsheet ID or URL"),
                    ToolParameter(name="range", type=ToolParameterType.string, description="A1 notation range to update"),
                    ToolParameter(name="values", type=ToolParameterType.array, description="2D array of values to write"),
                ],
            ),
            ToolSchema(
                id="workspace.docs.read",
                name="Read doc",
                description="Read the text content of a Google Doc.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="document_id", type=ToolParameterType.string, description="Google Doc document ID or URL"),
                ],
            ),
            ToolSchema(
                id="workspace.docs.create",
                name="Create doc",
                description="Create a new Google Doc with the given title and content.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="title", type=ToolParameterType.string, description="Document title"),
                    ToolParameter(name="content", type=ToolParameterType.string, description="Markdown or plain-text body content"),
                    ToolParameter(name="folder_id", type=ToolParameterType.string, description="Drive folder ID to save into", required=False),
                ],
            ),
            ToolSchema(
                id="workspace.docs.fill_template",
                name="Fill doc template",
                description="Copy a Google Doc template and replace placeholder variables with provided values.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="template_id", type=ToolParameterType.string, description="Template Google Doc ID"),
                    ToolParameter(name="variables", type=ToolParameterType.object, description="Key/value pairs to replace in the template"),
                    ToolParameter(name="output_title", type=ToolParameterType.string, description="Title for the new document"),
                ],
            ),
        ],
    },
    "slack": {
        "name": "Slack",
        "description": "Send messages and read channels in Slack.",
        "category": ConnectorCategory.communication,
        "auth": OAuth2AuthConfig(
            authorization_url="https://slack.com/oauth/v2/authorize",
            token_url="https://slack.com/api/oauth.v2.access",
            scopes=["chat:write", "channels:read", "channels:history"],
        ),
        "tags": ["slack", "messaging"],
        "tools": [
            ToolSchema(
                id="slack.send_message",
                name="Send message",
                description="Post a message to a Slack channel.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="channel", type=ToolParameterType.string, description="Channel name or ID"),
                    ToolParameter(name="text", type=ToolParameterType.string, description="Message text"),
                ],
            ),
            ToolSchema(
                id="slack.read_channel",
                name="Read channel",
                description="Read recent messages from a Slack channel.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="channel", type=ToolParameterType.string, description="Channel name or ID"),
                    ToolParameter(name="limit", type=ToolParameterType.integer, description="Number of messages", required=False, default=20),
                ],
            ),
            ToolSchema(
                id="slack.list_channels",
                name="List channels",
                description="List available Slack channels.",
                action_class=ToolActionClass.read,
                parameters=[],
            ),
        ],
    },
    "m365": {
        "name": "Microsoft 365",
        "description": "Send and read Outlook email and access OneDrive.",
        "category": ConnectorCategory.email,
        "auth": OAuth2AuthConfig(
            authorization_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
            scopes=["Mail.Send", "Mail.Read", "Files.ReadWrite"],
        ),
        "tags": ["microsoft", "email", "onedrive"],
        "tools": [
            ToolSchema(
                id="outlook.send",
                name="Send email",
                description="Send an email via Outlook.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="to", type=ToolParameterType.string, description="Recipient email address"),
                    ToolParameter(name="subject", type=ToolParameterType.string, description="Subject line"),
                    ToolParameter(name="body", type=ToolParameterType.string, description="Email body"),
                ],
            ),
            ToolSchema(
                id="outlook.read",
                name="Read inbox",
                description="Read emails from Outlook inbox.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="max_results", type=ToolParameterType.integer, description="Max messages", required=False, default=10),
                ],
            ),
        ],
    },
    "playwright_browser": {
        "name": "Browser",
        "description": "Browse and extract content from any web page using Playwright.",
        "category": ConnectorCategory.data,
        "auth": NoAuthConfig(),
        "tags": ["browser", "web", "scraping"],
        "tools": [
            ToolSchema(
                id="browser.navigate",
                name="Navigate",
                description="Open a URL and extract page text and structure.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="url", type=ToolParameterType.string, description="URL to navigate to"),
                ],
            ),
        ],
    },
    "brave_search": {
        "name": "Brave Search",
        "description": "Web search via the Brave Search API.",
        "category": ConnectorCategory.data,
        "auth": ApiKeyAuthConfig(param_name="X-Subscription-Token", credential_label="Brave API Key"),
        "tags": ["search", "web"],
        "tools": [
            ToolSchema(
                id="brave.search",
                name="Web search",
                description="Search the web using Brave Search.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                    ToolParameter(name="count", type=ToolParameterType.integer, description="Number of results", required=False, default=5),
                ],
            ),
        ],
    },
    "http_request": {
        "name": "HTTP Request",
        "description": "Make generic HTTP GET and POST requests to any API.",
        "category": ConnectorCategory.developer_tools,
        "auth": NoAuthConfig(),
        "tags": ["api", "http", "generic"],
        "tools": [
            ToolSchema(
                id="http.get",
                name="HTTP GET",
                description="Make an HTTP GET request.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="url", type=ToolParameterType.string, description="Request URL"),
                    ToolParameter(name="headers", type=ToolParameterType.object, description="Optional request headers", required=False),
                ],
            ),
            ToolSchema(
                id="http.post",
                name="HTTP POST",
                description="Make an HTTP POST request with a JSON body.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="url", type=ToolParameterType.string, description="Request URL"),
                    ToolParameter(name="body", type=ToolParameterType.object, description="JSON request body"),
                    ToolParameter(name="headers", type=ToolParameterType.object, description="Optional request headers", required=False),
                ],
            ),
        ],
    },
    # ── Google suite ──────────────────────────────────────────────────────────
    "google_analytics": {
        "name": "Google Analytics",
        "description": "Fetch GA4 traffic, conversion, and audience reports.",
        "category": ConnectorCategory.analytics,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        ),
        "tags": ["google", "analytics", "ga4"],
        "suite_id": "google",
        "suite_label": "Google",
        "service_order": 10,
        "logo_url": "https://www.gstatic.com/analytics-suite/header/suite/v2/ic_analytics.svg",
        "tools": [
            ToolSchema(
                id="analytics.ga4.report",
                name="GA4 Report",
                description="Fetch a GA4 report for a date range and set of metrics.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="property_id", type=ToolParameterType.string, description="GA4 property ID"),
                    ToolParameter(name="start_date", type=ToolParameterType.string, description="Start date YYYY-MM-DD"),
                    ToolParameter(name="end_date", type=ToolParameterType.string, description="End date YYYY-MM-DD"),
                    ToolParameter(name="metrics", type=ToolParameterType.array, description="List of GA4 metric names", required=False),
                ],
            ),
            ToolSchema(
                id="analytics.ga4.full_report",
                name="GA4 Full Report",
                description="Fetch a comprehensive GA4 report including channels and top pages.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="property_id", type=ToolParameterType.string, description="GA4 property ID"),
                    ToolParameter(name="days", type=ToolParameterType.integer, description="Lookback window in days", required=False, default=7),
                ],
            ),
        ],
        "emitted_event_types": [],
    },
    "google_ads": {
        "name": "Google Ads",
        "description": "Pull campaign performance data and manage Google Ads.",
        "category": ConnectorCategory.analytics,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/adwords"],
        ),
        "tags": ["google", "ads", "paid-search"],
        "suite_id": "google",
        "suite_label": "Google",
        "service_order": 20,
        "logo_url": "https://www.gstatic.com/images/branding/product/1x/google_ads_48dp.png",
        "tools": [
            ToolSchema(
                id="google_ads.get_campaigns",
                name="Get campaigns",
                description="List all Google Ads campaigns and their performance stats.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="customer_id", type=ToolParameterType.string, description="Google Ads customer ID"),
                    ToolParameter(name="start_date", type=ToolParameterType.string, description="Start date YYYY-MM-DD"),
                    ToolParameter(name="end_date", type=ToolParameterType.string, description="End date YYYY-MM-DD"),
                ],
            ),
        ],
        "emitted_event_types": [],
    },
    "google_maps": {
        "name": "Google Maps",
        "description": "Look up places, addresses, and route information via Google Maps.",
        "category": ConnectorCategory.data,
        "auth": ApiKeyAuthConfig(param_name="key", credential_label="Google Maps API Key"),
        "tags": ["google", "maps", "geocoding"],
        "suite_id": "google",
        "suite_label": "Google",
        "service_order": 30,
        "logo_url": "https://maps.gstatic.com/mapfiles/api-3/images/google_maps_logo.png",
        "tools": [
            ToolSchema(
                id="google_maps.geocode",
                name="Geocode address",
                description="Convert a free-text address to latitude/longitude.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="address", type=ToolParameterType.string, description="Address to geocode"),
                ],
            ),
            ToolSchema(
                id="google_maps.places_search",
                name="Places search",
                description="Search for nearby places matching a query.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                    ToolParameter(name="location", type=ToolParameterType.string, description="lat,lng centre point", required=False),
                    ToolParameter(name="radius_m", type=ToolParameterType.integer, description="Search radius in metres", required=False, default=5000),
                ],
            ),
        ],
        "emitted_event_types": [],
    },
    "google_api_hub": {
        "name": "Google API Hub",
        "description": "Discover and call Google Cloud APIs via the API Hub registry.",
        "category": ConnectorCategory.developer_tools,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        ),
        "tags": ["google", "cloud", "api-hub"],
        "suite_id": "google",
        "suite_label": "Google",
        "service_order": 40,
        "tools": [
            ToolSchema(
                id="google_api_hub.call",
                name="Call API",
                description="Execute an API call discovered via the Google API Hub.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="api_id", type=ToolParameterType.string, description="API identifier in the hub"),
                    ToolParameter(name="method", type=ToolParameterType.string, description="HTTP method"),
                    ToolParameter(name="path", type=ToolParameterType.string, description="API path"),
                    ToolParameter(name="body", type=ToolParameterType.object, description="Request body", required=False),
                ],
            ),
        ],
        "emitted_event_types": [],
    },
    # ── Gmail playwright variant ──────────────────────────────────────────────
    "gmail_playwright": {
        "name": "Gmail (Browser)",
        "description": "Read and compose Gmail using browser automation — no OAuth required.",
        "category": ConnectorCategory.email,
        "auth": NoAuthConfig(),
        "tags": ["google", "email", "browser"],
        "suite_id": "google",
        "suite_label": "Google",
        "service_order": 5,
        "tools": [
            ToolSchema(
                id="gmail.send",
                name="Send email",
                description="Send an email via the Gmail browser interface.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="to", type=ToolParameterType.string, description="Recipient address"),
                    ToolParameter(name="subject", type=ToolParameterType.string, description="Subject"),
                    ToolParameter(name="body", type=ToolParameterType.string, description="Body text"),
                ],
            ),
            ToolSchema(
                id="gmail.read",
                name="Read inbox",
                description="Read recent emails from the Gmail inbox.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="max_results", type=ToolParameterType.integer, description="Max messages", required=False, default=10),
                ],
            ),
        ],
        "emitted_event_types": [],
    },
    # ── Browser / web ─────────────────────────────────────────────────────────
    "playwright_contact_form": {
        "name": "Contact Form Filler",
        "description": "Automatically fill and submit contact forms on any website.",
        "category": ConnectorCategory.data,
        "auth": NoAuthConfig(),
        "tags": ["browser", "automation", "forms"],
        "service_order": 10,
        "tools": [
            ToolSchema(
                id="contact_form.fill",
                name="Fill contact form",
                description="Detect and fill a contact form on a target URL.",
                action_class=ToolActionClass.execute,
                parameters=[
                    ToolParameter(name="url", type=ToolParameterType.string, description="Target URL"),
                    ToolParameter(name="name", type=ToolParameterType.string, description="Contact name"),
                    ToolParameter(name="email", type=ToolParameterType.string, description="Contact email"),
                    ToolParameter(name="message", type=ToolParameterType.string, description="Message body"),
                ],
            ),
        ],
        "emitted_event_types": [],
    },
    # ── Utility / data connectors ─────────────────────────────────────────────
    "bing_search": {
        "name": "Bing Search",
        "description": "Web and news search powered by the Microsoft Bing Search API.",
        "category": ConnectorCategory.data,
        "auth": ApiKeyAuthConfig(param_name="Ocp-Apim-Subscription-Key", credential_label="Bing API Key"),
        "tags": ["search", "web", "microsoft"],
        "tools": [
            ToolSchema(
                id="bing.search",
                name="Web search",
                description="Search the web using Bing.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                    ToolParameter(name="count", type=ToolParameterType.integer, description="Number of results", required=False, default=5),
                ],
            ),
            ToolSchema(
                id="bing.news",
                name="News search",
                description="Search recent news articles using Bing News.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="query", type=ToolParameterType.string, description="News search query"),
                    ToolParameter(name="count", type=ToolParameterType.integer, description="Number of articles", required=False, default=5),
                ],
            ),
        ],
        "emitted_event_types": [],
    },
    "email_validation": {
        "name": "Email Validation",
        "description": "Validate email address deliverability and syntax in real time.",
        "category": ConnectorCategory.data,
        "auth": ApiKeyAuthConfig(param_name="api_key", credential_label="Validation API Key"),
        "tags": ["email", "validation", "data-quality"],
        "tools": [
            ToolSchema(
                id="email_validation.validate",
                name="Validate email",
                description="Check whether an email address is valid and deliverable.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="email", type=ToolParameterType.string, description="Email address to validate"),
                ],
            ),
            ToolSchema(
                id="email_validation.bulk_validate",
                name="Bulk validate",
                description="Validate a list of email addresses in one call.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="emails", type=ToolParameterType.array, description="List of email addresses"),
                ],
            ),
        ],
        "emitted_event_types": [],
    },
    "invoice": {
        "name": "Invoice Processing",
        "description": "Extract structured data from invoice PDFs using OCR and AI.",
        "category": ConnectorCategory.finance,
        "auth": NoAuthConfig(),
        "tags": ["finance", "invoices", "ocr", "documents"],
        "tools": [
            ToolSchema(
                id="invoice.extract",
                name="Extract invoice data",
                description="Parse an invoice PDF and return structured fields.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="file_url", type=ToolParameterType.string, description="URL or path to the invoice PDF"),
                ],
            ),
            ToolSchema(
                id="invoice.summarize",
                name="Summarize invoice",
                description="Return a brief natural-language summary of an invoice.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="file_url", type=ToolParameterType.string, description="URL or path to the invoice PDF"),
                ],
            ),
        ],
        "emitted_event_types": [],
    },
    # ── Community & research sources ──────────────────────────────────────────
    "reddit": {
        "name": "Reddit",
        "description": "Search Reddit posts and comments for community sentiment, product feedback, and market signals.",
        "category": ConnectorCategory.data,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="Reddit API Key (Bearer token)"),
        "tags": ["reddit", "community", "social", "research"],
        "tools": [
            ToolSchema(
                id="reddit.search",
                name="Search Reddit",
                description="Search Reddit posts across all subreddits or a specific subreddit.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                    ToolParameter(name="subreddit", type=ToolParameterType.string, description="Limit to a specific subreddit (without r/)", required=False),
                    ToolParameter(name="sort", type=ToolParameterType.string, description="Sort by: relevance, new, top, hot", required=False, default="relevance"),
                    ToolParameter(name="limit", type=ToolParameterType.integer, description="Number of posts to return", required=False, default=10),
                    ToolParameter(name="time_filter", type=ToolParameterType.string, description="Time filter: hour, day, week, month, year, all", required=False, default="month"),
                ],
            ),
            ToolSchema(
                id="reddit.get_comments",
                name="Get post comments",
                description="Retrieve comments from a specific Reddit post.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="post_url", type=ToolParameterType.string, description="Full URL of the Reddit post"),
                    ToolParameter(name="limit", type=ToolParameterType.integer, description="Number of top-level comments to return", required=False, default=20),
                ],
            ),
        ],
        "emitted_event_types": [],
    },
    "newsapi": {
        "name": "NewsAPI",
        "description": "Search and retrieve news articles from thousands of global sources via the NewsAPI service.",
        "category": ConnectorCategory.data,
        "auth": ApiKeyAuthConfig(param_name="X-Api-Key", credential_label="NewsAPI Key"),
        "tags": ["news", "media", "articles", "research"],
        "tools": [
            ToolSchema(
                id="newsapi.search",
                name="Search articles",
                description="Search for news articles matching a query across all sources.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                    ToolParameter(name="from_date", type=ToolParameterType.string, description="Start date YYYY-MM-DD", required=False),
                    ToolParameter(name="to_date", type=ToolParameterType.string, description="End date YYYY-MM-DD", required=False),
                    ToolParameter(name="language", type=ToolParameterType.string, description="Language code e.g. 'en'", required=False, default="en"),
                    ToolParameter(name="page_size", type=ToolParameterType.integer, description="Number of articles to return", required=False, default=10),
                ],
            ),
            ToolSchema(
                id="newsapi.top_headlines",
                name="Top headlines",
                description="Fetch top headlines for a topic, country, or category.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="query", type=ToolParameterType.string, description="Topic to search headlines for", required=False),
                    ToolParameter(name="category", type=ToolParameterType.string, description="Category: business, technology, science, health, sports, entertainment", required=False),
                    ToolParameter(name="country", type=ToolParameterType.string, description="2-letter country code e.g. 'gb', 'us'", required=False, default="gb"),
                    ToolParameter(name="page_size", type=ToolParameterType.integer, description="Number of headlines to return", required=False, default=10),
                ],
            ),
        ],
        "emitted_event_types": [],
    },
    "sec_edgar": {
        "name": "SEC EDGAR",
        "description": "Access US public company filings from the SEC EDGAR database — 10-K, 10-Q, 8-K, S-1, and more.",
        "category": ConnectorCategory.finance,
        "auth": NoAuthConfig(),
        "tags": ["sec", "edgar", "filings", "finance", "compliance", "research"],
        "tools": [
            ToolSchema(
                id="sec_edgar.search_company",
                name="Search company",
                description="Search for a company in the SEC EDGAR database and return its CIK number.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="company_name", type=ToolParameterType.string, description="Company name to search for"),
                ],
            ),
            ToolSchema(
                id="sec_edgar.get_filings",
                name="Get filings",
                description="Retrieve recent filings for a company by CIK or ticker symbol.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="cik_or_ticker", type=ToolParameterType.string, description="CIK number or stock ticker"),
                    ToolParameter(name="form_type", type=ToolParameterType.string, description="Filing type: 10-K, 10-Q, 8-K, S-1, DEF 14A", required=False),
                    ToolParameter(name="limit", type=ToolParameterType.integer, description="Number of filings to return", required=False, default=5),
                ],
            ),
            ToolSchema(
                id="sec_edgar.get_filing_text",
                name="Get filing text",
                description="Retrieve the text content of a specific SEC filing document.",
                action_class=ToolActionClass.read,
                parameters=[
                    ToolParameter(name="filing_url", type=ToolParameterType.string, description="URL of the specific filing document"),
                    ToolParameter(name="section", type=ToolParameterType.string, description="Section to extract: risk_factors, business, mda, financials", required=False),
                ],
            ),
        ],
        "emitted_event_types": [],
    },
}


def _default_profile(connector_id: str) -> dict:
    """Fallback profile for connectors not explicitly defined above."""
    return {
        "name": connector_id.replace("_", " ").title(),
        "description": f"{connector_id} connector.",
        "category": ConnectorCategory.other,
        "auth": NoAuthConfig(),
        "tags": [],
        "tools": [],
    }


def build_definition(connector_id: str, *, enabled: bool = True) -> ConnectorDefinitionSchema:
    """Return a ConnectorDefinitionSchema for the given connector_id."""
    profile = _PROFILES.get(connector_id) or _default_profile(connector_id)
    return ConnectorDefinitionSchema(
        id=connector_id,
        name=profile["name"],
        description=profile.get("description", ""),
        auth=profile.get("auth", NoAuthConfig()),
        category=profile.get("category", ConnectorCategory.other),
        tags=list(profile.get("tags") or []),
        tools=list(profile.get("tools") or []),
        logo_url=profile.get("logo_url"),
        suite_id=profile.get("suite_id"),
        suite_label=profile.get("suite_label"),
        service_order=profile.get("service_order", 99),
        emitted_event_types=list(profile.get("emitted_event_types") or []),
        is_public=enabled,
    )


def list_definitions(*, enabled_ids: list[str] | None = None) -> list[ConnectorDefinitionSchema]:
    """Return definitions for all known connectors, or a filtered subset."""
    from api.services.agent.connectors.registry import get_connector_registry

    all_ids = get_connector_registry().names()
    ids = enabled_ids if enabled_ids is not None else all_ids
    return [build_definition(cid) for cid in ids if cid in all_ids or cid in _PROFILES]


def get_definition(connector_id: str) -> ConnectorDefinitionSchema | None:
    """Return the definition for a single connector, or None if unknown."""
    from api.services.agent.connectors.registry import get_connector_registry

    if connector_id not in get_connector_registry().names() and connector_id not in _PROFILES:
        return None
    return build_definition(connector_id)
