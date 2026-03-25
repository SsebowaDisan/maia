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

PROFILES_EXT_FOUNDATION_BUSINESS: dict[str, dict] = {
    # ── Productivity & Docs (upgraded from stubs) ──────────────────────────────
    "notion": {
        "name": "Notion",
        "description": "Connect Notion workspaces — search pages, query databases, create and update content.",
        "category": ConnectorCategory.data,
        "auth": BearerAuthConfig(credential_label="Notion Integration Token"),
        "tags": ["notion", "docs", "project-management", "wiki"],
        "tools": [
            ToolSchema(id="notion.search", name="Search pages", description="Search Notion pages and databases by title or content.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=10),
            ]),
            ToolSchema(id="notion.get_page", name="Get page", description="Retrieve the content of a Notion page by ID.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="page_id", type=ToolParameterType.string, description="Notion page ID")]),
            ToolSchema(id="notion.create_page", name="Create page", description="Create a new Notion page in a parent page or database.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="parent_id", type=ToolParameterType.string, description="Parent page or database ID"),
                ToolParameter(name="title", type=ToolParameterType.string, description="Page title"),
                ToolParameter(name="content", type=ToolParameterType.string, description="Markdown content for the page body"),
            ]),
            ToolSchema(id="notion.update_page", name="Update page", description="Update properties or content of an existing Notion page.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="page_id", type=ToolParameterType.string, description="Page ID to update"),
                ToolParameter(name="content", type=ToolParameterType.string, description="New content (markdown)"),
            ]),
            ToolSchema(id="notion.query_database", name="Query database", description="Query a Notion database with optional filters and sorts.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="database_id", type=ToolParameterType.string, description="Database ID"),
                ToolParameter(name="filter", type=ToolParameterType.object, description="Notion filter object", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max rows", required=False, default=50),
            ]),
        ],
    },
    # ── CRM (upgraded from stubs) ─────────────────────────────────────────────
    "hubspot": {
        "name": "HubSpot",
        "description": "CRM contacts, deals, companies, and marketing automation via HubSpot API.",
        "category": ConnectorCategory.crm,
        "auth": BearerAuthConfig(credential_label="HubSpot Private App Token"),
        "tags": ["hubspot", "crm", "marketing", "sales"],
        "tools": [
            ToolSchema(id="hubspot.search_contacts", name="Search contacts", description="Search HubSpot contacts by name, email, or custom property.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="hubspot.create_contact", name="Create contact", description="Create a new contact in HubSpot CRM.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="email", type=ToolParameterType.string, description="Contact email"),
                ToolParameter(name="first_name", type=ToolParameterType.string, description="First name"),
                ToolParameter(name="last_name", type=ToolParameterType.string, description="Last name"),
                ToolParameter(name="company", type=ToolParameterType.string, description="Company name", required=False),
                ToolParameter(name="phone", type=ToolParameterType.string, description="Phone number", required=False),
            ]),
            ToolSchema(id="hubspot.get_deals", name="Get deals", description="List deals in the pipeline with stage, value, and close date.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="pipeline_id", type=ToolParameterType.string, description="Pipeline ID", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="hubspot.create_deal", name="Create deal", description="Create a new deal in HubSpot.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="name", type=ToolParameterType.string, description="Deal name"),
                ToolParameter(name="amount", type=ToolParameterType.string, description="Deal value"),
                ToolParameter(name="stage", type=ToolParameterType.string, description="Pipeline stage"),
                ToolParameter(name="contact_id", type=ToolParameterType.string, description="Associated contact ID", required=False),
            ]),
            ToolSchema(id="hubspot.update_deal_stage", name="Update deal stage", description="Move a deal to a new pipeline stage.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="deal_id", type=ToolParameterType.string, description="Deal ID"),
                ToolParameter(name="stage", type=ToolParameterType.string, description="New pipeline stage"),
            ]),
        ],
    },
    "salesforce": {
        "name": "Salesforce",
        "description": "CRM leads, opportunities, accounts, and reports via Salesforce API.",
        "category": ConnectorCategory.crm,
        "auth": OAuth2AuthConfig(
            authorization_url="https://login.salesforce.com/services/oauth2/authorize",
            token_url="https://login.salesforce.com/services/oauth2/token",
            scopes=["api", "refresh_token"],
        ),
        "tags": ["salesforce", "crm", "sales", "enterprise"],
        "tools": [
            ToolSchema(id="salesforce.query", name="SOQL query", description="Run a SOQL query against Salesforce objects.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="query", type=ToolParameterType.string, description="SOQL query string")]),
            ToolSchema(id="salesforce.get_record", name="Get record", description="Fetch a Salesforce record by object type and ID.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="object_type", type=ToolParameterType.string, description="Object type (Lead, Account, Opportunity, Contact)"),
                ToolParameter(name="record_id", type=ToolParameterType.string, description="Salesforce record ID"),
            ]),
            ToolSchema(id="salesforce.create_record", name="Create record", description="Create a new record in Salesforce.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="object_type", type=ToolParameterType.string, description="Object type"),
                ToolParameter(name="fields", type=ToolParameterType.object, description="Field name/value pairs"),
            ]),
            ToolSchema(id="salesforce.update_record", name="Update record", description="Update fields on an existing Salesforce record.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="object_type", type=ToolParameterType.string, description="Object type"),
                ToolParameter(name="record_id", type=ToolParameterType.string, description="Record ID"),
                ToolParameter(name="fields", type=ToolParameterType.object, description="Field name/value pairs to update"),
            ]),
            ToolSchema(id="salesforce.search", name="Search records", description="Full-text search across Salesforce objects.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search text"),
                ToolParameter(name="object_types", type=ToolParameterType.array, description="Object types to search", required=False),
            ]),
        ],
    },
    # ── Project Management (upgraded from stub) ───────────────────────────────
    "jira": {
        "name": "Jira",
        "description": "Issue tracking, sprint management, and project boards via Jira Cloud API.",
        "category": ConnectorCategory.project_management,
        "auth": BearerAuthConfig(credential_label="Jira API Token"),
        "tags": ["jira", "project-management", "atlassian", "issues"],
        "tools": [
            ToolSchema(id="jira.search_issues", name="Search issues", description="Search Jira issues using JQL (Jira Query Language).", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="jql", type=ToolParameterType.string, description="JQL query, e.g. 'project = PROJ AND status = Open'"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="jira.create_issue", name="Create issue", description="Create a new Jira issue.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="project_key", type=ToolParameterType.string, description="Project key e.g. PROJ"),
                ToolParameter(name="summary", type=ToolParameterType.string, description="Issue title"),
                ToolParameter(name="description", type=ToolParameterType.string, description="Issue description"),
                ToolParameter(name="issue_type", type=ToolParameterType.string, description="Issue type: Bug, Task, Story, Epic", required=False, default="Task"),
                ToolParameter(name="assignee", type=ToolParameterType.string, description="Assignee account ID", required=False),
                ToolParameter(name="priority", type=ToolParameterType.string, description="Priority: Highest, High, Medium, Low, Lowest", required=False, default="Medium"),
            ]),
            ToolSchema(id="jira.update_issue", name="Update issue", description="Update an existing Jira issue's fields or transition its status.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="issue_key", type=ToolParameterType.string, description="Issue key e.g. PROJ-123"),
                ToolParameter(name="fields", type=ToolParameterType.object, description="Fields to update", required=False),
                ToolParameter(name="transition", type=ToolParameterType.string, description="Transition name e.g. 'In Progress', 'Done'", required=False),
            ]),
            ToolSchema(id="jira.add_comment", name="Add comment", description="Add a comment to a Jira issue.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="issue_key", type=ToolParameterType.string, description="Issue key"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Comment text"),
            ]),
            ToolSchema(id="jira.get_sprint", name="Get sprint", description="Get the active sprint and its issues for a board.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="board_id", type=ToolParameterType.string, description="Jira board ID")]),
        ],
    },
    # ── Spreadsheet-DB (upgraded from stub) ───────────────────────────────────
    "airtable": {
        "name": "Airtable",
        "description": "Spreadsheet-database hybrid — read, create, and update records in Airtable bases.",
        "category": ConnectorCategory.data,
        "auth": BearerAuthConfig(credential_label="Airtable Personal Access Token"),
        "tags": ["airtable", "database", "spreadsheet", "no-code"],
        "tools": [
            ToolSchema(id="airtable.list_records", name="List records", description="List records from an Airtable table with optional filtering.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="base_id", type=ToolParameterType.string, description="Airtable base ID"),
                ToolParameter(name="table_name", type=ToolParameterType.string, description="Table name"),
                ToolParameter(name="filter_formula", type=ToolParameterType.string, description="Airtable formula filter", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max records", required=False, default=50),
            ]),
            ToolSchema(id="airtable.create_record", name="Create record", description="Create a new record in an Airtable table.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="base_id", type=ToolParameterType.string, description="Airtable base ID"),
                ToolParameter(name="table_name", type=ToolParameterType.string, description="Table name"),
                ToolParameter(name="fields", type=ToolParameterType.object, description="Field name/value pairs"),
            ]),
            ToolSchema(id="airtable.update_record", name="Update record", description="Update an existing record in Airtable.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="base_id", type=ToolParameterType.string, description="Base ID"),
                ToolParameter(name="table_name", type=ToolParameterType.string, description="Table name"),
                ToolParameter(name="record_id", type=ToolParameterType.string, description="Record ID"),
                ToolParameter(name="fields", type=ToolParameterType.object, description="Fields to update"),
            ]),
            ToolSchema(id="airtable.search", name="Search records", description="Search Airtable records by field values.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="base_id", type=ToolParameterType.string, description="Base ID"),
                ToolParameter(name="table_name", type=ToolParameterType.string, description="Table name"),
                ToolParameter(name="query", type=ToolParameterType.string, description="Search text"),
            ]),
        ],
    },
    # ── Support (upgraded from stub) ──────────────────────────────────────────
    "zendesk": {
        "name": "Zendesk",
        "description": "Customer support tickets, knowledge base, and agent workflows via Zendesk API.",
        "category": ConnectorCategory.support,
        "auth": BearerAuthConfig(credential_label="Zendesk API Token"),
        "tags": ["zendesk", "support", "helpdesk", "tickets"],
        "tools": [
            ToolSchema(id="zendesk.search_tickets", name="Search tickets", description="Search Zendesk tickets by query, status, or assignee.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="status", type=ToolParameterType.string, description="Filter by status: new, open, pending, solved, closed", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="zendesk.create_ticket", name="Create ticket", description="Create a new support ticket.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="subject", type=ToolParameterType.string, description="Ticket subject"),
                ToolParameter(name="description", type=ToolParameterType.string, description="Ticket description"),
                ToolParameter(name="priority", type=ToolParameterType.string, description="Priority: urgent, high, normal, low", required=False, default="normal"),
                ToolParameter(name="requester_email", type=ToolParameterType.string, description="Requester email", required=False),
            ]),
            ToolSchema(id="zendesk.update_ticket", name="Update ticket", description="Update a ticket's status, assignee, or add an internal note.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="ticket_id", type=ToolParameterType.string, description="Ticket ID"),
                ToolParameter(name="status", type=ToolParameterType.string, description="New status", required=False),
                ToolParameter(name="comment", type=ToolParameterType.string, description="Public reply or internal note", required=False),
                ToolParameter(name="internal", type=ToolParameterType.boolean, description="True for internal note", required=False, default=False),
            ]),
            ToolSchema(id="zendesk.get_ticket", name="Get ticket", description="Retrieve full ticket details including comments.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="ticket_id", type=ToolParameterType.string, description="Ticket ID")]),
        ],
    },
    # ── Commerce (upgraded from stubs) ────────────────────────────────────────
    "stripe": {
        "name": "Stripe",
        "description": "Payments, subscriptions, invoices, and financial reporting via Stripe API.",
        "category": ConnectorCategory.commerce,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="Stripe Secret Key"),
        "tags": ["stripe", "payments", "commerce", "subscriptions"],
        "tools": [
            ToolSchema(id="stripe.list_charges", name="List charges", description="List recent charges with optional customer or date filters.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="customer_id", type=ToolParameterType.string, description="Stripe customer ID filter", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="stripe.get_balance", name="Get balance", description="Retrieve the current Stripe account balance.", action_class=ToolActionClass.read, parameters=[]),
            ToolSchema(id="stripe.create_invoice", name="Create invoice", description="Create and send a Stripe invoice to a customer.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="customer_id", type=ToolParameterType.string, description="Customer ID"),
                ToolParameter(name="line_items", type=ToolParameterType.array, description="List of items with description and amount"),
                ToolParameter(name="auto_send", type=ToolParameterType.boolean, description="Automatically send to customer", required=False, default=True),
            ]),
            ToolSchema(id="stripe.list_subscriptions", name="List subscriptions", description="List active subscriptions with plan and billing details.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="status", type=ToolParameterType.string, description="Filter: active, past_due, canceled, all", required=False, default="active"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="stripe.search_customers", name="Search customers", description="Search Stripe customers by email or name.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="query", type=ToolParameterType.string, description="Search query")]),
        ],
    },
    "shopify": {
        "name": "Shopify",
        "description": "E-commerce orders, products, customers, and inventory via Shopify Admin API.",
        "category": ConnectorCategory.commerce,
        "auth": BearerAuthConfig(credential_label="Shopify Admin API Access Token"),
        "tags": ["shopify", "ecommerce", "commerce", "orders"],
        "tools": [
            ToolSchema(id="shopify.list_orders", name="List orders", description="List recent orders with status and fulfillment info.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="status", type=ToolParameterType.string, description="Order status: open, closed, cancelled, any", required=False, default="any"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="shopify.get_order", name="Get order", description="Get full details of a Shopify order.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="order_id", type=ToolParameterType.string, description="Shopify order ID")]),
            ToolSchema(id="shopify.list_products", name="List products", description="List products with prices, variants, and inventory.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=50),
            ]),
            ToolSchema(id="shopify.update_product", name="Update product", description="Update a product's title, description, price, or inventory.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="product_id", type=ToolParameterType.string, description="Product ID"),
                ToolParameter(name="fields", type=ToolParameterType.object, description="Fields to update (title, body_html, price, etc.)"),
            ]),
            ToolSchema(id="shopify.search_customers", name="Search customers", description="Search Shopify customers by name or email.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="query", type=ToolParameterType.string, description="Search query")]),
        ],
    },
}
