export type ConnectorField = {
  key: string;
  label: string;
  placeholder: string;
  sensitive?: boolean;
};

export type ConnectorDefinition = {
  id: string;
  label: string;
  description: string;
  fields: ConnectorField[];
};

export const MANUAL_CONNECTOR_DEFINITIONS: ConnectorDefinition[] = [
  {
    id: "brave_search",
    label: "Brave Search",
    description: "Search the web with Brave Search for fresh, citation-friendly results.",
    fields: [
      {
        key: "BRAVE_API_KEY",
        label: "API key",
        placeholder: "Brave Search API key",
        sensitive: true,
      },
    ],
  },
  {
    id: "reddit",
    label: "Reddit",
    description:
      "Search Reddit posts and comments for community sentiment and real-world discussions.",
    fields: [
      {
        key: "REDDIT_CLIENT_ID",
        label: "Client ID",
        placeholder: "Reddit app client ID",
      },
      {
        key: "REDDIT_CLIENT_SECRET",
        label: "Client Secret",
        placeholder: "Reddit app client secret",
        sensitive: true,
      },
    ],
  },
  {
    id: "newsapi",
    label: "NewsAPI",
    description:
      "Search and fetch current news articles from thousands of sources worldwide.",
    fields: [
      {
        key: "NEWSAPI_API_KEY",
        label: "API key",
        placeholder: "NewsAPI key",
        sensitive: true,
      },
    ],
  },
  {
    id: "sec_edgar",
    label: "SEC EDGAR",
    description:
      "Access public SEC filings (10-K, 10-Q, 8-K). No credentials are required.",
    fields: [],
  },
  {
    id: "google_maps",
    label: "Google Maps",
    description: "Search places and local business data via Google Maps APIs.",
    fields: [
      {
        key: "GOOGLE_MAPS_API_KEY",
        label: "API key",
        placeholder: "Google Maps API key",
        sensitive: true,
      },
    ],
  },
  {
    id: "google_workspace",
    label: "Google Workspace",
    description:
      "Unified Google OAuth connector for Gmail, Calendar, Drive, Docs, and Sheets.",
    fields: [],
  },
  {
    id: "gmail",
    label: "Gmail",
    description:
      "Email access is granted through the Google Workspace OAuth connector.",
    fields: [],
  },
  {
    id: "gmail_playwright",
    label: "Gmail (Playwright)",
    description:
      "Browser-assisted Gmail workflows use the same Google Workspace account connection.",
    fields: [],
  },
  {
    id: "google_api_hub",
    label: "Google API Hub",
    description:
      "Google API Hub access is managed through your Google Workspace OAuth setup.",
    fields: [],
  },
  {
    id: "playwright_browser",
    label: "Web Browser (Playwright)",
    description:
      "System browser automation for navigation, extraction, and web interaction.",
    fields: [],
  },
  {
    id: "playwright_contact_form",
    label: "Web Contact Form (Playwright)",
    description:
      "Automates website contact form submissions through browser automation.",
    fields: [],
  },
  {
    id: "arxiv",
    label: "arXiv",
    description:
      "Search and read open research papers from arXiv. No credentials are required.",
    fields: [],
  },
  {
    id: "google_calendar",
    label: "Google Calendar",
    description:
      "Calendar access is granted through Google OAuth scopes in the Google suite setup.",
    fields: [],
  },
  {
    id: "google_analytics",
    label: "Google Analytics",
    description:
      "Analytics access is granted through Google OAuth scopes in the Google suite setup.",
    fields: [],
  },
  {
    id: "slack",
    label: "Slack",
    description: "Post company updates and report digests to channels.",
    fields: [
      {
        key: "SLACK_BOT_TOKEN",
        label: "Bot token",
        placeholder: "xoxb-...",
        sensitive: true,
      },
    ],
  },
  {
    id: "google_ads",
    label: "Google Ads",
    description: "Read campaign metrics for KPI analysis and optimization.",
    fields: [
      {
        key: "GOOGLE_ADS_DEVELOPER_TOKEN",
        label: "Developer token",
        placeholder: "Google Ads developer token",
        sensitive: true,
      },
      {
        key: "GOOGLE_ADS_CUSTOMER_ID",
        label: "Customer ID",
        placeholder: "1234567890",
      },
      {
        key: "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
        label: "Login customer ID",
        placeholder: "Optional manager account ID",
      },
    ],
  },
  {
    id: "bing_search",
    label: "Bing Web Search (Legacy)",
    description: "Optional fallback search provider if Brave is unavailable.",
    fields: [
      {
        key: "AZURE_BING_API_KEY",
        label: "Azure API key",
        placeholder: "Bing Web Search key",
        sensitive: true,
      },
      {
        key: "BING_SEARCH_ENDPOINT",
        label: "Endpoint",
        placeholder: "https://api.bing.microsoft.com/v7.0/search",
      },
    ],
  },
  {
    id: "email_validation",
    label: "Email Validation",
    description: "Validate outreach emails before send to reduce bounces.",
    fields: [
      {
        key: "EMAIL_VALIDATION_PROVIDER",
        label: "Provider",
        placeholder: "abstractapi or zerobounce",
      },
      {
        key: "EMAIL_VALIDATION_API_KEY",
        label: "API key",
        placeholder: "Email verification provider key",
        sensitive: true,
      },
    ],
  },
  {
    id: "m365",
    label: "Microsoft 365",
    description: "Use OneDrive and Excel via Microsoft Graph.",
    fields: [
      {
        key: "M365_ACCESS_TOKEN",
        label: "Access token",
        placeholder: "Bearer token",
        sensitive: true,
      },
    ],
  },
  {
    id: "invoice",
    label: "Invoice Providers",
    description: "Send invoices through QuickBooks or Xero.",
    fields: [
      {
        key: "QUICKBOOKS_ACCESS_TOKEN",
        label: "QuickBooks access token",
        placeholder: "Bearer token",
        sensitive: true,
      },
      {
        key: "QUICKBOOKS_REALM_ID",
        label: "QuickBooks realm ID",
        placeholder: "Company realm ID",
      },
      {
        key: "XERO_ACCESS_TOKEN",
        label: "Xero access token",
        placeholder: "Bearer token",
        sensitive: true,
      },
      {
        key: "XERO_TENANT_ID",
        label: "Xero tenant ID",
        placeholder: "Tenant ID",
      },
    ],
  },
];
