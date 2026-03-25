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

PROFILES_EXT_FOUNDATION_CORE: dict[str, dict] = {
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
}
