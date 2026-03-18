function normalizePathCandidate(value: string | null | undefined): string {
  const raw = String(value || "").trim();
  if (!raw) {
    return "";
  }
  if (/^[a-z]+:\/\//i.test(raw)) {
    return "";
  }
  const [pathname] = raw.split("?");
  const withLeadingSlash = pathname.startsWith("/") ? pathname : `/${pathname}`;
  if (withLeadingSlash === "/") {
    return "/";
  }
  return withLeadingSlash.replace(/\/+$/, "");
}

export function normalizeConnectorSetupId(connectorId: string | null | undefined): string {
  const normalized = String(connectorId || "").trim().toLowerCase();
  if (!normalized) {
    return "";
  }
  // Suite normalization — map any suite member to the setup root connector
  const SUITE_MAP: Record<string, string> = {
    google_workspace: "google_workspace", gmail: "google_workspace", gmail_playwright: "google_workspace",
    google_calendar: "google_workspace", google_drive: "google_workspace", google_docs: "google_workspace",
    google_sheets: "google_workspace", google_analytics: "google_workspace", google_ads: "google_workspace",
    google_maps: "google_workspace", google_api_hub: "google_workspace",
    gcalendar: "google_workspace", gdrive: "google_workspace", gdocs: "google_workspace", gsheets: "google_workspace",
    m365: "m365", microsoft: "m365", microsoft_365: "m365", outlook: "m365",
    microsoft_calendar: "m365", onedrive: "m365", excel: "m365", word: "m365", teams: "m365",
  };
  return SUITE_MAP[normalized] || normalized;
}

export function buildConnectorOverlayPath(
  connectorId?: string | null,
  options?: { fromPath?: string | null },
): string {
  const params = new URLSearchParams();
  const normalizedConnectorId = normalizeConnectorSetupId(connectorId);
  if (normalizedConnectorId) {
    params.set("connector", normalizedConnectorId);
  }
  const fromPath = normalizePathCandidate(options?.fromPath);
  if (fromPath && fromPath !== "/connectors") {
    params.set("from", fromPath);
  }
  const query = params.toString();
  return query ? `/connectors?${query}` : "/connectors";
}

export function openConnectorOverlay(
  connectorId?: string | null,
  options?: { fromPath?: string | null },
): string {
  const targetPath = buildConnectorOverlayPath(connectorId, options);
  window.history.pushState({}, "", targetPath);
  window.dispatchEvent(new PopStateEvent("popstate"));
  return targetPath;
}
