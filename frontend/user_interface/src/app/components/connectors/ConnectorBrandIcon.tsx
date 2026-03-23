import { Globe2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  BRAND_OFFICIAL_DOMAIN_MAP,
  BRAND_STYLE_MAP,
  resolveBrandKey,
} from "./connectorBrandData";
import { LOCAL_ICON_URL_MAP } from "./connectorLocalIconMap";
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

type ConnectorLogoImageProps = {
  sources: string[];
  size: number;
  onExhausted: () => void;
};

function ConnectorLogoImage({ sources, size, onExhausted }: ConnectorLogoImageProps) {
  const [sourceIndex, setSourceIndex] = useState(0);
  const activeSource = sources[sourceIndex];

  if (!activeSource) {
    return null;
  }

  return (
    <img
      src={activeSource}
      alt=""
      width={Math.round(size * 0.65)}
      height={Math.round(size * 0.65)}
      loading="lazy"
      className="object-contain"
      onError={() => {
        const nextIndex = sourceIndex + 1;
        if (nextIndex < sources.length) {
          setSourceIndex(nextIndex);
          return;
        }
        onExhausted();
      }}
    />
  );
}

function buildOfficialFaviconUrl(domain: string | undefined): string {
  const cleanDomain = String(domain || "").trim().toLowerCase();
  if (!cleanDomain) {
    return "";
  }
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(cleanDomain)}&sz=128`;
}

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
  const [showGlyphFallback, setShowGlyphFallback] = useState(false);
  const officialFaviconUrl = useMemo(
    () => buildOfficialFaviconUrl(BRAND_OFFICIAL_DOMAIN_MAP[brandKey]),
    [brandKey],
  );
  const iconSources = useMemo(() => {
    const ordered = [style.localIconUrl, style.iconUrl, officialFaviconUrl, LOCAL_ICON_URL_MAP[brandKey]].filter(
      (value): value is string => Boolean(value),
    );
    return Array.from(new Set(ordered));
  }, [brandKey, officialFaviconUrl, style.localIconUrl, style.iconUrl]);
  useEffect(() => {
    setShowGlyphFallback(false);
  }, [brandKey, iconSources.length, label, connectorId]);
  if (brandKey === "generic") {
    return <Globe2 size={Math.max(12, size - 2)} className={`text-[#344054] ${className}`} />;
  }

  if (iconSources.length > 0) {
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
        {showGlyphFallback ? (
          <span
            style={{
              color: style.color,
              fontSize: `${Math.max(9, size * 0.32)}px`,
              fontWeight: 700,
            }}
          >
            {text}
          </span>
        ) : (
          <ConnectorLogoImage
            sources={iconSources}
            size={size}
            onExhausted={() => setShowGlyphFallback(true)}
          />
        )}
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


