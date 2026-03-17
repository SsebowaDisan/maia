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
  if (normalized === "google_calendar" || normalized === "google_analytics") {
    return "google_workspace";
  }
  return normalized;
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
