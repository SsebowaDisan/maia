"""Extended connector tool profiles — browser, search, finance, research, monitoring.

Responsibility: pure data continuation of connector_profiles.py.
Contains utility, community, research, internal runtime, and all Tier 1-3
connector profiles (GitHub, Discord, Teams, Twilio, etc.).
"""
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

PROFILES_EXT: dict[str, dict] = {
    # ── Browser (internal runtime) ────────────────────────────────────────────
    "playwright_browser": {
        "name": "Browser",
        "description": "Browse and extract structured content from any web page using Playwright.",
        "category": ConnectorCategory.data,
        "auth": NoAuthConfig(),
        "tags": ["browser", "web", "scraping"],
        "tools": [
            ToolSchema(id="browser.navigate", name="Navigate", description="Open a URL and extract the full page text content.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="url", type=ToolParameterType.string, description="URL to navigate to")]),
            ToolSchema(id="browser.get_meta_tags", name="Get meta tags", description="Extract the title tag, meta description, and Open Graph tags from a page.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="url", type=ToolParameterType.string, description="URL to inspect")]),
            ToolSchema(id="browser.get_headings", name="Get headings", description="Extract all H1-H4 headings from a page in document order.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="url", type=ToolParameterType.string, description="URL to inspect")]),
            ToolSchema(id="browser.get_links", name="Get links", description="Extract all hyperlinks from a page with their anchor text and href.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="url", type=ToolParameterType.string, description="URL to inspect"),
                ToolParameter(name="internal_only", type=ToolParameterType.boolean, description="Return only links within the same domain", required=False, default=False),
            ]),
            ToolSchema(id="browser.extract_text", name="Extract text", description="Extract clean readable text from a specific CSS selector on a page.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="url", type=ToolParameterType.string, description="URL to inspect"),
                ToolParameter(name="selector", type=ToolParameterType.string, description="CSS selector to target (e.g. 'main', '#pricing', '.features')", required=False),
            ]),
        ],
    },
    "gmail_playwright": {
        "name": "Gmail (Browser)",
        "description": "Read and compose Gmail using browser automation — no OAuth required.",
        "category": ConnectorCategory.email,
        "auth": NoAuthConfig(),
        "tags": ["google", "email", "browser"],
        "tools": [
            ToolSchema(id="gmail_pw.send", name="Send email", description="Send an email via the Gmail browser interface.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="to", type=ToolParameterType.string, description="Recipient address"),
                ToolParameter(name="subject", type=ToolParameterType.string, description="Subject"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Body text"),
            ]),
            ToolSchema(id="gmail_pw.read", name="Read inbox", description="Read recent emails from the Gmail inbox.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="max_results", type=ToolParameterType.integer, description="Max messages", required=False, default=10),
            ]),
        ],
    },
    "playwright_contact_form": {
        "name": "Contact Form Filler",
        "description": "Automatically fill and submit contact forms on any website.",
        "category": ConnectorCategory.data,
        "auth": NoAuthConfig(),
        "tags": ["browser", "automation", "forms"],
        "tools": [
            ToolSchema(id="contact_form.fill", name="Fill contact form", description="Detect and fill a contact form on a target URL.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="url", type=ToolParameterType.string, description="Target URL"),
                ToolParameter(name="name", type=ToolParameterType.string, description="Contact name"),
                ToolParameter(name="email", type=ToolParameterType.string, description="Contact email"),
                ToolParameter(name="message", type=ToolParameterType.string, description="Message body"),
            ]),
        ],
    },
    # ── Computer Use browser (replaces Playwright) ──────────────────────────
    "computer_use_browser": {
        "name": "Computer Use Browser",
        "description": "AI-driven browser automation via Computer Use — navigates pages, fills forms, extracts content, and takes screenshots.",
        "category": ConnectorCategory.data,
        "auth": NoAuthConfig(),
        "tags": ["browser", "automation", "computer-use"],
        "tools": [
            ToolSchema(id="cu_browser.navigate", name="Navigate", description="Open a URL in the Computer Use browser and return the page content.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="url", type=ToolParameterType.string, description="URL to navigate to")]),
            ToolSchema(id="cu_browser.click", name="Click element", description="Click an element on the page identified by text or selector.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="target", type=ToolParameterType.string, description="Element text, label, or CSS selector to click"),
            ]),
            ToolSchema(id="cu_browser.type_text", name="Type text", description="Type text into a form field or input element.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="target", type=ToolParameterType.string, description="Input field label, placeholder, or selector"),
                ToolParameter(name="text", type=ToolParameterType.string, description="Text to type"),
            ]),
            ToolSchema(id="cu_browser.extract_text", name="Extract text", description="Extract visible text content from the current page.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="selector", type=ToolParameterType.string, description="CSS selector to target (optional, defaults to full page)", required=False),
            ]),
            ToolSchema(id="cu_browser.screenshot", name="Screenshot", description="Take a screenshot of the current browser viewport.", action_class=ToolActionClass.read, parameters=[]),
        ],
    },
    # ── Search ────────────────────────────────────────────────────────────────
    "brave_search": {
        "name": "Brave Search",
        "description": "Web search via the Brave Search API.",
        "category": ConnectorCategory.data,
        "auth": ApiKeyAuthConfig(param_name="X-Subscription-Token", credential_label="Brave API Key"),
        "tags": ["search", "web"],
        "tools": [
            ToolSchema(id="brave.search", name="Web search", description="Search the web using Brave Search.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="count", type=ToolParameterType.integer, description="Number of results", required=False, default=5),
            ]),
        ],
    },
    "bing_search": {
        "name": "Bing Search",
        "description": "Web and news search powered by the Microsoft Bing Search API.",
        "category": ConnectorCategory.data,
        "auth": ApiKeyAuthConfig(param_name="Ocp-Apim-Subscription-Key", credential_label="Bing API Key"),
        "tags": ["search", "web", "microsoft"],
        "tools": [
            ToolSchema(id="bing.search", name="Web search", description="Search the web using Bing.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="count", type=ToolParameterType.integer, description="Number of results", required=False, default=5),
            ]),
            ToolSchema(id="bing.news", name="News search", description="Search recent news articles using Bing News.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="News search query"),
                ToolParameter(name="count", type=ToolParameterType.integer, description="Number of articles", required=False, default=5),
            ]),
        ],
    },
    # ── Utility ───────────────────────────────────────────────────────────────
    "http_request": {
        "name": "HTTP Request",
        "description": "Make generic HTTP GET and POST requests to any API.",
        "category": ConnectorCategory.developer_tools,
        "auth": NoAuthConfig(),
        "tags": ["api", "http", "generic"],
        "tools": [
            ToolSchema(id="http.get", name="HTTP GET", description="Make an HTTP GET request.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="url", type=ToolParameterType.string, description="Request URL"),
                ToolParameter(name="headers", type=ToolParameterType.object, description="Optional request headers", required=False),
            ]),
            ToolSchema(id="http.post", name="HTTP POST", description="Make an HTTP POST request with a JSON body.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="url", type=ToolParameterType.string, description="Request URL"),
                ToolParameter(name="body", type=ToolParameterType.object, description="JSON request body"),
                ToolParameter(name="headers", type=ToolParameterType.object, description="Optional request headers", required=False),
            ]),
        ],
    },
    "email_validation": {
        "name": "Email Validation",
        "description": "Validate email address deliverability and syntax in real time.",
        "category": ConnectorCategory.data,
        "auth": ApiKeyAuthConfig(param_name="api_key", credential_label="Validation API Key"),
        "tags": ["email", "validation", "data-quality"],
        "tools": [
            ToolSchema(id="email_validation.validate", name="Validate email", description="Check whether an email address is valid and deliverable.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="email", type=ToolParameterType.string, description="Email address to validate")]),
            ToolSchema(id="email_validation.bulk_validate", name="Bulk validate", description="Validate a list of email addresses in one call.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="emails", type=ToolParameterType.array, description="List of email addresses")]),
        ],
    },
    # ── Google suite extras ───────────────────────────────────────────────────
    "google_analytics": {
        "name": "Google Analytics",
        "description": "Fetch GA4 traffic, conversion, and audience reports.",
        "category": ConnectorCategory.analytics,
        "auth": ApiKeyAuthConfig(param_name="key", credential_label="GA4 OAuth (via suite)"),
        "tags": ["google", "analytics", "ga4"],
        "suite_id": "google", "suite_label": "Google", "service_order": 10,
        "tools": [
            ToolSchema(id="analytics.ga4.report", name="GA4 Report", description="Fetch a GA4 report for a date range and set of metrics.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="property_id", type=ToolParameterType.string, description="GA4 property ID"),
                ToolParameter(name="start_date", type=ToolParameterType.string, description="Start date YYYY-MM-DD"),
                ToolParameter(name="end_date", type=ToolParameterType.string, description="End date YYYY-MM-DD"),
                ToolParameter(name="metrics", type=ToolParameterType.array, description="List of GA4 metric names", required=False),
            ]),
            ToolSchema(id="analytics.ga4.full_report", name="GA4 Full Report", description="Fetch a comprehensive GA4 report including channels and top pages.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="property_id", type=ToolParameterType.string, description="GA4 property ID"),
                ToolParameter(name="days", type=ToolParameterType.integer, description="Lookback window in days", required=False, default=7),
            ]),
        ],
    },
    "google_ads": {
        "name": "Google Ads",
        "description": "Pull campaign performance data and manage Google Ads campaigns.",
        "category": ConnectorCategory.analytics,
        "auth": ApiKeyAuthConfig(param_name="key", credential_label="Google Ads OAuth (via suite)"),
        "tags": ["google", "ads", "paid-search"],
        "suite_id": "google", "suite_label": "Google", "service_order": 20,
        "tools": [
            ToolSchema(id="google_ads.get_campaigns", name="Get campaigns", description="List all Google Ads campaigns and their performance stats.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="customer_id", type=ToolParameterType.string, description="Google Ads customer ID"),
                ToolParameter(name="start_date", type=ToolParameterType.string, description="Start date YYYY-MM-DD"),
                ToolParameter(name="end_date", type=ToolParameterType.string, description="End date YYYY-MM-DD"),
            ]),
            ToolSchema(id="google_ads.pause_campaign", name="Pause campaign", description="Pause a Google Ads campaign to stop spend immediately.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="customer_id", type=ToolParameterType.string, description="Google Ads customer ID"),
                ToolParameter(name="campaign_id", type=ToolParameterType.string, description="Campaign ID to pause"),
            ]),
            ToolSchema(id="google_ads.update_bid", name="Update bid", description="Update the CPC bid or target CPA/ROAS for a Google Ads campaign or ad group.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="customer_id", type=ToolParameterType.string, description="Google Ads customer ID"),
                ToolParameter(name="campaign_id", type=ToolParameterType.string, description="Campaign ID"),
                ToolParameter(name="bid_type", type=ToolParameterType.string, description="Bid type: cpc, target_cpa, target_roas"),
                ToolParameter(name="bid_value", type=ToolParameterType.string, description="New bid value"),
            ]),
            ToolSchema(id="google_ads.add_negative_keyword", name="Add negative keyword", description="Add a negative keyword to a campaign to block irrelevant searches.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="customer_id", type=ToolParameterType.string, description="Google Ads customer ID"),
                ToolParameter(name="campaign_id", type=ToolParameterType.string, description="Campaign ID"),
                ToolParameter(name="keyword", type=ToolParameterType.string, description="Negative keyword text"),
                ToolParameter(name="match_type", type=ToolParameterType.string, description="Match type: broad, phrase, exact", required=False, default="exact"),
            ]),
        ],
    },
    "google_maps": {
        "name": "Google Maps",
        "description": "Look up places, addresses, and route information via Google Maps.",
        "category": ConnectorCategory.data,
        "auth": ApiKeyAuthConfig(param_name="key", credential_label="Google Maps API Key"),
        "tags": ["google", "maps", "geocoding"],
        "suite_id": "google", "suite_label": "Google", "service_order": 30,
        "tools": [
            ToolSchema(id="google_maps.geocode", name="Geocode address", description="Convert a free-text address to latitude/longitude.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="address", type=ToolParameterType.string, description="Address to geocode")]),
            ToolSchema(id="google_maps.places_search", name="Places search", description="Search for nearby places matching a query.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="location", type=ToolParameterType.string, description="lat,lng centre point", required=False),
                ToolParameter(name="radius_m", type=ToolParameterType.integer, description="Search radius in metres", required=False, default=5000),
            ]),
        ],
    },
    "google_api_hub": {
        "name": "Google API Hub",
        "description": "Discover and call Google Cloud APIs via the API Hub registry.",
        "category": ConnectorCategory.developer_tools,
        "auth": NoAuthConfig(),
        "tags": ["google", "cloud", "api-hub"],
        "suite_id": "google", "suite_label": "Google", "service_order": 40,
        "tools": [
            ToolSchema(id="google_api_hub.call", name="Call API", description="Execute an API call discovered via the Google API Hub.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="api_id", type=ToolParameterType.string, description="API identifier in the hub"),
                ToolParameter(name="method", type=ToolParameterType.string, description="HTTP method"),
                ToolParameter(name="path", type=ToolParameterType.string, description="API path"),
                ToolParameter(name="body", type=ToolParameterType.object, description="Request body", required=False),
            ]),
        ],
    },
    # ── Finance ───────────────────────────────────────────────────────────────
    "invoice": {
        "name": "Invoice Processing",
        "description": "Extract structured data from invoice PDFs using OCR and AI.",
        "category": ConnectorCategory.finance,
        "auth": NoAuthConfig(),
        "tags": ["finance", "invoices", "ocr", "documents"],
        "tools": [
            ToolSchema(id="invoice.extract", name="Extract invoice data", description="Parse an invoice PDF and return structured fields.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="file_url", type=ToolParameterType.string, description="URL or path to the invoice PDF")]),
            ToolSchema(id="invoice.summarize", name="Summarize invoice", description="Return a brief natural-language summary of an invoice.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="file_url", type=ToolParameterType.string, description="URL or path to the invoice PDF")]),
            ToolSchema(id="invoice.mark_paid", name="Mark invoice paid", description="Mark an invoice as paid in the invoice system and record the payment date.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="invoice_id", type=ToolParameterType.string, description="Invoice ID to mark as paid"),
                ToolParameter(name="payment_date", type=ToolParameterType.string, description="Payment date YYYY-MM-DD", required=False),
                ToolParameter(name="payment_reference", type=ToolParameterType.string, description="Payment reference or transaction ID", required=False),
            ]),
            ToolSchema(id="invoice.create_invoice", name="Create invoice", description="Create a new invoice with line items and send to the specified recipient.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="recipient_email", type=ToolParameterType.string, description="Recipient email address"),
                ToolParameter(name="line_items", type=ToolParameterType.array, description="List of line item objects with description, quantity, unit_price"),
                ToolParameter(name="due_date", type=ToolParameterType.string, description="Due date YYYY-MM-DD", required=False),
                ToolParameter(name="currency", type=ToolParameterType.string, description="Currency code e.g. GBP, USD, EUR", required=False, default="GBP"),
            ]),
        ],
    },
    # ── Research / community ──────────────────────────────────────────────────
    "reddit": {
        "name": "Reddit",
        "description": "Search Reddit posts and comments for community sentiment, product feedback, and market signals.",
        "category": ConnectorCategory.data,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="Reddit API Key (Bearer token)"),
        "tags": ["reddit", "community", "social", "research"],
        "tools": [
            ToolSchema(id="reddit.search", name="Search Reddit", description="Search Reddit posts across all subreddits or a specific subreddit.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="subreddit", type=ToolParameterType.string, description="Limit to a specific subreddit (without r/)", required=False),
                ToolParameter(name="sort", type=ToolParameterType.string, description="Sort by: relevance, new, top, hot", required=False, default="relevance"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Number of posts to return", required=False, default=10),
                ToolParameter(name="time_filter", type=ToolParameterType.string, description="Time filter: hour, day, week, month, year, all", required=False, default="month"),
            ]),
            ToolSchema(id="reddit.get_comments", name="Get post comments", description="Retrieve comments from a specific Reddit post.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="post_url", type=ToolParameterType.string, description="Full URL of the Reddit post"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Number of top-level comments to return", required=False, default=20),
            ]),
        ],
    },
    "newsapi": {
        "name": "NewsAPI",
        "description": "Search and retrieve news articles from thousands of global sources via the NewsAPI service.",
        "category": ConnectorCategory.data,
        "auth": ApiKeyAuthConfig(param_name="X-Api-Key", credential_label="NewsAPI Key"),
        "tags": ["news", "media", "articles", "research"],
        "tools": [
            ToolSchema(id="newsapi.search", name="Search articles", description="Search for news articles matching a query across all sources.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="from_date", type=ToolParameterType.string, description="Start date YYYY-MM-DD", required=False),
                ToolParameter(name="to_date", type=ToolParameterType.string, description="End date YYYY-MM-DD", required=False),
                ToolParameter(name="language", type=ToolParameterType.string, description="Language code e.g. 'en'", required=False, default="en"),
                ToolParameter(name="page_size", type=ToolParameterType.integer, description="Number of articles to return", required=False, default=10),
            ]),
            ToolSchema(id="newsapi.top_headlines", name="Top headlines", description="Fetch top headlines for a topic, country, or category.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Topic to search headlines for", required=False),
                ToolParameter(name="category", type=ToolParameterType.string, description="Category: business, technology, science, health, sports, entertainment", required=False),
                ToolParameter(name="country", type=ToolParameterType.string, description="2-letter country code e.g. 'gb', 'us'", required=False, default="gb"),
                ToolParameter(name="page_size", type=ToolParameterType.integer, description="Number of headlines to return", required=False, default=10),
            ]),
        ],
    },
    "sec_edgar": {
        "name": "SEC EDGAR",
        "description": "Access US public company filings from the SEC EDGAR database.",
        "category": ConnectorCategory.finance,
        "auth": NoAuthConfig(),
        "tags": ["sec", "edgar", "filings", "finance", "compliance", "research"],
        "tools": [
            ToolSchema(id="sec_edgar.search_company", name="Search company", description="Search for a company in the SEC EDGAR database and return its CIK number.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="company_name", type=ToolParameterType.string, description="Company name to search for")]),
            ToolSchema(id="sec_edgar.get_filings", name="Get filings", description="Retrieve recent filings for a company by CIK or ticker symbol.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="cik_or_ticker", type=ToolParameterType.string, description="CIK number or stock ticker"),
                ToolParameter(name="form_type", type=ToolParameterType.string, description="Filing type: 10-K, 10-Q, 8-K, S-1, DEF 14A", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Number of filings to return", required=False, default=5),
            ]),
            ToolSchema(id="sec_edgar.get_filing_text", name="Get filing text", description="Retrieve the text content of a specific SEC filing document.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="filing_url", type=ToolParameterType.string, description="URL of the specific filing document"),
                ToolParameter(name="section", type=ToolParameterType.string, description="Section to extract: risk_factors, business, mda, financials", required=False),
            ]),
        ],
    },
    # ── Monitoring ────────────────────────────────────────────────────────────
    "page_monitor": {
        "name": "Page Monitor",
        "description": "Register URLs for automated change detection. Maia tracks content hashes and notifies when pages change.",
        "category": ConnectorCategory.data,
        "auth": NoAuthConfig(),
        "tags": ["monitoring", "change-detection", "competitor", "web"],
        "emitted_event_types": ["page_changed", "page_unreachable"],
        "tools": [
            ToolSchema(id="page_monitor.register_url", name="Register URL", description="Register a URL for automated content change monitoring.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="url", type=ToolParameterType.string, description="URL to monitor"),
                ToolParameter(name="label", type=ToolParameterType.string, description="Human-readable label for this URL", required=False),
                ToolParameter(name="check_interval_hours", type=ToolParameterType.integer, description="How often to check for changes in hours", required=False, default=24),
            ]),
            ToolSchema(id="page_monitor.list_monitored", name="List monitored URLs", description="List all URLs currently registered for change monitoring.", action_class=ToolActionClass.read, parameters=[]),
            ToolSchema(id="page_monitor.unregister_url", name="Unregister URL", description="Stop monitoring a previously registered URL.", action_class=ToolActionClass.execute, parameters=[ToolParameter(name="url", type=ToolParameterType.string, description="URL to stop monitoring")]),
        ],
    },
    # ── Enterprise ─────────────────────────────────────────────────────────────
    "sap": {
        "name": "SAP",
        "description": "Connect to SAP ERP and S/4HANA for purchase orders, invoices, master data, and enterprise workflow automation.",
        "category": ConnectorCategory.commerce,
        "auth": NoAuthConfig(),
        "tags": ["sap", "erp", "enterprise", "finance", "procurement"],
        "tools": [
            ToolSchema(id="sap.read_purchase_order", name="Read purchase order", description="Retrieve a purchase order by document number from SAP.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="document_number", type=ToolParameterType.string, description="SAP purchase order document number"),
            ]),
            ToolSchema(id="sap.list_purchase_orders", name="List purchase orders", description="List recent purchase orders filtered by vendor, date range, or status.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="vendor_id", type=ToolParameterType.string, description="SAP vendor ID", required=False),
                ToolParameter(name="date_from", type=ToolParameterType.string, description="Start date YYYY-MM-DD", required=False),
                ToolParameter(name="date_to", type=ToolParameterType.string, description="End date YYYY-MM-DD", required=False),
                ToolParameter(name="status", type=ToolParameterType.string, description="Order status filter", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results to return", required=False, default=25),
            ]),
            ToolSchema(id="sap.create_purchase_order", name="Create purchase order", description="Create a new purchase order in SAP with line items.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="vendor_id", type=ToolParameterType.string, description="SAP vendor ID"),
                ToolParameter(name="company_code", type=ToolParameterType.string, description="SAP company code"),
                ToolParameter(name="line_items", type=ToolParameterType.array, description="List of line item objects with material, quantity, unit_price"),
                ToolParameter(name="delivery_date", type=ToolParameterType.string, description="Requested delivery date YYYY-MM-DD", required=False),
            ]),
            ToolSchema(id="sap.read_invoice", name="Read invoice", description="Retrieve an invoice document from SAP by number.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="invoice_number", type=ToolParameterType.string, description="SAP invoice document number"),
            ]),
            ToolSchema(id="sap.get_material_master", name="Get material master", description="Look up a material master record by material number.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="material_number", type=ToolParameterType.string, description="SAP material number"),
            ]),
            ToolSchema(id="sap.post_goods_receipt", name="Post goods receipt", description="Post a goods receipt against a purchase order in SAP.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="purchase_order", type=ToolParameterType.string, description="Purchase order document number"),
                ToolParameter(name="line_items", type=ToolParameterType.array, description="List of items with material, quantity received"),
                ToolParameter(name="posting_date", type=ToolParameterType.string, description="Posting date YYYY-MM-DD", required=False),
            ]),
        ],
    },
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
    # ══════════════════════════════════════════════════════════════════════════
    # TIER 1 — Essential connectors (every competitor has these)
    # ══════════════════════════════════════════════════════════════════════════
    "github": {
        "name": "GitHub",
        "description": "Repositories, issues, pull requests, and Actions via GitHub API.",
        "category": ConnectorCategory.developer_tools,
        "auth": BearerAuthConfig(credential_label="GitHub Personal Access Token"),
        "tags": ["github", "git", "developer", "code"],
        "tools": [
            ToolSchema(id="github.list_repos", name="List repos", description="List repositories for the authenticated user or an organisation.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="org", type=ToolParameterType.string, description="Organisation name (omit for personal repos)", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="github.search_issues", name="Search issues", description="Search issues and PRs across repositories.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="GitHub search query"),
                ToolParameter(name="repo", type=ToolParameterType.string, description="Limit to repo (owner/repo)", required=False),
            ]),
            ToolSchema(id="github.create_issue", name="Create issue", description="Create a new issue in a GitHub repository.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="repo", type=ToolParameterType.string, description="Repository (owner/repo)"),
                ToolParameter(name="title", type=ToolParameterType.string, description="Issue title"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Issue body (markdown)"),
                ToolParameter(name="labels", type=ToolParameterType.array, description="Labels to apply", required=False),
                ToolParameter(name="assignees", type=ToolParameterType.array, description="Assignee usernames", required=False),
            ]),
            ToolSchema(id="github.get_pr", name="Get pull request", description="Get details of a pull request including diff stats.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="repo", type=ToolParameterType.string, description="Repository (owner/repo)"),
                ToolParameter(name="pr_number", type=ToolParameterType.integer, description="PR number"),
            ]),
            ToolSchema(id="github.create_pr", name="Create pull request", description="Open a new pull request.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="repo", type=ToolParameterType.string, description="Repository (owner/repo)"),
                ToolParameter(name="title", type=ToolParameterType.string, description="PR title"),
                ToolParameter(name="body", type=ToolParameterType.string, description="PR description"),
                ToolParameter(name="head", type=ToolParameterType.string, description="Source branch"),
                ToolParameter(name="base", type=ToolParameterType.string, description="Target branch", required=False, default="main"),
            ]),
            ToolSchema(id="github.get_file", name="Get file contents", description="Read a file from a GitHub repository.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="repo", type=ToolParameterType.string, description="Repository (owner/repo)"),
                ToolParameter(name="path", type=ToolParameterType.string, description="File path in the repo"),
                ToolParameter(name="ref", type=ToolParameterType.string, description="Branch or commit SHA", required=False, default="main"),
            ]),
            ToolSchema(id="github.list_actions_runs", name="List workflow runs", description="List recent GitHub Actions workflow runs.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="repo", type=ToolParameterType.string, description="Repository (owner/repo)"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=10),
            ]),
        ],
    },
    "linear": {
        "name": "Linear",
        "description": "Modern issue tracking — create, update, and search issues, projects, and cycles.",
        "category": ConnectorCategory.project_management,
        "auth": BearerAuthConfig(credential_label="Linear API Key"),
        "tags": ["linear", "project-management", "issues", "engineering"],
        "tools": [
            ToolSchema(id="linear.search_issues", name="Search issues", description="Search Linear issues by text, status, or assignee.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="team", type=ToolParameterType.string, description="Team key filter", required=False),
                ToolParameter(name="status", type=ToolParameterType.string, description="Status filter", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="linear.create_issue", name="Create issue", description="Create a new Linear issue.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="team_id", type=ToolParameterType.string, description="Team ID"),
                ToolParameter(name="title", type=ToolParameterType.string, description="Issue title"),
                ToolParameter(name="description", type=ToolParameterType.string, description="Issue description (markdown)", required=False),
                ToolParameter(name="priority", type=ToolParameterType.integer, description="Priority 0-4 (0=none, 1=urgent, 4=low)", required=False),
                ToolParameter(name="assignee_id", type=ToolParameterType.string, description="Assignee user ID", required=False),
            ]),
            ToolSchema(id="linear.update_issue", name="Update issue", description="Update a Linear issue's status, assignee, or priority.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="issue_id", type=ToolParameterType.string, description="Issue ID"),
                ToolParameter(name="status", type=ToolParameterType.string, description="New status", required=False),
                ToolParameter(name="priority", type=ToolParameterType.integer, description="New priority", required=False),
                ToolParameter(name="assignee_id", type=ToolParameterType.string, description="New assignee", required=False),
            ]),
            ToolSchema(id="linear.get_cycles", name="Get cycles", description="List active and upcoming cycles for a team.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="team_id", type=ToolParameterType.string, description="Team ID")]),
        ],
    },
    "asana": {
        "name": "Asana",
        "description": "Project and task management — create tasks, track progress, and manage teams.",
        "category": ConnectorCategory.project_management,
        "auth": BearerAuthConfig(credential_label="Asana Personal Access Token"),
        "tags": ["asana", "project-management", "tasks", "teams"],
        "tools": [
            ToolSchema(id="asana.search_tasks", name="Search tasks", description="Search tasks across Asana projects and workspaces.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search text"),
                ToolParameter(name="project_id", type=ToolParameterType.string, description="Filter to project", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="asana.create_task", name="Create task", description="Create a new task in an Asana project.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="project_id", type=ToolParameterType.string, description="Project ID"),
                ToolParameter(name="name", type=ToolParameterType.string, description="Task name"),
                ToolParameter(name="notes", type=ToolParameterType.string, description="Task description", required=False),
                ToolParameter(name="due_date", type=ToolParameterType.string, description="Due date YYYY-MM-DD", required=False),
                ToolParameter(name="assignee", type=ToolParameterType.string, description="Assignee email or user ID", required=False),
            ]),
            ToolSchema(id="asana.update_task", name="Update task", description="Update a task's status, assignee, or due date.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="task_id", type=ToolParameterType.string, description="Task ID"),
                ToolParameter(name="completed", type=ToolParameterType.boolean, description="Mark complete/incomplete", required=False),
                ToolParameter(name="due_date", type=ToolParameterType.string, description="New due date", required=False),
                ToolParameter(name="assignee", type=ToolParameterType.string, description="New assignee", required=False),
            ]),
            ToolSchema(id="asana.list_projects", name="List projects", description="List projects in a workspace.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="workspace_id", type=ToolParameterType.string, description="Workspace ID")]),
        ],
    },
    "monday": {
        "name": "Monday.com",
        "description": "Work OS — boards, items, columns, and automations via Monday.com API.",
        "category": ConnectorCategory.project_management,
        "auth": BearerAuthConfig(credential_label="Monday.com API Token"),
        "tags": ["monday", "project-management", "boards", "work-os"],
        "tools": [
            ToolSchema(id="monday.list_boards", name="List boards", description="List all boards accessible to the authenticated user.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20)]),
            ToolSchema(id="monday.get_items", name="Get items", description="Get items from a Monday.com board with column values.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="board_id", type=ToolParameterType.string, description="Board ID"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max items", required=False, default=50),
            ]),
            ToolSchema(id="monday.create_item", name="Create item", description="Create a new item on a Monday.com board.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="board_id", type=ToolParameterType.string, description="Board ID"),
                ToolParameter(name="item_name", type=ToolParameterType.string, description="Item name"),
                ToolParameter(name="column_values", type=ToolParameterType.object, description="Column values as JSON", required=False),
                ToolParameter(name="group_id", type=ToolParameterType.string, description="Group ID to add item to", required=False),
            ]),
            ToolSchema(id="monday.update_item", name="Update item", description="Update column values on an existing item.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="board_id", type=ToolParameterType.string, description="Board ID"),
                ToolParameter(name="item_id", type=ToolParameterType.string, description="Item ID"),
                ToolParameter(name="column_values", type=ToolParameterType.object, description="Column values to update"),
            ]),
        ],
    },
    "trello": {
        "name": "Trello",
        "description": "Kanban boards — cards, lists, and checklists via Trello API.",
        "category": ConnectorCategory.project_management,
        "auth": ApiKeyAuthConfig(param_name="key", credential_label="Trello API Key + Token"),
        "tags": ["trello", "kanban", "boards", "project-management"],
        "tools": [
            ToolSchema(id="trello.list_boards", name="List boards", description="List all Trello boards for the authenticated user.", action_class=ToolActionClass.read, parameters=[]),
            ToolSchema(id="trello.get_cards", name="Get cards", description="Get all cards on a Trello board.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="board_id", type=ToolParameterType.string, description="Board ID")]),
            ToolSchema(id="trello.create_card", name="Create card", description="Create a new Trello card on a list.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="list_id", type=ToolParameterType.string, description="List ID"),
                ToolParameter(name="name", type=ToolParameterType.string, description="Card name"),
                ToolParameter(name="description", type=ToolParameterType.string, description="Card description", required=False),
                ToolParameter(name="due_date", type=ToolParameterType.string, description="Due date", required=False),
            ]),
            ToolSchema(id="trello.move_card", name="Move card", description="Move a card to a different list.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="card_id", type=ToolParameterType.string, description="Card ID"),
                ToolParameter(name="list_id", type=ToolParameterType.string, description="Destination list ID"),
            ]),
        ],
    },
    "discord": {
        "name": "Discord",
        "description": "Send messages, manage channels, and interact with Discord communities via bot API.",
        "category": ConnectorCategory.communication,
        "auth": BearerAuthConfig(credential_label="Discord Bot Token"),
        "tags": ["discord", "messaging", "community", "chat"],
        "tools": [
            ToolSchema(id="discord.send_message", name="Send message", description="Send a message to a Discord channel.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="channel_id", type=ToolParameterType.string, description="Channel ID"),
                ToolParameter(name="content", type=ToolParameterType.string, description="Message text"),
            ]),
            ToolSchema(id="discord.read_messages", name="Read messages", description="Read recent messages from a Discord channel.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="channel_id", type=ToolParameterType.string, description="Channel ID"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Number of messages", required=False, default=20),
            ]),
            ToolSchema(id="discord.list_channels", name="List channels", description="List channels in a Discord server.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="guild_id", type=ToolParameterType.string, description="Server/guild ID")]),
            ToolSchema(id="discord.create_thread", name="Create thread", description="Create a new thread in a channel.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="channel_id", type=ToolParameterType.string, description="Channel ID"),
                ToolParameter(name="name", type=ToolParameterType.string, description="Thread name"),
                ToolParameter(name="message", type=ToolParameterType.string, description="Initial message"),
            ]),
        ],
    },
    "microsoft_teams": {
        "name": "Microsoft Teams",
        "description": "Send messages, manage channels, and schedule meetings in Microsoft Teams.",
        "category": ConnectorCategory.communication,
        "auth": OAuth2AuthConfig(
            authorization_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
            scopes=["ChannelMessage.Send", "Channel.ReadBasic.All", "Chat.ReadWrite"],
        ),
        "tags": ["microsoft", "teams", "messaging", "enterprise"],
        "suite_id": "microsoft", "suite_label": "Microsoft 365", "service_order": 10,
        "tools": [
            ToolSchema(id="teams.send_message", name="Send message", description="Send a message to a Teams channel.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="team_id", type=ToolParameterType.string, description="Team ID"),
                ToolParameter(name="channel_id", type=ToolParameterType.string, description="Channel ID"),
                ToolParameter(name="content", type=ToolParameterType.string, description="Message text (supports HTML)"),
            ]),
            ToolSchema(id="teams.read_messages", name="Read messages", description="Read recent messages from a Teams channel.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="team_id", type=ToolParameterType.string, description="Team ID"),
                ToolParameter(name="channel_id", type=ToolParameterType.string, description="Channel ID"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max messages", required=False, default=20),
            ]),
            ToolSchema(id="teams.list_channels", name="List channels", description="List channels in a Team.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="team_id", type=ToolParameterType.string, description="Team ID")]),
            ToolSchema(id="teams.list_teams", name="List teams", description="List all teams the user is a member of.", action_class=ToolActionClass.read, parameters=[]),
        ],
    },
    "twilio": {
        "name": "Twilio",
        "description": "Send SMS, WhatsApp messages, and make calls via Twilio API.",
        "category": ConnectorCategory.communication,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="Twilio Account SID + Auth Token"),
        "tags": ["twilio", "sms", "whatsapp", "voice", "messaging"],
        "tools": [
            ToolSchema(id="twilio.send_sms", name="Send SMS", description="Send an SMS message via Twilio.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="to", type=ToolParameterType.string, description="Recipient phone number (+E.164 format)"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Message text"),
                ToolParameter(name="from_number", type=ToolParameterType.string, description="Twilio phone number to send from", required=False),
            ]),
            ToolSchema(id="twilio.send_whatsapp", name="Send WhatsApp", description="Send a WhatsApp message via Twilio.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="to", type=ToolParameterType.string, description="Recipient WhatsApp number"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Message text"),
            ]),
            ToolSchema(id="twilio.list_messages", name="List messages", description="List recent inbound and outbound messages.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
                ToolParameter(name="to", type=ToolParameterType.string, description="Filter by recipient", required=False),
            ]),
        ],
    },
    "intercom": {
        "name": "Intercom",
        "description": "Customer messaging platform — conversations, contacts, and articles via Intercom API.",
        "category": ConnectorCategory.support,
        "auth": BearerAuthConfig(credential_label="Intercom Access Token"),
        "tags": ["intercom", "support", "messaging", "customer-success"],
        "tools": [
            ToolSchema(id="intercom.search_contacts", name="Search contacts", description="Search Intercom contacts by name or email.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="query", type=ToolParameterType.string, description="Search query")]),
            ToolSchema(id="intercom.list_conversations", name="List conversations", description="List recent conversations with status and assignee.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="status", type=ToolParameterType.string, description="Filter: open, closed, snoozed", required=False, default="open"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="intercom.reply_conversation", name="Reply to conversation", description="Send a reply in an Intercom conversation.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="conversation_id", type=ToolParameterType.string, description="Conversation ID"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Reply text"),
                ToolParameter(name="message_type", type=ToolParameterType.string, description="Type: comment (public) or note (internal)", required=False, default="comment"),
            ]),
            ToolSchema(id="intercom.create_article", name="Create article", description="Create a help centre article.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="title", type=ToolParameterType.string, description="Article title"),
                ToolParameter(name="body", type=ToolParameterType.string, description="Article content (HTML)"),
                ToolParameter(name="collection_id", type=ToolParameterType.string, description="Collection to add article to", required=False),
            ]),
        ],
    },
    "mailchimp": {
        "name": "Mailchimp",
        "description": "Email marketing — campaigns, audiences, and templates via Mailchimp API.",
        "category": ConnectorCategory.marketing,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="Mailchimp API Key"),
        "tags": ["mailchimp", "email", "marketing", "campaigns"],
        "tools": [
            ToolSchema(id="mailchimp.list_campaigns", name="List campaigns", description="List email campaigns with send stats.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="status", type=ToolParameterType.string, description="Filter: sent, draft, schedule", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="mailchimp.get_campaign_report", name="Campaign report", description="Get open rate, click rate, and bounce stats for a campaign.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="campaign_id", type=ToolParameterType.string, description="Campaign ID")]),
            ToolSchema(id="mailchimp.add_subscriber", name="Add subscriber", description="Add a subscriber to a Mailchimp audience.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="list_id", type=ToolParameterType.string, description="Audience/list ID"),
                ToolParameter(name="email", type=ToolParameterType.string, description="Subscriber email"),
                ToolParameter(name="first_name", type=ToolParameterType.string, description="First name", required=False),
                ToolParameter(name="last_name", type=ToolParameterType.string, description="Last name", required=False),
                ToolParameter(name="tags", type=ToolParameterType.array, description="Tags to apply", required=False),
            ]),
            ToolSchema(id="mailchimp.search_members", name="Search members", description="Search audience members by email or name.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="list_id", type=ToolParameterType.string, description="Audience/list ID"),
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
            ]),
        ],
    },
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
    # ══════════════════════════════════════════════════════════════════════════
    # TIER 3 — Industry-specific, high value
    # ══════════════════════════════════════════════════════════════════════════
    "quickbooks": {
        "name": "QuickBooks",
        "description": "Accounting — invoices, expenses, customers, and reports via QuickBooks Online API.",
        "category": ConnectorCategory.accounting,
        "auth": OAuth2AuthConfig(
            authorization_url="https://appcenter.intuit.com/connect/oauth2",
            token_url="https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer",
            scopes=["com.intuit.quickbooks.accounting"],
        ),
        "tags": ["quickbooks", "accounting", "invoices", "finance"],
        "tools": [
            ToolSchema(id="quickbooks.list_invoices", name="List invoices", description="List recent invoices with amount and status.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="status", type=ToolParameterType.string, description="Filter: paid, unpaid, overdue", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="quickbooks.create_invoice", name="Create invoice", description="Create a new invoice for a customer.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="customer_id", type=ToolParameterType.string, description="Customer ID"),
                ToolParameter(name="line_items", type=ToolParameterType.array, description="Line items with description, quantity, rate"),
                ToolParameter(name="due_date", type=ToolParameterType.string, description="Due date YYYY-MM-DD", required=False),
            ]),
            ToolSchema(id="quickbooks.get_profit_loss", name="Profit & Loss", description="Get a profit and loss report for a date range.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="start_date", type=ToolParameterType.string, description="Start date YYYY-MM-DD"),
                ToolParameter(name="end_date", type=ToolParameterType.string, description="End date YYYY-MM-DD"),
            ]),
            ToolSchema(id="quickbooks.list_customers", name="List customers", description="List customers with balance info.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=50)]),
        ],
    },
    "xero": {
        "name": "Xero",
        "description": "Cloud accounting — invoices, bank transactions, contacts, and reports via Xero API.",
        "category": ConnectorCategory.accounting,
        "auth": OAuth2AuthConfig(
            authorization_url="https://login.xero.com/identity/connect/authorize",
            token_url="https://identity.xero.com/connect/token",
            scopes=["openid", "accounting.transactions", "accounting.contacts"],
        ),
        "tags": ["xero", "accounting", "invoices", "finance"],
        "tools": [
            ToolSchema(id="xero.list_invoices", name="List invoices", description="List invoices with status and amounts.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="status", type=ToolParameterType.string, description="Filter: DRAFT, SUBMITTED, AUTHORISED, PAID", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="xero.create_invoice", name="Create invoice", description="Create a new sales invoice.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="contact_id", type=ToolParameterType.string, description="Contact ID"),
                ToolParameter(name="line_items", type=ToolParameterType.array, description="Line items with description, quantity, unit_amount"),
                ToolParameter(name="due_date", type=ToolParameterType.string, description="Due date YYYY-MM-DD", required=False),
            ]),
            ToolSchema(id="xero.get_profit_loss", name="Profit & Loss", description="Get a profit and loss report.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="from_date", type=ToolParameterType.string, description="Start date YYYY-MM-DD"),
                ToolParameter(name="to_date", type=ToolParameterType.string, description="End date YYYY-MM-DD"),
            ]),
            ToolSchema(id="xero.list_contacts", name="List contacts", description="List contacts (customers and suppliers).", action_class=ToolActionClass.read, parameters=[ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=50)]),
        ],
    },
    "zapier_webhooks": {
        "name": "Zapier Webhooks",
        "description": "Trigger Zapier workflows via webhooks — bridge Maia agents to 6,000+ apps.",
        "category": ConnectorCategory.other,
        "auth": NoAuthConfig(),
        "tags": ["zapier", "webhooks", "automation", "integration"],
        "tools": [
            ToolSchema(id="zapier.trigger_webhook", name="Trigger webhook", description="Send a POST request to a Zapier webhook URL to trigger a Zap.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="webhook_url", type=ToolParameterType.string, description="Zapier webhook URL"),
                ToolParameter(name="data", type=ToolParameterType.object, description="JSON payload to send"),
            ]),
        ],
    },
    "make": {
        "name": "Make (Integromat)",
        "description": "Trigger Make scenarios via webhooks and retrieve scenario run status.",
        "category": ConnectorCategory.other,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="Make API Token"),
        "tags": ["make", "integromat", "automation", "integration"],
        "tools": [
            ToolSchema(id="make.trigger_scenario", name="Trigger scenario", description="Trigger a Make scenario via its webhook URL.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="webhook_url", type=ToolParameterType.string, description="Make webhook URL"),
                ToolParameter(name="data", type=ToolParameterType.object, description="JSON payload"),
            ]),
            ToolSchema(id="make.list_scenarios", name="List scenarios", description="List available Make scenarios.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20)]),
        ],
    },
    "aws": {
        "name": "AWS",
        "description": "Amazon Web Services — S3 file management, Lambda invocations, and CloudWatch metrics.",
        "category": ConnectorCategory.cloud,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="AWS Access Key + Secret Key"),
        "tags": ["aws", "cloud", "s3", "lambda", "infrastructure"],
        "tools": [
            ToolSchema(id="aws.s3_list", name="List S3 objects", description="List objects in an S3 bucket with optional prefix.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="bucket", type=ToolParameterType.string, description="S3 bucket name"),
                ToolParameter(name="prefix", type=ToolParameterType.string, description="Object prefix filter", required=False),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max objects", required=False, default=50),
            ]),
            ToolSchema(id="aws.s3_get", name="Get S3 object", description="Download/read an object from S3.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="bucket", type=ToolParameterType.string, description="Bucket name"),
                ToolParameter(name="key", type=ToolParameterType.string, description="Object key"),
            ]),
            ToolSchema(id="aws.s3_put", name="Put S3 object", description="Upload content to S3.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="bucket", type=ToolParameterType.string, description="Bucket name"),
                ToolParameter(name="key", type=ToolParameterType.string, description="Object key"),
                ToolParameter(name="content", type=ToolParameterType.string, description="Content to upload"),
            ]),
            ToolSchema(id="aws.lambda_invoke", name="Invoke Lambda", description="Invoke an AWS Lambda function.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="function_name", type=ToolParameterType.string, description="Lambda function name or ARN"),
                ToolParameter(name="payload", type=ToolParameterType.object, description="JSON payload", required=False),
            ]),
            ToolSchema(id="aws.cloudwatch_query", name="CloudWatch query", description="Query CloudWatch metrics for a service.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="namespace", type=ToolParameterType.string, description="CloudWatch namespace (e.g. AWS/EC2)"),
                ToolParameter(name="metric_name", type=ToolParameterType.string, description="Metric name"),
                ToolParameter(name="period_hours", type=ToolParameterType.integer, description="Lookback period in hours", required=False, default=24),
            ]),
        ],
    },
    "cloudflare": {
        "name": "Cloudflare",
        "description": "DNS, security, and performance — manage zones, DNS records, and view analytics.",
        "category": ConnectorCategory.cloud,
        "auth": BearerAuthConfig(credential_label="Cloudflare API Token"),
        "tags": ["cloudflare", "dns", "security", "cdn", "cloud"],
        "tools": [
            ToolSchema(id="cloudflare.list_zones", name="List zones", description="List all DNS zones in the Cloudflare account.", action_class=ToolActionClass.read, parameters=[]),
            ToolSchema(id="cloudflare.list_dns_records", name="List DNS records", description="List DNS records for a zone.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="zone_id", type=ToolParameterType.string, description="Zone ID")]),
            ToolSchema(id="cloudflare.create_dns_record", name="Create DNS record", description="Create a new DNS record.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="zone_id", type=ToolParameterType.string, description="Zone ID"),
                ToolParameter(name="type", type=ToolParameterType.string, description="Record type: A, AAAA, CNAME, TXT, MX"),
                ToolParameter(name="name", type=ToolParameterType.string, description="Record name"),
                ToolParameter(name="content", type=ToolParameterType.string, description="Record value"),
                ToolParameter(name="proxied", type=ToolParameterType.boolean, description="Enable Cloudflare proxy", required=False, default=True),
            ]),
            ToolSchema(id="cloudflare.get_analytics", name="Get analytics", description="Get traffic analytics for a zone.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="zone_id", type=ToolParameterType.string, description="Zone ID"),
                ToolParameter(name="hours", type=ToolParameterType.integer, description="Lookback hours", required=False, default=24),
            ]),
        ],
    },
    "vercel": {
        "name": "Vercel",
        "description": "Deployment platform — list projects, deployments, domains, and environment variables.",
        "category": ConnectorCategory.cloud,
        "auth": BearerAuthConfig(credential_label="Vercel Access Token"),
        "tags": ["vercel", "deployment", "hosting", "cloud"],
        "tools": [
            ToolSchema(id="vercel.list_projects", name="List projects", description="List all Vercel projects.", action_class=ToolActionClass.read, parameters=[]),
            ToolSchema(id="vercel.list_deployments", name="List deployments", description="List recent deployments for a project.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="project_id", type=ToolParameterType.string, description="Project ID or name"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=10),
            ]),
            ToolSchema(id="vercel.get_deployment", name="Get deployment", description="Get details of a specific deployment.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="deployment_id", type=ToolParameterType.string, description="Deployment ID or URL")]),
            ToolSchema(id="vercel.list_domains", name="List domains", description="List custom domains for a project.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="project_id", type=ToolParameterType.string, description="Project ID")]),
        ],
    },
    "twitter": {
        "name": "X (Twitter)",
        "description": "Post tweets, search conversations, and monitor mentions via the X/Twitter API.",
        "category": ConnectorCategory.social,
        "auth": BearerAuthConfig(credential_label="X/Twitter Bearer Token"),
        "tags": ["twitter", "x", "social-media", "posts"],
        "tools": [
            ToolSchema(id="twitter.post_tweet", name="Post tweet", description="Post a new tweet.", action_class=ToolActionClass.execute, parameters=[ToolParameter(name="text", type=ToolParameterType.string, description="Tweet text (max 280 chars)")]),
            ToolSchema(id="twitter.search_tweets", name="Search tweets", description="Search recent tweets matching a query.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
            ToolSchema(id="twitter.get_mentions", name="Get mentions", description="Get recent mentions of the authenticated user.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20)]),
            ToolSchema(id="twitter.get_user_tweets", name="Get user tweets", description="Get recent tweets from a specific user.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="username", type=ToolParameterType.string, description="Twitter username (without @)"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=20),
            ]),
        ],
    },
    "linkedin": {
        "name": "LinkedIn",
        "description": "Professional networking — post content, search profiles, and manage company pages.",
        "category": ConnectorCategory.social,
        "auth": OAuth2AuthConfig(
            authorization_url="https://www.linkedin.com/oauth/v2/authorization",
            token_url="https://www.linkedin.com/oauth/v2/accessToken",
            scopes=["r_liteprofile", "w_member_social"],
        ),
        "tags": ["linkedin", "social-media", "professional", "networking"],
        "tools": [
            ToolSchema(id="linkedin.create_post", name="Create post", description="Publish a post on LinkedIn.", action_class=ToolActionClass.execute, parameters=[ToolParameter(name="text", type=ToolParameterType.string, description="Post content")]),
            ToolSchema(id="linkedin.get_profile", name="Get profile", description="Get the authenticated user's LinkedIn profile.", action_class=ToolActionClass.read, parameters=[]),
            ToolSchema(id="linkedin.search_people", name="Search people", description="Search LinkedIn profiles by keywords.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="keywords", type=ToolParameterType.string, description="Search keywords"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=10),
            ]),
            ToolSchema(id="linkedin.get_company", name="Get company", description="Get a company page's details.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="company_id", type=ToolParameterType.string, description="LinkedIn company ID")]),
        ],
    },
    "youtube": {
        "name": "YouTube",
        "description": "YouTube Data API — channel analytics, video search, playlists, and comment management.",
        "category": ConnectorCategory.social,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            scopes=["https://www.googleapis.com/auth/youtube.readonly"],
        ),
        "tags": ["youtube", "google", "video", "analytics"],
        "suite_id": "google", "suite_label": "Google", "service_order": 60,
        "tools": [
            ToolSchema(id="youtube.search_videos", name="Search videos", description="Search YouTube videos by query.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=10),
            ]),
            ToolSchema(id="youtube.get_channel_stats", name="Channel stats", description="Get subscriber count, video count, and view stats for a channel.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="channel_id", type=ToolParameterType.string, description="YouTube channel ID")]),
            ToolSchema(id="youtube.get_video_details", name="Video details", description="Get details, stats, and comments for a video.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="video_id", type=ToolParameterType.string, description="YouTube video ID")]),
            ToolSchema(id="youtube.list_playlists", name="List playlists", description="List playlists for a channel.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="channel_id", type=ToolParameterType.string, description="Channel ID")]),
        ],
    },
    "spotify": {
        "name": "Spotify",
        "description": "Spotify Web API — search tracks, get playlists, artist data, and playback control.",
        "category": ConnectorCategory.other,
        "auth": OAuth2AuthConfig(
            authorization_url="https://accounts.spotify.com/authorize",
            token_url="https://accounts.spotify.com/api/token",
            scopes=["user-read-playback-state", "playlist-read-private"],
        ),
        "tags": ["spotify", "music", "media", "entertainment"],
        "tools": [
            ToolSchema(id="spotify.search", name="Search", description="Search Spotify for tracks, artists, albums, or playlists.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="query", type=ToolParameterType.string, description="Search query"),
                ToolParameter(name="type", type=ToolParameterType.string, description="Type: track, artist, album, playlist", required=False, default="track"),
                ToolParameter(name="limit", type=ToolParameterType.integer, description="Max results", required=False, default=10),
            ]),
            ToolSchema(id="spotify.get_playlist", name="Get playlist", description="Get tracks in a Spotify playlist.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="playlist_id", type=ToolParameterType.string, description="Playlist ID")]),
            ToolSchema(id="spotify.get_artist", name="Get artist", description="Get artist details including top tracks and related artists.", action_class=ToolActionClass.read, parameters=[ToolParameter(name="artist_id", type=ToolParameterType.string, description="Artist ID")]),
        ],
    },
    "openai": {
        "name": "OpenAI",
        "description": "Call OpenAI models (GPT, DALL-E, Whisper) as tools within Maia agent workflows.",
        "category": ConnectorCategory.developer_tools,
        "auth": ApiKeyAuthConfig(param_name="Authorization", credential_label="OpenAI API Key"),
        "tags": ["openai", "ai", "llm", "gpt"],
        "tools": [
            ToolSchema(id="openai.chat", name="Chat completion", description="Generate a response from an OpenAI chat model.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="model", type=ToolParameterType.string, description="Model ID (gpt-4o, gpt-4o-mini)", required=False, default="gpt-4o-mini"),
                ToolParameter(name="messages", type=ToolParameterType.array, description="Chat messages array"),
                ToolParameter(name="max_tokens", type=ToolParameterType.integer, description="Max tokens", required=False, default=1000),
            ]),
            ToolSchema(id="openai.image", name="Generate image", description="Generate an image using DALL-E.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="prompt", type=ToolParameterType.string, description="Image description"),
                ToolParameter(name="size", type=ToolParameterType.string, description="Size: 1024x1024, 512x512", required=False, default="1024x1024"),
            ]),
            ToolSchema(id="openai.embeddings", name="Create embeddings", description="Generate text embeddings for semantic search.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="input", type=ToolParameterType.string, description="Text to embed"),
                ToolParameter(name="model", type=ToolParameterType.string, description="Embedding model", required=False, default="text-embedding-3-small"),
            ]),
        ],
    },
    "pinecone": {
        "name": "Pinecone",
        "description": "Vector database — upsert, query, and manage embeddings for semantic search and RAG.",
        "category": ConnectorCategory.database,
        "auth": ApiKeyAuthConfig(param_name="Api-Key", credential_label="Pinecone API Key"),
        "tags": ["pinecone", "vector-db", "embeddings", "rag", "ai"],
        "tools": [
            ToolSchema(id="pinecone.query", name="Query vectors", description="Query a Pinecone index for similar vectors.", action_class=ToolActionClass.read, parameters=[
                ToolParameter(name="index_name", type=ToolParameterType.string, description="Index name"),
                ToolParameter(name="vector", type=ToolParameterType.array, description="Query vector (float array)"),
                ToolParameter(name="top_k", type=ToolParameterType.integer, description="Number of results", required=False, default=10),
                ToolParameter(name="namespace", type=ToolParameterType.string, description="Namespace filter", required=False),
            ]),
            ToolSchema(id="pinecone.upsert", name="Upsert vectors", description="Upsert vectors into a Pinecone index.", action_class=ToolActionClass.execute, parameters=[
                ToolParameter(name="index_name", type=ToolParameterType.string, description="Index name"),
                ToolParameter(name="vectors", type=ToolParameterType.array, description="Array of {id, values, metadata} objects"),
                ToolParameter(name="namespace", type=ToolParameterType.string, description="Namespace", required=False),
            ]),
            ToolSchema(id="pinecone.list_indexes", name="List indexes", description="List all Pinecone indexes.", action_class=ToolActionClass.read, parameters=[]),
        ],
    },
}
