import { Globe2 } from "lucide-react";

type ConnectorBrandKey =
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
  | "bing"
  | "brave"
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

type BrandStyle = {
  text: string;
  background: string;
  color: string;
  borderColor: string;
  iconUrl?: string;
};

// Google products: official product marks from gstatic.
// Third-party brands: official favicon/logo URLs from brand-owned domains.
const _GOOGLE_PRODUCT = "https://www.gstatic.com/images/branding/product/1x/";

const BRAND_STYLE_MAP: Record<ConnectorBrandKey, BrandStyle> = {
  google: {
    text: "G", background: "#ffffff", color: "#4285f4", borderColor: "#e5e7eb",
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
    iconUrl: `${_GOOGLE_PRODUCT}calendar_48dp.png`,
  },
  google_drive: {
    text: "Dr", background: "#ffffff", color: "#4285f4", borderColor: "#e5e7eb",
    iconUrl: `${_GOOGLE_PRODUCT}drive_48dp.png`,
  },
  google_docs: {
    text: "Doc", background: "#ffffff", color: "#4285f4", borderColor: "#e5e7eb",
    iconUrl: `${_GOOGLE_PRODUCT}docs_48dp.png`,
  },
  google_sheets: {
    text: "Sh", background: "#ffffff", color: "#0f9d58", borderColor: "#e5e7eb",
    iconUrl: `${_GOOGLE_PRODUCT}sheets_48dp.png`,
  },
  google_analytics: {
    text: "GA", background: "#ffffff", color: "#e37400", borderColor: "#e5e7eb",
    iconUrl: `${_GOOGLE_PRODUCT}analytics_48dp.png`,
  },
  google_ads: {
    text: "Ads", background: "#ffffff", color: "#4285f4", borderColor: "#e5e7eb",
    iconUrl: `${_GOOGLE_PRODUCT}ads_48dp.png`,
  },
  google_maps: {
    text: "Map", background: "#ffffff", color: "#ea4335", borderColor: "#e5e7eb",
    iconUrl: `${_GOOGLE_PRODUCT}maps_48dp.png`,
  },
  microsoft: {
    text: "MS", background: "#ffffff", color: "#5E5E5E", borderColor: "#e5e7eb",
    iconUrl: "https://www.microsoft.com/favicon.ico",
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
  bing: {
    text: "B", background: "#ffffff", color: "#008373", borderColor: "#e5e7eb",
    iconUrl: "https://www.bing.com/favicon.ico",
  },
  brave: {
    text: "Br", background: "#ffffff", color: "#fb542b", borderColor: "#e5e7eb",
    iconUrl: "https://brave.com/favicon.ico",
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
    iconUrl: "/maia-icon.svg",
  },
  invoice: {
    text: "INV", background: "#ffffff", color: "#7c3aed", borderColor: "#e5e7eb",
    iconUrl: "https://www.xero.com/favicon.ico",
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

const CONNECTOR_BRAND_ALIAS_MAP: Record<string, ConnectorBrandKey> = {
  arxiv: "arxiv",
  airtable: "airtable",
  bing_search: "bing",
  brave_search: "brave",
  email_validation: "email_validation",
  excel: "excel",
  gmail: "gmail",
  gmail_playwright: "gmail",  // deprecated — redirects to gmail API
  computer_use_browser: "browser",
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
  invoice: "invoice",
  jira: "jira",
  m365: "microsoft",
  microsoft: "microsoft",
  microsoft_365: "microsoft",
  microsoft_calendar: "microsoft_calendar",
  newsapi: "newsapi",
  notion: "notion",
  onedrive: "onedrive",
  outlook: "outlook",
  page_monitor: "page_monitor",
  playwright_browser: "browser",  // deprecated — redirects to computer_use_browser
  playwright_contact_form: "browser",  // deprecated — redirects to computer_use_browser
  reddit: "reddit",
  salesforce: "salesforce",
  sap: "sap",
  sec_edgar: "sec_edgar",
  shopify: "shopify",
  slack: "slack",
  stripe: "stripe",
  teams: "teams",
  word: "word",
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

function resolveBrandKey(connectorId: string, brandSlug: string): ConnectorBrandKey {
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

function fallbackGlyph(label: string): string {
  const firstLetter = String(label || "").trim().slice(0, 1).toUpperCase();
  return firstLetter || "?";
}

function glyphClassBySize(size: number): string {
  if (size <= 16) {
    return "text-[9px]";
  }
  if (size <= 20) {
    return "text-[10px]";
  }
  return "text-[11px]";
}

type ConnectorBrandIconProps = {
  connectorId: string;
  brandSlug?: string;
  label?: string;
  size?: number;
  className?: string;
};

export function ConnectorBrandIcon({
  connectorId,
  brandSlug = "",
  label = "",
  size = 18,
  className = "",
}: ConnectorBrandIconProps) {
  const brandKey = resolveBrandKey(connectorId, brandSlug);
  const style = BRAND_STYLE_MAP[brandKey];
  const text = style.text === "?" ? fallbackGlyph(label) : style.text;
  if (brandKey === "generic") {
    return <Globe2 size={Math.max(12, size - 2)} className={`text-[#344054] ${className}`} />;
  }

  // Use official logo image when available
  if (style.iconUrl) {
    return (
      <span
        className={`inline-flex shrink-0 items-center justify-center overflow-hidden rounded-[8px] border ${className}`}
        style={{
          width: `${size}px`,
          height: `${size}px`,
          background: "#ffffff",
          borderColor: style.borderColor,
        }}
        aria-hidden="true"
        title={label || connectorId}
      >
        <img
          src={style.iconUrl}
          alt=""
          width={Math.round(size * 0.65)}
          height={Math.round(size * 0.65)}
          loading="lazy"
          className="object-contain"
          onError={(e) => {
            // Fallback to letter glyph if image fails to load
            const target = e.currentTarget;
            target.style.display = "none";
            const parent = target.parentElement;
            if (parent) {
              parent.style.background = style.background;
              parent.style.color = style.color;
              parent.textContent = text;
              parent.style.fontSize = `${Math.max(9, size * 0.32)}px`;
              parent.style.fontWeight = "700";
            }
          }}
        />
      </span>
    );
  }

  // Fallback to letter glyph
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-[8px] border font-semibold leading-none tracking-[-0.01em] ${glyphClassBySize(
        size,
      )} ${className}`}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        background: style.background,
        color: style.color,
        borderColor: style.borderColor,
      }}
      aria-hidden="true"
      title={label || connectorId}
    >
      {text}
    </span>
  );
}
