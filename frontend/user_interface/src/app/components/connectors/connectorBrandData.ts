export type ConnectorBrandKey =
  | "google"
  | "google_cloud"
  | "gmail"
  | "google_calendar"
  | "google_drive"
  | "google_docs"
  | "google_sheets"
  | "google_analytics"
  | "google_ads"
  | "google_maps"
  | "microsoft"
  | "outlook"
  | "microsoft_calendar"
  | "onedrive"
  | "excel"
  | "word"
  | "teams"
  | "slack"
  | "notion"
  | "hubspot"
  | "salesforce"
  | "jira"
  | "airtable"
  | "zendesk"
  | "stripe"
  | "shopify"
  | "sap"
  | "asana"
  | "aws"
  | "bigquery"
  | "bing"
  | "box"
  | "brave"
  | "calendly"
  | "cloudflare"
  | "confluence"
  | "discord"
  | "docusign"
  | "dropbox"
  | "figma"
  | "github"
  | "intercom"
  | "linear"
  | "linkedin"
  | "mailchimp"
  | "make"
  | "monday"
  | "openai"
  | "pinecone"
  | "postgresql"
  | "quickbooks"
  | "spotify"
  | "supabase"
  | "trello"
  | "twilio"
  | "twitter"
  | "vercel"
  | "webflow"
  | "xero"
  | "youtube"
  | "zapier"
  | "playwright"
  | "browser"
  | "http"
  | "page_monitor"
  | "invoice"
  | "email_validation"
  | "sec_edgar"
  | "newsapi"
  | "reddit"
  | "arxiv"
  | "generic";

export type BrandStyle = {
  text: string;
  background: string;
  color: string;
  borderColor: string;
  localIconUrl?: string;
  iconUrl?: string;
};

// Official brand domains used for runtime favicon fallback resolution.
// This allows each connector to display an official favicon even when a
// direct icon URL is blocked, moved, or temporarily unavailable.
export const BRAND_OFFICIAL_DOMAIN_MAP: Partial<Record<ConnectorBrandKey, string>> = {
  google: "workspace.google.com",
  google_cloud: "cloud.google.com",
  gmail: "mail.google.com",
  google_calendar: "calendar.google.com",
  google_drive: "drive.google.com",
  google_docs: "docs.google.com",
  google_sheets: "sheets.google.com",
  google_analytics: "analytics.google.com",
  google_ads: "ads.google.com",
  google_maps: "maps.google.com",
  microsoft: "microsoft.com",
  outlook: "outlook.live.com",
  microsoft_calendar: "outlook.live.com",
  onedrive: "onedrive.live.com",
  excel: "microsoft365.com",
  word: "microsoft365.com",
  teams: "teams.microsoft.com",
  slack: "slack.com",
  notion: "notion.so",
  hubspot: "hubspot.com",
  salesforce: "salesforce.com",
  jira: "atlassian.com",
  airtable: "airtable.com",
  zendesk: "zendesk.com",
  stripe: "stripe.com",
  shopify: "shopify.com",
  sap: "sap.com",
  asana: "asana.com",
  aws: "aws.amazon.com",
  bigquery: "cloud.google.com",
  bing: "bing.com",
  box: "box.com",
  brave: "brave.com",
  calendly: "calendly.com",
  cloudflare: "cloudflare.com",
  confluence: "atlassian.com",
  discord: "discord.com",
  docusign: "docusign.com",
  dropbox: "dropbox.com",
  figma: "figma.com",
  github: "github.com",
  intercom: "intercom.com",
  linear: "linear.app",
  linkedin: "linkedin.com",
  mailchimp: "mailchimp.com",
  make: "make.com",
  monday: "monday.com",
  openai: "openai.com",
  pinecone: "pinecone.io",
  postgresql: "postgresql.org",
  quickbooks: "quickbooks.intuit.com",
  spotify: "spotify.com",
  supabase: "supabase.com",
  trello: "trello.com",
  twilio: "twilio.com",
  twitter: "x.com",
  vercel: "vercel.com",
  webflow: "webflow.com",
  xero: "xero.com",
  youtube: "youtube.com",
  zapier: "zapier.com",
  playwright: "playwright.dev",
  browser: "google.com",
  http: "httpbin.org",
  page_monitor: "web.dev",
  invoice: "quickbooks.intuit.com",
  email_validation: "zerobounce.net",
  sec_edgar: "sec.gov",
  newsapi: "newsapi.org",
  reddit: "reddit.com",
  arxiv: "arxiv.org",
};

// Google products: official product marks from gstatic.
// Third-party brands: official favicon/logo URLs from brand-owned domains.
const _GOOGLE_PRODUCT = "https://www.gstatic.com/images/branding/product/1x/";

export const BRAND_STYLE_MAP: Record<ConnectorBrandKey, BrandStyle> = {
  google: {
    text: "G", background: "#ffffff", color: "#4285f4", borderColor: "#e5e7eb",
    localIconUrl: "/icons/connectors/google-workspace.svg",
    iconUrl: "https://workspace.google.com/favicon.ico",
  },
  google_cloud: {
    text: "GC", background: "#ffffff", color: "#4285f4", borderColor: "#e5e7eb",
    iconUrl: `${_GOOGLE_PRODUCT}cloud_48dp.png`,
  },
  gmail: {
    text: "M", background: "#ffffff", color: "#ea4335", borderColor: "#e5e7eb",
    iconUrl: `${_GOOGLE_PRODUCT}gmail_48dp.png`,
  },
  google_calendar: {
    text: "31", background: "#ffffff", color: "#4285f4", borderColor: "#e5e7eb",
    localIconUrl: "/icons/connectors/google-calendar.svg",
    iconUrl: `${_GOOGLE_PRODUCT}calendar_48dp.png`,
  },
  google_drive: {
    text: "Dr", background: "#ffffff", color: "#4285f4", borderColor: "#e5e7eb",
    localIconUrl: "/icons/connectors/google-drive.svg",
    iconUrl: `${_GOOGLE_PRODUCT}drive_48dp.png`,
  },
  google_docs: {
    text: "Doc", background: "#ffffff", color: "#4285f4", borderColor: "#e5e7eb",
    localIconUrl: "/icons/connectors/google-docs.svg",
    iconUrl: `${_GOOGLE_PRODUCT}docs_48dp.png`,
  },
  google_sheets: {
    text: "Sh", background: "#ffffff", color: "#0f9d58", borderColor: "#e5e7eb",
    localIconUrl: "/icons/connectors/google-sheets.svg",
    iconUrl: `${_GOOGLE_PRODUCT}sheets_48dp.png`,
  },
  google_analytics: {
    text: "GA", background: "#ffffff", color: "#e37400", borderColor: "#e5e7eb",
    localIconUrl: "/icons/connectors/google-analytics.svg",
    iconUrl: `${_GOOGLE_PRODUCT}analytics_48dp.png`,
  },
  google_ads: {
    text: "Ads", background: "#ffffff", color: "#4285f4", borderColor: "#e5e7eb",
    localIconUrl: "/icons/connectors/google-ads.svg",
    iconUrl: `${_GOOGLE_PRODUCT}ads_48dp.png`,
  },
  google_maps: {
    text: "Map", background: "#ffffff", color: "#ea4335", borderColor: "#e5e7eb",
    localIconUrl: "/icons/connectors/google-maps.svg",
    iconUrl: `${_GOOGLE_PRODUCT}maps_48dp.png`,
  },
  microsoft: {
    text: "MS", background: "#ffffff", color: "#5E5E5E", borderColor: "#e5e7eb",
    iconUrl: "https://res.cdn.office.net/officehub/images/content/images/favicon_copilot-4370172aa6.ico",
  },
  outlook: {
    text: "O", background: "#ffffff", color: "#0078d4", borderColor: "#e5e7eb",
    iconUrl: "https://outlook.live.com/favicon.ico",
  },
  microsoft_calendar: {
    text: "Cal", background: "#ffffff", color: "#0078d4", borderColor: "#e5e7eb",
    iconUrl: "https://outlook.live.com/favicon.ico",
  },
  onedrive: {
    text: "1D", background: "#ffffff", color: "#0078d4", borderColor: "#e5e7eb",
    iconUrl: "https://www.onedrive.com/favicon.ico",
  },
  excel: {
    text: "X", background: "#ffffff", color: "#217346", borderColor: "#e5e7eb",
    iconUrl: "https://www.office.com/favicon.ico",
  },
  word: {
    text: "W", background: "#ffffff", color: "#2b579a", borderColor: "#e5e7eb",
    iconUrl: "https://www.office.com/favicon.ico",
  },
  teams: {
    text: "T", background: "#ffffff", color: "#6264a7", borderColor: "#e5e7eb",
    iconUrl: "https://teams.microsoft.com/favicon.ico",
  },
  slack: {
    text: "S", background: "#ffffff", color: "#4a154b", borderColor: "#e5e7eb",
    iconUrl: "https://slack.com/favicon.ico",
  },
  notion: {
    text: "N", background: "#ffffff", color: "#000000", borderColor: "#e5e7eb",
    iconUrl: "https://www.notion.so/images/favicon.ico",
  },
  hubspot: {
    text: "H", background: "#ffffff", color: "#ff7a59", borderColor: "#e5e7eb",
    iconUrl: "https://www.hubspot.com/favicon.ico",
  },
  salesforce: {
    text: "SF", background: "#ffffff", color: "#00a1e0", borderColor: "#e5e7eb",
    iconUrl: "https://www.salesforce.com/favicon.ico",
  },
  jira: {
    text: "J", background: "#ffffff", color: "#0052cc", borderColor: "#e5e7eb",
    iconUrl: "https://www.atlassian.com/favicon.ico",
  },
  airtable: {
    text: "AT", background: "#ffffff", color: "#18bfff", borderColor: "#e5e7eb",
    iconUrl: "https://airtable.com/favicon.ico",
  },
  zendesk: {
    text: "Z", background: "#ffffff", color: "#03363d", borderColor: "#e5e7eb",
    iconUrl: "https://www.zendesk.com/favicon.ico",
  },
  stripe: {
    text: "St", background: "#ffffff", color: "#635bff", borderColor: "#e5e7eb",
    iconUrl: "https://stripe.com/favicon.ico",
  },
  shopify: {
    text: "Sh", background: "#ffffff", color: "#7ab55c", borderColor: "#e5e7eb",
    iconUrl: "https://www.shopify.com/favicon.ico",
  },
  sap: {
    text: "SAP", background: "#ffffff", color: "#0faaff", borderColor: "#e5e7eb",
    iconUrl: "https://help.sap.com/favicon.ico",
  },
  asana: {
    text: "A", background: "#ffffff", color: "#f06a6a", borderColor: "#e5e7eb",
    iconUrl: "https://asana.com/favicon.ico",
  },
  aws: {
    text: "AWS", background: "#ffffff", color: "#ff9900", borderColor: "#e5e7eb",
    iconUrl: "https://aws.amazon.com/favicon.ico",
  },
  bigquery: {
    text: "BQ", background: "#ffffff", color: "#4285f4", borderColor: "#e5e7eb",
    iconUrl: `${_GOOGLE_PRODUCT}bigquery_48dp.png`,
  },
  bing: {
    text: "B", background: "#ffffff", color: "#008373", borderColor: "#e5e7eb",
    iconUrl: "https://www.bing.com/favicon.ico",
  },
  box: {
    text: "Box", background: "#ffffff", color: "#0061d5", borderColor: "#e5e7eb",
    iconUrl: "https://www.box.com/favicon.ico",
  },
  brave: {
    text: "Br", background: "#ffffff", color: "#fb542b", borderColor: "#e5e7eb",
    iconUrl: "https://brave.com/favicon.ico",
  },
  calendly: {
    text: "C", background: "#ffffff", color: "#006bff", borderColor: "#e5e7eb",
    iconUrl: "https://calendly.com/favicon.ico",
  },
  cloudflare: {
    text: "CF", background: "#ffffff", color: "#f38020", borderColor: "#e5e7eb",
    iconUrl: "https://www.cloudflare.com/favicon.ico",
  },
  confluence: {
    text: "C", background: "#ffffff", color: "#0052cc", borderColor: "#e5e7eb",
    iconUrl: "https://www.atlassian.com/favicon.ico",
  },
  discord: {
    text: "D", background: "#ffffff", color: "#5865f2", borderColor: "#e5e7eb",
    iconUrl: "https://cdn.prod.website-files.com/6257adef93867e50d84d30e2/62fddf0fde45a8baedcc7ee5_847541504914fd33810e70a0ea73177e%20(2)-1.png",
  },
  docusign: {
    text: "DS", background: "#ffffff", color: "#ffcc00", borderColor: "#e5e7eb",
    iconUrl: "https://www.docusign.com/favicon.ico",
  },
  dropbox: {
    text: "DB", background: "#ffffff", color: "#0061ff", borderColor: "#e5e7eb",
    iconUrl: "https://cfl.dropboxstatic.com/static/metaserver/static/images/favicon.ico",
  },
  figma: {
    text: "F", background: "#ffffff", color: "#a259ff", borderColor: "#e5e7eb",
    iconUrl: "https://static.figma.com/app/icon/2/favicon.ico",
  },
  github: {
    text: "GH", background: "#ffffff", color: "#111827", borderColor: "#e5e7eb",
    iconUrl: "https://github.com/favicon.ico",
  },
  intercom: {
    text: "I", background: "#ffffff", color: "#0ea5e9", borderColor: "#e5e7eb",
    iconUrl: "https://www.intercom.com/intercom-marketing-site/favicons/favicon.ico",
  },
  linear: {
    text: "L", background: "#ffffff", color: "#5e6ad2", borderColor: "#e5e7eb",
    iconUrl: "https://linear.app/favicon.ico",
  },
  linkedin: {
    text: "in", background: "#ffffff", color: "#0a66c2", borderColor: "#e5e7eb",
    iconUrl: "https://www.linkedin.com/favicon.ico",
  },
  mailchimp: {
    text: "MC", background: "#ffffff", color: "#f7b801", borderColor: "#e5e7eb",
    iconUrl: "https://mailchimp.com/favicon.ico",
  },
  make: {
    text: "Mk", background: "#ffffff", color: "#6c2bd9", borderColor: "#e5e7eb",
    iconUrl: "https://www.make.com/favicon.ico",
  },
  monday: {
    text: "M", background: "#ffffff", color: "#6c3ed0", borderColor: "#e5e7eb",
    iconUrl: "https://monday.com/favicon.ico",
  },
  openai: {
    text: "AI", background: "#ffffff", color: "#10a37f", borderColor: "#e5e7eb",
    iconUrl: "https://www.google.com/s2/favicons?domain=openai.com&sz=128",
  },
  pinecone: {
    text: "P", background: "#ffffff", color: "#00b894", borderColor: "#e5e7eb",
    iconUrl: "https://www.pinecone.io/favicon.ico",
  },
  postgresql: {
    text: "PG", background: "#ffffff", color: "#336791", borderColor: "#e5e7eb",
    iconUrl: "https://www.postgresql.org/favicon.ico",
  },
  quickbooks: {
    text: "QB", background: "#ffffff", color: "#2ca01c", borderColor: "#e5e7eb",
    iconUrl: "https://www.google.com/s2/favicons?domain=quickbooks.intuit.com&sz=128",
  },
  spotify: {
    text: "Sp", background: "#ffffff", color: "#1db954", borderColor: "#e5e7eb",
    iconUrl: "https://open.spotify.com/favicon.ico",
  },
  supabase: {
    text: "SB", background: "#ffffff", color: "#3ecf8e", borderColor: "#e5e7eb",
    iconUrl: "https://supabase.com/favicon/favicon-96x96.png",
  },
  trello: {
    text: "Tr", background: "#ffffff", color: "#0079bf", borderColor: "#e5e7eb",
    iconUrl: "https://trello.com/favicon.ico",
  },
  twilio: {
    text: "Tw", background: "#ffffff", color: "#f22f46", borderColor: "#e5e7eb",
    iconUrl: "https://www.twilio.com/favicon.ico",
  },
  twitter: {
    text: "X", background: "#ffffff", color: "#111827", borderColor: "#e5e7eb",
    iconUrl: "https://x.com/favicon.ico",
  },
  vercel: {
    text: "V", background: "#ffffff", color: "#111827", borderColor: "#e5e7eb",
    iconUrl: "https://vercel.com/favicon.ico",
  },
  webflow: {
    text: "WF", background: "#ffffff", color: "#4353ff", borderColor: "#e5e7eb",
    iconUrl: "https://webflow.com/favicon.ico",
  },
  xero: {
    text: "X", background: "#ffffff", color: "#13b5ea", borderColor: "#e5e7eb",
    iconUrl: "https://www.xero.com/favicon.ico",
  },
  youtube: {
    text: "YT", background: "#ffffff", color: "#ff0000", borderColor: "#e5e7eb",
    iconUrl: "https://www.youtube.com/favicon.ico",
  },
  zapier: {
    text: "Z", background: "#ffffff", color: "#ff4a00", borderColor: "#e5e7eb",
    iconUrl: "https://zapier.com/l/favicon-96.png",
  },
  playwright: {
    text: "PW", background: "#ffffff", color: "#2eab6f", borderColor: "#e5e7eb",
    iconUrl: "https://playwright.dev/img/playwright-logo.svg",
  },
  browser: {
    text: "WB", background: "#ffffff", color: "#4285f4", borderColor: "#e5e7eb",
    iconUrl: "https://www.google.com/chrome/static/images/favicons/favicon-96x96.png",
  },
  http: {
    text: "HTTP", background: "#ffffff", color: "#2563eb", borderColor: "#e5e7eb",
    iconUrl: "https://httpbin.org/static/favicon.ico",
  },
  page_monitor: {
    text: "PM", background: "#ffffff", color: "#2563eb", borderColor: "#e5e7eb",
    iconUrl: "https://www.gstatic.com/devrel-devsite/prod/v8b8ef181e1dc913802015af34f7ea88ee446e0cb5daec5c977ac4c46a7a372bd/web/images/favicon.png",
  },
  invoice: {
    text: "INV", background: "#ffffff", color: "#7c3aed", borderColor: "#e5e7eb",
    iconUrl: "https://www.google.com/s2/favicons?domain=quickbooks.intuit.com&sz=128",
  },
  email_validation: {
    text: "EV", background: "#ffffff", color: "#7c3aed", borderColor: "#e5e7eb",
    iconUrl: "https://www.zerobounce.net/favicon.ico",
  },
  sec_edgar: {
    text: "SEC", background: "#ffffff", color: "#1e293b", borderColor: "#e5e7eb",
    iconUrl: "https://www.sec.gov/favicon.ico",
  },
  newsapi: {
    text: "N", background: "#ffffff", color: "#ef4444", borderColor: "#e5e7eb",
    iconUrl: "https://newsapi.org/favicon.ico",
  },
  reddit: {
    text: "R", background: "#ffffff", color: "#ff4500", borderColor: "#e5e7eb",
    iconUrl: "https://www.reddit.com/favicon.ico",
  },
  arxiv: {
    text: "arX", background: "#ffffff", color: "#b31b1b", borderColor: "#e5e7eb",
    iconUrl: "https://arxiv.org/favicon.ico",
  },
  generic: {
    text: "?", background: "#ffffff", color: "#6b7280", borderColor: "#e5e7eb",
  },
};

export const CONNECTOR_BRAND_ALIAS_MAP: Record<string, ConnectorBrandKey> = {
  arxiv: "arxiv",
  airtable: "airtable",
  asana: "asana",
  aws: "aws",
  bigquery: "bigquery",
  bing: "bing",
  bing_search: "bing",
  box: "box",
  brave: "brave",
  brave_search: "brave",
  calendly: "calendly",
  cloudflare: "cloudflare",
  computer_use_browser: "browser",
  confluence: "confluence",
  discord: "discord",
  docusign: "docusign",
  dropbox: "dropbox",
  email_validation: "email_validation",
  excel: "excel",
  figma: "figma",
  github: "github",
  gmail: "gmail",
  gmail_playwright: "gmail", // deprecated: redirects to gmail API
  google_ads: "google_ads",
  google_analytics: "google_analytics",
  google_api_hub: "google_cloud",
  google_calendar: "google_calendar",
  google_cloud: "google_cloud",
  google_docs: "google_docs",
  google_drive: "google_drive",
  google_maps: "google_maps",
  google_sheets: "google_sheets",
  google_workspace: "google",
  hubspot: "hubspot",
  http: "http",
  http_request: "http",
  intercom: "intercom",
  invoice: "invoice",
  jira: "jira",
  linear: "linear",
  linkedin: "linkedin",
  mailchimp: "mailchimp",
  make: "make",
  m365: "microsoft",
  microsoft: "microsoft",
  microsoft_365: "microsoft",
  microsoft_calendar: "microsoft_calendar",
  microsoft_teams: "teams",
  monday: "monday",
  newsapi: "newsapi",
  notion: "notion",
  onedrive: "onedrive",
  openai: "openai",
  outlook: "outlook",
  page_monitor: "page_monitor",
  pinecone: "pinecone",
  playwright_browser: "browser", // deprecated: redirects to computer_use_browser
  playwright_contact_form: "browser", // deprecated: redirects to computer_use_browser
  postgresql: "postgresql",
  quickbooks: "quickbooks",
  reddit: "reddit",
  salesforce: "salesforce",
  sap: "sap",
  sec_edgar: "sec_edgar",
  shopify: "shopify",
  slack: "slack",
  spotify: "spotify",
  stripe: "stripe",
  supabase: "supabase",
  teams: "teams",
  trello: "trello",
  twilio: "twilio",
  twitter: "twitter",
  vercel: "vercel",
  webflow: "webflow",
  word: "word",
  xero: "xero",
  youtube: "youtube",
  zapier: "zapier",
  zapier_webhooks: "zapier",
  zendesk: "zendesk",
};

function _resolveSingleBrandKey(value: string): ConnectorBrandKey | null {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  if (CONNECTOR_BRAND_ALIAS_MAP[normalized]) {
    return CONNECTOR_BRAND_ALIAS_MAP[normalized];
  }
  if (normalized.startsWith("google_")) {
    return "google";
  }
  if (normalized.startsWith("microsoft_")) {
    return "microsoft";
  }
  return null;
}

export function resolveBrandKey(connectorId: string, brandSlug: string): ConnectorBrandKey {
  const fromConnectorId = _resolveSingleBrandKey(connectorId);
  if (fromConnectorId) {
    return fromConnectorId;
  }
  const fromBrandSlug = _resolveSingleBrandKey(brandSlug);
  if (fromBrandSlug) {
    return fromBrandSlug;
  }
  return "generic";
}


