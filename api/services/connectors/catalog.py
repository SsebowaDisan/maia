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
        "description": "Access Google Drive files and documents.",
        "category": ConnectorCategory.storage,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly",
                "https://www.googleapis.com/auth/drive.file",
            ],
        ),
        "tags": ["google", "drive"],
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
