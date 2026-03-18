import { Globe2 } from "lucide-react";

type ConnectorBrandKey =
  | "google"
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
};

const BRAND_STYLE_MAP: Record<ConnectorBrandKey, BrandStyle> = {
  google: {
    text: "G",
    background:
      "conic-gradient(from 220deg at 50% 50%, #4285f4 0deg 95deg, #34a853 95deg 185deg, #fbbc05 185deg 275deg, #ea4335 275deg 360deg)",
    color: "#ffffff",
    borderColor: "#d0d5dd",
  },
  gmail: {
    text: "M",
    background: "linear-gradient(135deg, #ea4335 0%, #fbbc05 50%, #34a853 100%)",
    color: "#ffffff",
    borderColor: "#fecaca",
  },
  google_calendar: {
    text: "31",
    background: "linear-gradient(135deg, #3b82f6 0%, #60a5fa 100%)",
    color: "#ffffff",
    borderColor: "#bfdbfe",
  },
  google_drive: {
    text: "Dr",
    background: "linear-gradient(135deg, #0f9d58 0%, #34a853 100%)",
    color: "#ffffff",
    borderColor: "#bbf7d0",
  },
  google_docs: {
    text: "Doc",
    background: "linear-gradient(135deg, #2563eb 0%, #60a5fa 100%)",
    color: "#ffffff",
    borderColor: "#bfdbfe",
  },
  google_sheets: {
    text: "Sh",
    background: "linear-gradient(135deg, #16a34a 0%, #4ade80 100%)",
    color: "#14532d",
    borderColor: "#bbf7d0",
  },
  google_analytics: {
    text: "GA",
    background: "linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%)",
    color: "#78350f",
    borderColor: "#fde68a",
  },
  google_ads: {
    text: "Ads",
    background: "linear-gradient(135deg, #2563eb 0%, #22c55e 100%)",
    color: "#ffffff",
    borderColor: "#bfdbfe",
  },
  google_maps: {
    text: "Map",
    background: "linear-gradient(135deg, #22c55e 0%, #3b82f6 100%)",
    color: "#ffffff",
    borderColor: "#bfdbfe",
  },
  microsoft: {
    text: "MS",
    background: "linear-gradient(135deg, #f25022 0%, #00a4ef 35%, #7fba00 70%, #ffb900 100%)",
    color: "#ffffff",
    borderColor: "#d0d5dd",
  },
  outlook: {
    text: "O",
    background: "linear-gradient(135deg, #0a66c2 0%, #2563eb 100%)",
    color: "#ffffff",
    borderColor: "#bfdbfe",
  },
  microsoft_calendar: {
    text: "Cal",
    background: "linear-gradient(135deg, #0f766e 0%, #2dd4bf 100%)",
    color: "#f0fdfa",
    borderColor: "#99f6e4",
  },
  onedrive: {
    text: "1D",
    background: "linear-gradient(135deg, #2563eb 0%, #38bdf8 100%)",
    color: "#ffffff",
    borderColor: "#bae6fd",
  },
  excel: {
    text: "X",
    background: "linear-gradient(135deg, #166534 0%, #22c55e 100%)",
    color: "#ffffff",
    borderColor: "#bbf7d0",
  },
  word: {
    text: "W",
    background: "linear-gradient(135deg, #1d4ed8 0%, #60a5fa 100%)",
    color: "#ffffff",
    borderColor: "#bfdbfe",
  },
  teams: {
    text: "T",
    background: "linear-gradient(135deg, #4f46e5 0%, #a78bfa 100%)",
    color: "#ffffff",
    borderColor: "#ddd6fe",
  },
  slack: {
    text: "S",
    background: "linear-gradient(135deg, #36c5f0 0%, #2eb67d 33%, #ecb22e 66%, #e01e5a 100%)",
    color: "#ffffff",
    borderColor: "#d0d5dd",
  },
  notion: {
    text: "N",
    background: "linear-gradient(135deg, #111827 0%, #374151 100%)",
    color: "#ffffff",
    borderColor: "#d1d5db",
  },
  hubspot: {
    text: "H",
    background: "linear-gradient(135deg, #f97316 0%, #fb923c 100%)",
    color: "#7c2d12",
    borderColor: "#fdba74",
  },
  salesforce: {
    text: "SF",
    background: "linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%)",
    color: "#082f49",
    borderColor: "#bae6fd",
  },
  jira: {
    text: "J",
    background: "linear-gradient(135deg, #2563eb 0%, #818cf8 100%)",
    color: "#ffffff",
    borderColor: "#c7d2fe",
  },
  airtable: {
    text: "AT",
    background: "linear-gradient(135deg, #ef4444 0%, #f59e0b 50%, #22c55e 100%)",
    color: "#ffffff",
    borderColor: "#fed7aa",
  },
  zendesk: {
    text: "Z",
    background: "linear-gradient(135deg, #14532d 0%, #16a34a 100%)",
    color: "#ffffff",
    borderColor: "#bbf7d0",
  },
  stripe: {
    text: "St",
    background: "linear-gradient(135deg, #635bff 0%, #8b5cf6 100%)",
    color: "#ffffff",
    borderColor: "#ddd6fe",
  },
  shopify: {
    text: "Sh",
    background: "linear-gradient(135deg, #4ade80 0%, #16a34a 100%)",
    color: "#14532d",
    borderColor: "#bbf7d0",
  },
  sap: {
    text: "SAP",
    background: "linear-gradient(135deg, #0092d1 0%, #38bdf8 100%)",
    color: "#f8fafc",
    borderColor: "#bae6fd",
  },
  bing: {
    text: "B",
    background: "linear-gradient(135deg, #008373 0%, #5eead4 100%)",
    color: "#083344",
    borderColor: "#99f6e4",
  },
  brave: {
    text: "Br",
    background: "linear-gradient(135deg, #fb923c 0%, #f97316 100%)",
    color: "#7c2d12",
    borderColor: "#fdba74",
  },
  playwright: {
    text: "PW",
    background: "linear-gradient(135deg, #16a34a 0%, #86efac 100%)",
    color: "#14532d",
    borderColor: "#bbf7d0",
  },
  invoice: {
    text: "INV",
    background: "linear-gradient(135deg, #a78bfa 0%, #c4b5fd 100%)",
    color: "#4c1d95",
    borderColor: "#ddd6fe",
  },
  email_validation: {
    text: "EV",
    background: "linear-gradient(135deg, #a78bfa 0%, #c4b5fd 100%)",
    color: "#4c1d95",
    borderColor: "#c4b5fd",
  },
  sec_edgar: {
    text: "SEC",
    background: "linear-gradient(135deg, #94a3b8 0%, #e2e8f0 100%)",
    color: "#1e293b",
    borderColor: "#cbd5e1",
  },
  newsapi: {
    text: "N",
    background: "linear-gradient(135deg, #f87171 0%, #fca5a5 100%)",
    color: "#7f1d1d",
    borderColor: "#fecaca",
  },
  reddit: {
    text: "R",
    background: "linear-gradient(135deg, #fb923c 0%, #f97316 100%)",
    color: "#7c2d12",
    borderColor: "#fdba74",
  },
  arxiv: {
    text: "arX",
    background: "linear-gradient(135deg, #6ee7b7 0%, #34d399 100%)",
    color: "#064e3b",
    borderColor: "#a7f3d0",
  },
  generic: {
    text: "?",
    background: "linear-gradient(135deg, #e2e8f0 0%, #f8fafc 100%)",
    color: "#334155",
    borderColor: "#d0d5dd",
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
  google_api_hub: "google",
  google_calendar: "google_calendar",
  google_docs: "google_docs",
  google_drive: "google_drive",
  google_maps: "google_maps",
  google_sheets: "google_sheets",
  google_workspace: "google",
  hubspot: "hubspot",
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

function resolveBrandKey(value: string): ConnectorBrandKey {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return "generic";
  }
  if (normalized.startsWith("google_")) {
    return "google";
  }
  if (normalized.startsWith("microsoft_")) {
    return "microsoft";
  }
  return CONNECTOR_BRAND_ALIAS_MAP[normalized] || "generic";
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
  const brandKey = resolveBrandKey(brandSlug || connectorId);
  const style = BRAND_STYLE_MAP[brandKey];
  const text = style.text === "?" ? fallbackGlyph(label) : style.text;
  if (brandKey === "generic") {
    return <Globe2 size={Math.max(12, size - 2)} className={`text-[#344054] ${className}`} />;
  }
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
