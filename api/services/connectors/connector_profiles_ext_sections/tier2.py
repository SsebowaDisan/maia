from __future__ import annotations

from api.schemas.connector_definition import (
    ApiKeyAuthConfig,
    BearerAuthConfig,
    ConnectorCategory,
    NoAuthConfig,
    OAuth2AuthConfig,
    ToolActionClass,
    ToolParameter,
    ToolParameterType,
    ToolSchema,
)

PROFILES_EXT_TIER2: dict[str, dict] = {
    # ══════════════════════════════════════════════════════════════════════════
    # TIER 2 — Differentiators for specific verticals
    # ══════════════════════════════════════════════════════════════════════════
    "calendly": {
        "name": "Calendly",
        "description": "Scheduling and booking — list events, manage availability, and create invite links.",
        "category": ConnectorCategory.scheduling,
        "auth": BearerAuthConfig(credential_label="Calendly Personal Access Token"),
        "tags": ["calendly", "scheduling", "booking", "meetings"],
        "tools": [
            ToolSchema(id="calendly.list_events", name="List events", description="List upcoming and past scheduled events.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="status", type=ToolParameterType.string, description="Filter: active, canceled", required=False, default="active"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="calendly.get_event_types", name="Get event types", description="List available event types and their booking links.", action_class=ToolActionClass.read, parameters=[]),
            ToolSchema(id="calendly.cancel_event", name="Cancel event", description="Cancel a scheduled Calendly event.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="event_id", type=ToolParameterType.string, description="Event UUID"),
                ToolParameter(name="reason", type=ToolParameterType.string, description="Cancellation reason", required=False),
            ]),
        ],
    },
    "docusign": {
        "name": "DocuSign",
        "description": "E-signatures — send envelopes, check signing status, and download completed documents.",
        "category": ConnectorCategory.other,
        "auth": OAuth2AuthConfig(
            authorization_url="https://account-d.docusign.com/oauth/auth",
            token_url="https://account-d.docusign.com/oauth/token",
            scopes=["signature", "impersonation"],
        ),
        "tags": ["docusign", "esignature", "legal", "contracts"],
        "tools": [
            ToolSchema(id="docusign.send_envelope", name="Send envelope", description="Create and send a DocuSign envelope for signing.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="document_url", type=ToolParameterType.string, description="URL or path to the document"),
                ToolParameter(name="signer_email", type=ToolParameterType.string, description="Signer's email"),
                ToolParameter(name="signer_name", type=ToolParameterType.string, description="Signer's name"),
                ToolParameter(name="subject", type=ToolParameterType.string, description="Email subject", required=False),
            ]),
            ToolSchema(id="docusign.get_envelope_status", name="Get status", description="Check the signing status of an envelope.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="envelope_id", type=ToolParameterType.string, description="Envelope ID")]),
            ToolSchema(id="docusign.list_envelopes", name="List envelopes", description="List recent envelopes with status.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="status", type=ToolParameterType.string, description="Filter: sent, completed, voided", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
        ],
    },
    "dropbox": {
        "name": "Dropbox",
        "description": "Cloud file storage — upload, download, search, and share files via Dropbox API.",
        "category": ConnectorCategory.storage,
        "auth": OAuth2AuthConfig(
            authorization_url="https://www.dropbox.com/oauth2/authorize",
            token_url="https://api.dropboxapi.com/oauth2/token",
            scopes=["files.content.read", "files.content.write"],
        ),
        "tags": ["dropbox", "storage", "files", "cloud"],
        "tools": [
            ToolSchema(id="dropbox.search", name="Search files", description="Search for files in Dropbox by name or content.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="query", type=ToolParameterType.string, description="Search query")]),
            ToolSchema(id="dropbox.list_folder", name="List folder", description="List files and folders at a path.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="path", type=ToolParameterType.string, description="Folder path (e.g. /Documents)")]),
            ToolSchema(id="dropbox.download", name="Download file", description="Download a file from Dropbox.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="path", type=ToolParameterType.string, description="File path")]),
            ToolSchema(id="dropbox.create_shared_link", name="Create shared link", description="Create a shared link for a file.", action_class=ToolActionClass.execute, parameters=[ToolParameter(name="path", type=ToolParameterType.string, description="File path")]),
        ],
    },
    "box": {
        "name": "Box",
        "description": "Enterprise cloud storage — files, folders, collaborations, and metadata via Box API.",
        "category": ConnectorCategory.storage,
        "auth": OAuth2AuthConfig(
            authorization_url="https://account.box.com/api/oauth2/authorize",
            token_url="https://api.box.com/oauth2/token",
            scopes=["root_readwrite"],
        ),
        "tags": ["box", "storage", "enterprise", "files"],
        "tools": [
            ToolSchema(id="box.search", name="Search files", description="Search Box for files by name, content, or metadata.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="query", type=ToolParameterType.string, description="Search query")]),
            ToolSchema(id="box.list_folder", name="List folder", description="List items in a Box folder.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="folder_id", type=ToolParameterType.string, description="Folder ID (0 for root)")]),
            ToolSchema(id="box.download", name="Download file", description="Download a file from Box.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="file_id", type=ToolParameterType.string, description="File ID")]),
            ToolSchema(id="box.upload", name="Upload file", description="Upload a file to a Box folder.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="folder_id", type=ToolParameterType.string, description="Target folder ID"),
                ToolParameter(name="file_name", type=ToolParameterType.string, description="File name"),
                ToolParameter(name="content", type=ToolParameterType.string, description="File content"),
            ]),
        ],
    },
    "confluence": {
        "name": "Confluence",
        "description": "Wiki and knowledge base — search, read, create, and update Confluence pages.",
        "category": ConnectorCategory.data,
        "auth": BearerAuthConfig(credential_label="Confluence API Token"),
        "tags": ["confluence", "atlassian", "wiki", "knowledge-base"],
        "tools": [
            ToolSchema(id="confluence.search", name="Search pages", description="Search Confluence pages by content or title.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="CQL or text search query"),
                ToolParameter(name="space_key", type=ToolParameterType.string, description="Confluence space key", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="confluence.get_page", name="Get page", description="Retrieve a Confluence page's content.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="page_id", type=ToolParameterType.string, description="Page ID")]),
            ToolSchema(id="confluence.create_page", name="Create page", description="Create a new Confluence page.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="space_key", type=ToolParameterType.string, description="Space key"),
                ToolParameter(name="title", type=ToolParameterType.string, description="Page title"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Page content (Confluence storage format or markdown)"),
                ToolParameter(name="parent_id", type=ToolParameterType.string, description="Parent page ID", required=False),
            ]),
            ToolSchema(id="confluence.update_page", name="Update page", description="Update an existing page's content.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="page_id", type=ToolParameterType.string, description="Page ID"),
                ToolParameter(name="title", type=ToolParameterType.string, description="Updated title"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Updated content"),
            ]),
        ],
    },
    "figma": {
        "name": "Figma",
        "description": "Design platform — read files, components, comments, and export assets via Figma API.",
        "category": ConnectorCategory.design,
        "auth": BearerAuthConfig(credential_label="Figma Personal Access Token"),
        "tags": ["figma", "design", "ui", "prototyping"],
        "tools": [
            ToolSchema(id="figma.get_file", name="Get file", description="Get the structure and metadata of a Figma file.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="file_key", type=ToolParameterType.string, description="Figma file key")]),
            ToolSchema(id="figma.get_comments", name="Get comments", description="List comments on a Figma file.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="file_key", type=ToolParameterType.string, description="Figma file key")]),
            ToolSchema(id="figma.post_comment", name="Post comment", description="Add a comment to a Figma file.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="file_key", type=ToolParameterType.string, description="Figma file key"),
                ToolParameter(name="message", type=ToolParameterType.string, description="Comment text"),
            ]),
            ToolSchema(id="figma.export_image", name="Export image", description="Export a Figma node as PNG, SVG, or PDF.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="file_key", type=ToolParameterType.string, description="Figma file key"),
                ToolParameter(name="node_ids", type=ToolParameterType.array, description="Node IDs to export"),
                ToolParameter(name="format", type=ToolParameterType.string, description="Export format: png, svg, pdf", required=False, default="png"),
            ]),
            ToolSchema(id="figma.get_components", name="Get components", description="List published components in a Figma file or library.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="file_key", type=ToolParameterType.string, description="Figma file key")]),
        ],
    },
    "webflow": {
        "name": "Webflow",
        "description": "CMS and site management — collections, items, and publishing via Webflow API.",
        "category": ConnectorCategory.marketing,
        "auth": BearerAuthConfig(credential_label="Webflow API Token"),
        "tags": ["webflow", "cms", "website", "marketing"],
        "tools": [
            ToolSchema(id="webflow.list_collections", name="List collections", description="List CMS collections for a Webflow site.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="site_id", type=ToolParameterType.string, description="Webflow site ID")]),
            ToolSchema(id="webflow.list_items", name="List items", description="List items in a Webflow CMS collection.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="collection_id", type=ToolParameterType.string, description="Collection ID"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max items", required=False, default=50),
            ]),
            ToolSchema(id="webflow.create_item", name="Create item", description="Create a new CMS item in a collection.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="collection_id", type=ToolParameterType.string, description="Collection ID"),
                ToolParameter(name="fields", type=ToolParameterType.object, description="Field values for the item"),
                ToolParameter(name="publish", type=ToolParameterType.boolean, description="Publish immediately", required=False, default=False),
            ]),
            ToolSchema(id="webflow.publish_site", name="Publish site", description="Publish the Webflow site to production.", action_class=ToolActionClass.execute, parameters=[ToolParameter(name="site_id", type=ToolParameterType.string, description="Site ID")]),
        ],
    },
    "supabase": {
        "name": "Supabase",
        "description": "Postgres database, auth, storage, and edge functions via Supabase API.",
        "category": ConnectorCategory.database,
        "auth": ApiKeyAuthConfig(param_name="apikey", credential_label="Supabase API Key (anon or service_role)"),
        "tags": ["supabase", "database", "postgres", "backend"],
        "tools": [
            ToolSchema(id="supabase.query", name="Query table", description="Query a Supabase table with filters and sorting.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="table", type=ToolParameterType.string, description="Table name"),
                ToolParameter(name="select", type=ToolParameterType.string, description="Columns to select", required=False, default="*"),
                ToolParameter(name="filter", type=ToolParameterType.string, description="PostgREST filter string", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max rows", required=False, default=50),
            ]),
            ToolSchema(id="supabase.insert", name="Insert row", description="Insert a new row into a Supabase table.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="table", type=ToolParameterType.string, description="Table name"),
                ToolParameter(name="data", type=ToolParameterType.object, description="Row data as key/value pairs"),
            ]),
            ToolSchema(id="supabase.update", name="Update rows", description="Update rows matching a filter.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="table", type=ToolParameterType.string, description="Table name"),
                ToolParameter(name="filter", type=ToolParameterType.string, description="PostgREST filter for rows to update"),
                ToolParameter(name="data", type=ToolParameterType.object, description="Fields to update"),
            ]),
            ToolSchema(id="supabase.rpc", name="Call function", description="Call a Supabase edge function or stored procedure.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="function_name", type=ToolParameterType.string, description="Function name"),
                ToolParameter(name="params", type=ToolParameterType.object, description="Function parameters", required=False),
            ]),
        ],
    },
    "postgresql": {
        "name": "PostgreSQL",
        "description": "Direct SQL queries against a PostgreSQL database — read, write, and manage data.",
        "category": ConnectorCategory.database,
        "auth": ApiKeyAuthConfig(param_name="connection_string", credential_label="PostgreSQL Connection String"),
        "tags": ["postgresql", "database", "sql", "data"],
        "tools": [
            ToolSchema(id="postgresql.query", name="Run query", description="Execute a read-only SQL query and return results.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="sql", type=ToolParameterType.string, description="SQL query (SELECT only)"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max rows", required=False, default=100),
            ]),
            ToolSchema(id="postgresql.execute", name="Execute SQL", description="Execute a write SQL statement (INSERT, UPDATE, DELETE).", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="sql", type=ToolParameterType.string, description="SQL statement"),
                ToolParameter(name="params", type=ToolParameterType.array, description="Parameterised query values", required=False),
            ]),
            ToolSchema(id="postgresql.list_tables", name="List tables", description="List all tables in the database.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="schema", type=ToolParameterType.string, description="Schema name", required=False, default="public")]),
            ToolSchema(id="postgresql.describe_table", name="Describe table", description="Get column names, types, and constraints for a table.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="table_name", type=ToolParameterType.string, description="Table name")]),
        ],
    },
    "bigquery": {
        "name": "BigQuery",
        "description": "Google BigQuery data warehouse — run SQL queries, list datasets, and export results.",
        "category": ConnectorCategory.database,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
        ),
        "tags": ["bigquery", "google", "data-warehouse", "sql", "analytics"],
        "suite_id": "google", "suite_label": "Google", "service_order": 50,
        "tools": [
            ToolSchema(id="bigquery.query", name="Run query", description="Execute a BigQuery SQL query.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="sql", type=ToolParameterType.string, description="Standard SQL query"),
                ToolParameter(name="project_id", type=ToolParameterType.string, description="GCP project ID"),
                ToolParameter(name="max_rows", type=ToolParameterType.integer, description="Max rows to return", required=False, default=100),
            ]),
            ToolSchema(id="bigquery.list_datasets", name="List datasets", description="List all datasets in a BigQuery project.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="project_id", type=ToolParameterType.string, description="GCP project ID")]),
            ToolSchema(id="bigquery.list_tables", name="List tables", description="List tables in a BigQuery dataset.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="project_id", type=ToolParameterType.string, description="GCP project ID"),
                ToolParameter(name="dataset_id", type=ToolParameterType.string, description="Dataset ID"),
            ]),
            ToolSchema(id="bigquery.get_schema", name="Get table schema", description="Get the schema of a BigQuery table.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="project_id", type=ToolParameterType.string, description="GCP project ID"),
                ToolParameter(name="dataset_id", type=ToolParameterType.string, description="Dataset ID"),
                ToolParameter(name="table_id", type=ToolParameterType.string, description="Table ID"),
            ]),
        ],
    },
}
