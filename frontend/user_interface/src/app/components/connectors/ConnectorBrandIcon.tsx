import { Globe2 } from "lucide-react";

type ConnectorBrandKey =
  | "google"
  | "microsoft"
  | "slack"
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
  microsoft: {
    text: "MS",
    background: "linear-gradient(135deg, #f25022 0%, #00a4ef 35%, #7fba00 70%, #ffb900 100%)",
    color: "#ffffff",
    borderColor: "#d0d5dd",
  },
  slack: {
    text: "S",
    background: "linear-gradient(135deg, #36c5f0 0%, #2eb67d 33%, #ecb22e 66%, #e01e5a 100%)",
    color: "#ffffff",
    borderColor: "#d0d5dd",
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
  bing_search: "bing",
  brave_search: "brave",
  email_validation: "email_validation",
  gmail: "google",
  gmail_playwright: "google",
  google_ads: "google",
  google_analytics: "google",
  google_api_hub: "google",
  google_calendar: "google",
  google_maps: "google",
  google_workspace: "google",
  invoice: "invoice",
  m365: "microsoft",
  newsapi: "newsapi",
  playwright_browser: "playwright",
  playwright_contact_form: "playwright",
  reddit: "reddit",
  sec_edgar: "sec_edgar",
  slack: "slack",
};

function resolveBrandKey(connectorId: string): ConnectorBrandKey {
  const normalized = String(connectorId || "").trim().toLowerCase();
  if (!normalized) {
    return "generic";
  }
  if (normalized.startsWith("google_")) {
    return "google";
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
  label?: string;
  size?: number;
  className?: string;
};

export function ConnectorBrandIcon({
  connectorId,
  label = "",
  size = 18,
  className = "",
}: ConnectorBrandIconProps) {
  const brandKey = resolveBrandKey(connectorId);
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
