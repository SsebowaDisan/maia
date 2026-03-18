"""Static connector tool profiles — auth configs, tool schemas, and tags.

Responsibility: pure data. Each entry maps a connector_id to enough
metadata (name, description, auth, tools, tags) to build a
ConnectorDefinitionSchema. Kept separate from the catalog builder so
each file stays focused and under 500 LOC.

This file contains Google suite, Microsoft 365, and core utility profiles.
See connector_profiles_ext.py for community, research, and monitoring profiles.
"""
from __future__ import annotations

from api.schemas.connector_definition import (
    ApiKeyAuthConfig,
    ConnectorCategory,
    NoAuthConfig,
    OAuth2AuthConfig,
    ToolActionClass,
    ToolParameter,
    ToolParameterType,
    ToolSchema,
)

PROFILES: dict[str, dict] = {
    # ── Gmail ─────────────────────────────────────────────────────────────────
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
            ToolSchema(id="gmail.send", name="Send email", description="Compose and send an email via Gmail.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="to", type=ToolParameterType.string, description="Recipient email address"),
                ToolParameter(name="subject", type=ToolParameterType.string, description="Email subject line"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Plain-text email body"),
                ToolParameter(name="cc", type=ToolParameterType.string, description="CC recipients", required=False),
            ]),
            ToolSchema(id="gmail.draft", name="Create draft", description="Save an email as a draft in Gmail without sending it.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="to", type=ToolParameterType.string, description="Recipient email address"),
                ToolParameter(name="subject", type=ToolParameterType.string, description="Email subject line"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Plain-text email body"),
                ToolParameter(name="cc", type=ToolParameterType.string, description="CC recipients", required=False),
            ]),
            ToolSchema(id="gmail.search", name="Search emails", description="Search Gmail messages using a query string.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Gmail search query, e.g. 'subject:invoice from:vendor'"),
                ToolParameter(name="max_results", type=ToolParameterType.integer, description="Maximum messages to return", required=False, default=10),
            ]),
            ToolSchema(id="gmail.read", name="Read inbox", description="Search and read Gmail messages.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Gmail search query, e.g. 'from:alice'"),
                ToolParameter(name="max_results", type=ToolParameterType.integer, description="Maximum messages to return", required=False, default=10),
            ]),
        ],
    },
    # ── Google Calendar ───────────────────────────────────────────────────────
    "google_calendar": {
        "name": "Google Calendar",
        "description": "Create, list, and manage Google Calendar events.",
        "category": ConnectorCategory.calendar,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/calendar"],
        ),
        "tags": ["google", "calendar"],
        "tools": [
            ToolSchema(id="gcalendar.create_event", name="Create event", description="Create a new Google Calendar event.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="title", type=ToolParameterType.string, description="Event title"),
                ToolParameter(name="start", type=ToolParameterType.string, description="Start datetime ISO 8601"),
                ToolParameter(name="end", type=ToolParameterType.string, description="End datetime ISO 8601"),
                ToolParameter(name="description", type=ToolParameterType.string, description="Event description", required=False),
            ]),
            ToolSchema(id="gcalendar.list_events", name="List events", description="List upcoming Google Calendar events.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="max_results", type=ToolParameterType.integer, description="Max events to return", required=False, default=10),
                ToolParameter(name="time_min", type=ToolParameterType.string, description="Start of search window (ISO 8601)", required=False),
            ]),
            ToolSchema(id="gcalendar.get_event_details", name="Get event details", description="Fetch full details of a specific Google Calendar event by ID.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="event_id", type=ToolParameterType.string, description="Google Calendar event ID"),
            ]),
            ToolSchema(id="gcalendar.list_day_events", name="List day events", description="List all events on a specific calendar day.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="date", type=ToolParameterType.string, description="Date in YYYY-MM-DD format"),
            ]),
            ToolSchema(id="gcalendar.update_event", name="Update event", description="Update the title, time, or description of an existing calendar event.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="event_id", type=ToolParameterType.string, description="Google Calendar event ID"),
                ToolParameter(name="title", type=ToolParameterType.string, description="New event title", required=False),
                ToolParameter(name="start", type=ToolParameterType.string, description="New start datetime ISO 8601", required=False),
                ToolParameter(name="end", type=ToolParameterType.string, description="New end datetime ISO 8601", required=False),
                ToolParameter(name="description", type=ToolParameterType.string, description="New event description", required=False),
            ]),
        ],
    },
    # ── Google Workspace (Drive / Docs / Sheets / Slides) ─────────────────────
    "google_workspace": {
        "name": "Google Workspace",
        "description": "Access Google Drive, Docs, Sheets, and Slides.",
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
            ToolSchema(id="gdrive.read_file", name="Read file", description="Read the contents of a Google Drive file.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="file_id", type=ToolParameterType.string, description="Google Drive file ID")]),
            ToolSchema(id="workspace.drive.search", name="Search Drive", description="Search Google Drive for files by name or type.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query, e.g. 'CRM tracker'"),
                ToolParameter(name="max_results", type=ToolParameterType.integer, description="Max files to return", required=False, default=10),
            ]),
            ToolSchema(id="workspace.sheets.read", name="Read sheet", description="Read rows from a Google Sheets spreadsheet.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="spreadsheet_id", type=ToolParameterType.string, description="Spreadsheet ID or URL"),
                ToolParameter(name="range", type=ToolParameterType.string, description="A1 notation range, e.g. 'Sheet1!A1:Z100'", required=False),
            ]),
            ToolSchema(id="workspace.sheets.append", name="Append row", description="Append a row to a Google Sheets spreadsheet.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="spreadsheet_id", type=ToolParameterType.string, description="Spreadsheet ID or URL"),
                ToolParameter(name="values", type=ToolParameterType.array, description="List of cell values for the new row"),
                ToolParameter(name="sheet_name", type=ToolParameterType.string, description="Sheet tab name", required=False, default="Sheet1"),
            ]),
            ToolSchema(id="workspace.sheets.update", name="Update cell", description="Update a specific cell or range in a Google Sheet.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="spreadsheet_id", type=ToolParameterType.string, description="Spreadsheet ID or URL"),
                ToolParameter(name="range", type=ToolParameterType.string, description="A1 notation range to update"),
                ToolParameter(name="values", type=ToolParameterType.array, description="2D array of values to write"),
            ]),
            ToolSchema(id="workspace.docs.read", name="Read doc", description="Read the text content of a Google Doc.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="document_id", type=ToolParameterType.string, description="Google Doc document ID or URL")]),
            ToolSchema(id="workspace.docs.create", name="Create doc", description="Create a new Google Doc with the given title and content.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="title", type=ToolParameterType.string, description="Document title"),
                ToolParameter(name="content", type=ToolParameterType.string, description="Markdown or plain-text body content"),
                ToolParameter(name="folder_id", type=ToolParameterType.string, description="Drive folder ID to save into", required=False),
            ]),
            ToolSchema(id="workspace.docs.fill_template", name="Fill doc template", description="Copy a Google Doc template and replace placeholder variables with provided values.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="template_id", type=ToolParameterType.string, description="Template Google Doc ID"),
                ToolParameter(name="variables", type=ToolParameterType.object, description="Key/value pairs to replace in the template"),
                ToolParameter(name="output_title", type=ToolParameterType.string, description="Title for the new document"),
            ]),
            ToolSchema(id="workspace.drive.export_as_text", name="Export file as text", description="Export a Google Drive file (PDF, Slides, Sheets) as plain text for reading.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="file_id", type=ToolParameterType.string, description="Google Drive file ID")]),
            ToolSchema(id="workspace.slides.create", name="Create presentation", description="Create a new Google Slides presentation with a title slide.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="title", type=ToolParameterType.string, description="Presentation title"),
                ToolParameter(name="folder_id", type=ToolParameterType.string, description="Drive folder ID to save into", required=False),
            ]),
            ToolSchema(id="workspace.slides.add_slide", name="Add slide", description="Add a new slide with title and body text to an existing Google Slides presentation.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="presentation_id", type=ToolParameterType.string, description="Google Slides presentation ID"),
                ToolParameter(name="slide_title", type=ToolParameterType.string, description="Slide title text"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Slide body text (bullet points, one per line)"),
                ToolParameter(name="layout", type=ToolParameterType.string, description="Slide layout: TITLE_AND_BODY, TITLE_ONLY, BLANK", required=False, default="TITLE_AND_BODY"),
            ]),
        ],
    },
    # ── Slack ─────────────────────────────────────────────────────────────────
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
            ToolSchema(id="slack.send_message", name="Send message", description="Post a message to a Slack channel.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="channel", type=ToolParameterType.string, description="Channel name or ID"),
                ToolParameter(name="text", type=ToolParameterType.string, description="Message text"),
            ]),
            ToolSchema(id="slack.read_channel", name="Read channel", description="Read recent messages from a Slack channel.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="channel", type=ToolParameterType.string, description="Channel name or ID"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Number of messages", required=False, default=20),
            ]),
            ToolSchema(id="slack.list_channels", name="List channels", description="List available Slack channels.", action_class=ToolActionClass.read, parameters=[]),
        ],
    },
    # ── Microsoft 365 ─────────────────────────────────────────────────────────
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
            ToolSchema(id="outlook.draft", name="Create draft", description="Save an email as a draft in Outlook without sending it.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="to", type=ToolParameterType.string, description="Recipient email address"),
                ToolParameter(name="subject", type=ToolParameterType.string, description="Subject line"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Email body"),
                ToolParameter(name="cc", type=ToolParameterType.string, description="CC recipients", required=False),
            ]),
            ToolSchema(id="outlook.send", name="Send email", description="Send an email via Outlook.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="to", type=ToolParameterType.string, description="Recipient email address"),
                ToolParameter(name="subject", type=ToolParameterType.string, description="Subject line"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Email body"),
            ]),
            ToolSchema(id="outlook.read", name="Read inbox", description="Read emails from Outlook inbox.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="max_results", type=ToolParameterType.integer, description="Max messages", required=False, default=10),
            ]),
        ],
    },
}
