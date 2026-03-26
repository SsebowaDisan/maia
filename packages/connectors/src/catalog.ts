/**
 * Connector catalog — definitions for 50+ connectors.
 * Each entry describes what the connector does, what auth it needs,
 * and what tools it provides. The actual API calls are in implementations.
 */

import type { ConnectorDefinition, AuthKind } from "./types";
import { IMPLEMENTATIONS } from "./implementations";

interface CatalogEntry {
  name: string;
  description: string;
  authKind: AuthKind;
  category: string;
  iconEmoji: string;
  requiredCredentials: string[];
  tools: { id: string; name: string; description: string }[];
}

const CATALOG: Record<string, CatalogEntry> = {
  // ── Communication ────────────────────────────────────────────
  gmail: { name: "Gmail", description: "Send, read, and search emails", authKind: "oauth2", category: "communication", iconEmoji: "\u{2709}", requiredCredentials: ["client_id", "client_secret", "refresh_token"], tools: [{ id: "send_email", name: "Send Email", description: "Send an email with subject, body, and attachments" }, { id: "search_email", name: "Search Email", description: "Search emails by query" }, { id: "read_email", name: "Read Email", description: "Read a specific email by ID" }, { id: "list_labels", name: "List Labels", description: "List all Gmail labels" }] },
  slack: { name: "Slack", description: "Send messages, manage channels, read threads", authKind: "oauth2", category: "communication", iconEmoji: "\u{1F4AC}", requiredCredentials: ["bot_token"], tools: [{ id: "send_message", name: "Send Message", description: "Post a message to a channel" }, { id: "list_channels", name: "List Channels", description: "List available channels" }, { id: "read_thread", name: "Read Thread", description: "Read messages in a thread" }, { id: "search_messages", name: "Search Messages", description: "Search across messages" }] },
  microsoft_teams: { name: "Microsoft Teams", description: "Send messages and manage Teams channels", authKind: "oauth2", category: "communication", iconEmoji: "\u{1F4E2}", requiredCredentials: ["client_id", "client_secret", "tenant_id"], tools: [{ id: "send_message", name: "Send Message", description: "Post to a Teams channel" }, { id: "list_teams", name: "List Teams", description: "List available teams" }] },
  discord: { name: "Discord", description: "Send messages and manage Discord servers", authKind: "token", category: "communication", iconEmoji: "\u{1F3AE}", requiredCredentials: ["bot_token"], tools: [{ id: "send_message", name: "Send Message", description: "Post to a channel" }, { id: "list_channels", name: "List Channels", description: "List server channels" }] },
  twilio: { name: "Twilio", description: "Send SMS and make voice calls", authKind: "api_key", category: "communication", iconEmoji: "\u{1F4F1}", requiredCredentials: ["account_sid", "auth_token"], tools: [{ id: "send_sms", name: "Send SMS", description: "Send a text message" }, { id: "make_call", name: "Make Call", description: "Initiate a voice call" }] },

  // ── Project Management ───────────────────────────────────────
  jira: { name: "Jira", description: "Create and manage issues, sprints, and boards", authKind: "api_key", category: "project_management", iconEmoji: "\u{1F4CB}", requiredCredentials: ["domain", "email", "api_token"], tools: [{ id: "create_issue", name: "Create Issue", description: "Create a Jira issue" }, { id: "search_issues", name: "Search Issues", description: "Search with JQL" }, { id: "update_issue", name: "Update Issue", description: "Update an existing issue" }, { id: "list_projects", name: "List Projects", description: "List all projects" }] },
  linear: { name: "Linear", description: "Create and manage issues and projects", authKind: "api_key", category: "project_management", iconEmoji: "\u{1F4D0}", requiredCredentials: ["api_key"], tools: [{ id: "create_issue", name: "Create Issue", description: "Create a Linear issue" }, { id: "search_issues", name: "Search Issues", description: "Search issues" }, { id: "list_projects", name: "List Projects", description: "List projects" }] },
  asana: { name: "Asana", description: "Create tasks and manage projects", authKind: "token", category: "project_management", iconEmoji: "\u{2705}", requiredCredentials: ["access_token"], tools: [{ id: "create_task", name: "Create Task", description: "Create an Asana task" }, { id: "list_tasks", name: "List Tasks", description: "List tasks in a project" }] },
  trello: { name: "Trello", description: "Manage boards, lists, and cards", authKind: "api_key", category: "project_management", iconEmoji: "\u{1F5C2}", requiredCredentials: ["api_key", "token"], tools: [{ id: "create_card", name: "Create Card", description: "Create a Trello card" }, { id: "list_boards", name: "List Boards", description: "List all boards" }] },
  monday: { name: "Monday.com", description: "Manage boards and items", authKind: "api_key", category: "project_management", iconEmoji: "\u{1F4C5}", requiredCredentials: ["api_token"], tools: [{ id: "create_item", name: "Create Item", description: "Create a board item" }, { id: "list_boards", name: "List Boards", description: "List all boards" }] },

  // ── Developer Tools ──────────────────────────────────────────
  github: { name: "GitHub", description: "Manage repos, issues, PRs, and actions", authKind: "token", category: "developer", iconEmoji: "\u{1F4BB}", requiredCredentials: ["token"], tools: [{ id: "create_issue", name: "Create Issue", description: "Create a GitHub issue" }, { id: "create_pr", name: "Create PR", description: "Create a pull request" }, { id: "list_repos", name: "List Repos", description: "List repositories" }, { id: "search_code", name: "Search Code", description: "Search code across repos" }] },
  confluence: { name: "Confluence", description: "Create and search documentation pages", authKind: "api_key", category: "developer", iconEmoji: "\u{1F4DA}", requiredCredentials: ["domain", "email", "api_token"], tools: [{ id: "create_page", name: "Create Page", description: "Create a Confluence page" }, { id: "search_pages", name: "Search Pages", description: "Search documentation" }] },

  // ── CRM & Sales ──────────────────────────────────────────────
  salesforce: { name: "Salesforce", description: "Manage leads, contacts, and opportunities", authKind: "oauth2", category: "crm", iconEmoji: "\u{2601}", requiredCredentials: ["client_id", "client_secret", "refresh_token"], tools: [{ id: "create_lead", name: "Create Lead", description: "Create a new lead" }, { id: "search_contacts", name: "Search Contacts", description: "Search contacts" }, { id: "create_opportunity", name: "Create Opportunity", description: "Create an opportunity" }] },
  hubspot: { name: "HubSpot", description: "Manage contacts, deals, and marketing", authKind: "api_key", category: "crm", iconEmoji: "\u{1F4C8}", requiredCredentials: ["api_key"], tools: [{ id: "create_contact", name: "Create Contact", description: "Create a HubSpot contact" }, { id: "search_contacts", name: "Search Contacts", description: "Search contacts" }, { id: "create_deal", name: "Create Deal", description: "Create a deal" }] },

  // ── Data & Analytics ─────────────────────────────────────────
  google_analytics: { name: "Google Analytics", description: "Fetch website analytics and reports", authKind: "oauth2", category: "analytics", iconEmoji: "\u{1F4CA}", requiredCredentials: ["client_id", "client_secret", "refresh_token"], tools: [{ id: "get_report", name: "Get Report", description: "Fetch an analytics report" }, { id: "get_realtime", name: "Get Realtime", description: "Get realtime visitor data" }] },
  google_ads: { name: "Google Ads", description: "Manage ad campaigns and reporting", authKind: "oauth2", category: "analytics", iconEmoji: "\u{1F4B0}", requiredCredentials: ["client_id", "client_secret", "developer_token"], tools: [{ id: "list_campaigns", name: "List Campaigns", description: "List ad campaigns" }, { id: "get_report", name: "Get Report", description: "Fetch performance report" }] },
  bigquery: { name: "BigQuery", description: "Run SQL queries on large datasets", authKind: "oauth2", category: "database", iconEmoji: "\u{1F5C4}", requiredCredentials: ["service_account_json"], tools: [{ id: "run_query", name: "Run Query", description: "Execute a SQL query" }, { id: "list_datasets", name: "List Datasets", description: "List available datasets" }] },
  postgresql: { name: "PostgreSQL", description: "Query and manage PostgreSQL databases", authKind: "basic", category: "database", iconEmoji: "\u{1F418}", requiredCredentials: ["host", "port", "database", "user", "password"], tools: [{ id: "run_query", name: "Run Query", description: "Execute a SQL query" }, { id: "list_tables", name: "List Tables", description: "List database tables" }] },
  supabase: { name: "Supabase", description: "Query and manage Supabase projects", authKind: "api_key", category: "database", iconEmoji: "\u{26A1}", requiredCredentials: ["url", "anon_key"], tools: [{ id: "query", name: "Query", description: "Query a table" }, { id: "insert", name: "Insert", description: "Insert a row" }] },

  // ── Productivity ─────────────────────────────────────────────
  notion: { name: "Notion", description: "Create and search pages and databases", authKind: "token", category: "productivity", iconEmoji: "\u{1F4DD}", requiredCredentials: ["api_key"], tools: [{ id: "create_page", name: "Create Page", description: "Create a Notion page" }, { id: "search", name: "Search", description: "Search pages and databases" }, { id: "query_database", name: "Query Database", description: "Query a Notion database" }] },
  airtable: { name: "Airtable", description: "Manage spreadsheet-like databases", authKind: "api_key", category: "productivity", iconEmoji: "\u{1F4CA}", requiredCredentials: ["api_key"], tools: [{ id: "list_records", name: "List Records", description: "List records in a table" }, { id: "create_record", name: "Create Record", description: "Create a new record" }] },
  google_calendar: { name: "Google Calendar", description: "Create and manage calendar events", authKind: "oauth2", category: "productivity", iconEmoji: "\u{1F4C6}", requiredCredentials: ["client_id", "client_secret", "refresh_token"], tools: [{ id: "create_event", name: "Create Event", description: "Create a calendar event" }, { id: "list_events", name: "List Events", description: "List upcoming events" }] },
  calendly: { name: "Calendly", description: "Manage scheduling and availability", authKind: "token", category: "productivity", iconEmoji: "\u{1F4C5}", requiredCredentials: ["access_token"], tools: [{ id: "list_events", name: "List Events", description: "List scheduled events" }, { id: "get_availability", name: "Get Availability", description: "Check availability" }] },

  // ── Storage ──────────────────────────────────────────────────
  google_drive: { name: "Google Drive", description: "Upload, download, and search files", authKind: "oauth2", category: "storage", iconEmoji: "\u{1F4C1}", requiredCredentials: ["client_id", "client_secret", "refresh_token"], tools: [{ id: "search_files", name: "Search Files", description: "Search for files" }, { id: "upload_file", name: "Upload File", description: "Upload a file" }, { id: "download_file", name: "Download File", description: "Download a file" }] },
  dropbox: { name: "Dropbox", description: "Manage files and folders", authKind: "oauth2", category: "storage", iconEmoji: "\u{1F4E6}", requiredCredentials: ["access_token"], tools: [{ id: "list_files", name: "List Files", description: "List files in a folder" }, { id: "upload_file", name: "Upload File", description: "Upload a file" }] },
  box: { name: "Box", description: "Enterprise file management", authKind: "oauth2", category: "storage", iconEmoji: "\u{1F4E5}", requiredCredentials: ["client_id", "client_secret"], tools: [{ id: "search_files", name: "Search Files", description: "Search for files" }, { id: "upload_file", name: "Upload File", description: "Upload a file" }] },

  // ── Commerce ─────────────────────────────────────────────────
  stripe: { name: "Stripe", description: "Manage payments, customers, and invoices", authKind: "api_key", category: "commerce", iconEmoji: "\u{1F4B3}", requiredCredentials: ["secret_key"], tools: [{ id: "create_invoice", name: "Create Invoice", description: "Create an invoice" }, { id: "list_customers", name: "List Customers", description: "List customers" }, { id: "get_balance", name: "Get Balance", description: "Get account balance" }] },
  shopify: { name: "Shopify", description: "Manage products, orders, and customers", authKind: "api_key", category: "commerce", iconEmoji: "\u{1F6D2}", requiredCredentials: ["shop_domain", "access_token"], tools: [{ id: "list_products", name: "List Products", description: "List products" }, { id: "list_orders", name: "List Orders", description: "List orders" }, { id: "create_product", name: "Create Product", description: "Create a product" }] },
  quickbooks: { name: "QuickBooks", description: "Manage invoices and accounting", authKind: "oauth2", category: "commerce", iconEmoji: "\u{1F4B5}", requiredCredentials: ["client_id", "client_secret"], tools: [{ id: "create_invoice", name: "Create Invoice", description: "Create an invoice" }, { id: "list_customers", name: "List Customers", description: "List customers" }] },
  xero: { name: "Xero", description: "Cloud accounting and invoicing", authKind: "oauth2", category: "commerce", iconEmoji: "\u{1F4B6}", requiredCredentials: ["client_id", "client_secret"], tools: [{ id: "create_invoice", name: "Create Invoice", description: "Create an invoice" }, { id: "list_contacts", name: "List Contacts", description: "List contacts" }] },

  // ── Marketing ────────────────────────────────────────────────
  mailchimp: { name: "Mailchimp", description: "Manage email campaigns and audiences", authKind: "api_key", category: "marketing", iconEmoji: "\u{1F4E7}", requiredCredentials: ["api_key"], tools: [{ id: "send_campaign", name: "Send Campaign", description: "Send an email campaign" }, { id: "list_audiences", name: "List Audiences", description: "List audiences" }] },

  // ── Social ───────────────────────────────────────────────────
  twitter: { name: "Twitter/X", description: "Post tweets and search", authKind: "oauth2", category: "social", iconEmoji: "\u{1F426}", requiredCredentials: ["api_key", "api_secret", "access_token", "access_secret"], tools: [{ id: "post_tweet", name: "Post Tweet", description: "Post a tweet" }, { id: "search_tweets", name: "Search Tweets", description: "Search tweets" }] },
  linkedin: { name: "LinkedIn", description: "Post updates and manage company pages", authKind: "oauth2", category: "social", iconEmoji: "\u{1F4BC}", requiredCredentials: ["access_token"], tools: [{ id: "create_post", name: "Create Post", description: "Post an update" }, { id: "get_profile", name: "Get Profile", description: "Get profile info" }] },

  // ── Search ───────────────────────────────────────────────────
  brave_search: { name: "Brave Search", description: "Web search via Brave API", authKind: "api_key", category: "search", iconEmoji: "\u{1F50D}", requiredCredentials: ["api_key"], tools: [{ id: "web_search", name: "Web Search", description: "Search the web" }, { id: "news_search", name: "News Search", description: "Search news" }] },

  // ── Support ──────────────────────────────────────────────────
  zendesk: { name: "Zendesk", description: "Manage support tickets", authKind: "api_key", category: "support", iconEmoji: "\u{1F3AB}", requiredCredentials: ["subdomain", "email", "api_token"], tools: [{ id: "create_ticket", name: "Create Ticket", description: "Create a support ticket" }, { id: "search_tickets", name: "Search Tickets", description: "Search tickets" }] },
  intercom: { name: "Intercom", description: "Manage conversations and contacts", authKind: "token", category: "support", iconEmoji: "\u{1F4AC}", requiredCredentials: ["access_token"], tools: [{ id: "send_message", name: "Send Message", description: "Send a message to a user" }, { id: "list_conversations", name: "List Conversations", description: "List conversations" }] },

  // ── Design ───────────────────────────────────────────────────
  figma: { name: "Figma", description: "Read design files and components", authKind: "token", category: "design", iconEmoji: "\u{1F3A8}", requiredCredentials: ["access_token"], tools: [{ id: "get_file", name: "Get File", description: "Get a Figma file" }, { id: "list_components", name: "List Components", description: "List components" }] },

  // ── Automation ────────────────────────────────────────────────
  zapier_webhooks: { name: "Zapier Webhooks", description: "Trigger Zapier workflows via webhooks", authKind: "none", category: "automation", iconEmoji: "\u{26A1}", requiredCredentials: ["webhook_url"], tools: [{ id: "trigger", name: "Trigger Webhook", description: "Send data to a Zapier webhook" }] },
  make: { name: "Make (Integromat)", description: "Trigger Make scenarios", authKind: "none", category: "automation", iconEmoji: "\u{1F504}", requiredCredentials: ["webhook_url"], tools: [{ id: "trigger", name: "Trigger Scenario", description: "Trigger a Make scenario" }] },

  // ── Cloud & Infra ────────────────────────────────────────────
  aws: { name: "AWS", description: "Manage S3, Lambda, and other AWS services", authKind: "api_key", category: "cloud", iconEmoji: "\u{2601}", requiredCredentials: ["access_key_id", "secret_access_key", "region"], tools: [{ id: "s3_list", name: "List S3 Buckets", description: "List S3 buckets" }, { id: "lambda_invoke", name: "Invoke Lambda", description: "Invoke a Lambda function" }] },
  vercel: { name: "Vercel", description: "Manage deployments and projects", authKind: "token", category: "cloud", iconEmoji: "\u{25B2}", requiredCredentials: ["token"], tools: [{ id: "list_deployments", name: "List Deployments", description: "List deployments" }, { id: "trigger_deploy", name: "Trigger Deploy", description: "Trigger a deployment" }] },
  cloudflare: { name: "Cloudflare", description: "Manage DNS, workers, and pages", authKind: "api_key", category: "cloud", iconEmoji: "\u{1F6E1}", requiredCredentials: ["api_token"], tools: [{ id: "list_zones", name: "List Zones", description: "List DNS zones" }, { id: "purge_cache", name: "Purge Cache", description: "Purge cache" }] },

  // ── AI/ML ────────────────────────────────────────────────────
  openai: { name: "OpenAI", description: "Call OpenAI models (GPT, DALL-E, Whisper)", authKind: "api_key", category: "ai", iconEmoji: "\u{1F916}", requiredCredentials: ["api_key"], tools: [{ id: "chat_completion", name: "Chat Completion", description: "Generate chat completion" }, { id: "create_image", name: "Create Image", description: "Generate an image with DALL-E" }] },
  pinecone: { name: "Pinecone", description: "Vector database for semantic search", authKind: "api_key", category: "ai", iconEmoji: "\u{1F333}", requiredCredentials: ["api_key", "environment"], tools: [{ id: "upsert", name: "Upsert Vectors", description: "Upsert vectors" }, { id: "query", name: "Query", description: "Query similar vectors" }] },

  // ── Enterprise ───────────────────────────────────────────────
  sap: { name: "SAP", description: "Connect to SAP ERP systems", authKind: "basic", category: "enterprise", iconEmoji: "\u{1F3ED}", requiredCredentials: ["base_url", "username", "password"], tools: [{ id: "read_entity", name: "Read Entity", description: "Read an OData entity" }, { id: "create_entity", name: "Create Entity", description: "Create an OData entity" }] },
  docusign: { name: "DocuSign", description: "Send and manage document signatures", authKind: "oauth2", category: "enterprise", iconEmoji: "\u{270D}", requiredCredentials: ["client_id", "client_secret"], tools: [{ id: "send_envelope", name: "Send Envelope", description: "Send a document for signature" }, { id: "list_envelopes", name: "List Envelopes", description: "List envelopes" }] },

  // ── Media ────────────────────────────────────────────────────
  youtube: { name: "YouTube", description: "Search videos and manage channels", authKind: "api_key", category: "media", iconEmoji: "\u{1F3AC}", requiredCredentials: ["api_key"], tools: [{ id: "search_videos", name: "Search Videos", description: "Search YouTube videos" }, { id: "get_video", name: "Get Video", description: "Get video details" }] },
  spotify: { name: "Spotify", description: "Search music and manage playlists", authKind: "oauth2", category: "media", iconEmoji: "\u{1F3B5}", requiredCredentials: ["client_id", "client_secret"], tools: [{ id: "search_tracks", name: "Search Tracks", description: "Search for music" }, { id: "get_playlist", name: "Get Playlist", description: "Get playlist details" }] },

  // ── Website ──────────────────────────────────────────────────
  webflow: { name: "Webflow", description: "Manage CMS collections and sites", authKind: "token", category: "website", iconEmoji: "\u{1F310}", requiredCredentials: ["access_token"], tools: [{ id: "list_sites", name: "List Sites", description: "List Webflow sites" }, { id: "list_items", name: "List Items", description: "List CMS items" }] },
};

/** Get all connector definitions with real execute functions. */
export function getAllConnectors(): ConnectorDefinition[] {
  return Object.entries(CATALOG).map(([id, entry]) => {
    const impls = IMPLEMENTATIONS[id] || {};
    return {
      id,
      ...entry,
      tools: entry.tools.map((t) => ({
        ...t,
        inputSchema: {},
        execute: impls[t.id] || (async () => ({ success: false, error: "Not implemented", summary: `${id}.${t.id} not yet wired` })),
      })),
    };
  });
}

/** Get a connector definition by ID. */
export function getConnector(id: string): ConnectorDefinition | undefined {
  return getAllConnectors().find((c) => c.id === id);
}

/** Get connectors by category. */
export function getConnectorsByCategory(category: string): ConnectorDefinition[] {
  return getAllConnectors().filter((c) => c.category === category);
}

/** Get all category names. */
export function getCategories(): string[] {
  return [...new Set(Object.values(CATALOG).map((c) => c.category))];
}

export { CATALOG };