/**
 * Hub navigation — determines if a route should open in a new tab (hub pages)
 * or stay in the current tab (chat pages).
 *
 * Hub pages: marketplace, creators, explore — open in new tab so users
 * don't lose chat context.
 *
 * Chat pages: operations, workflows, connectors, settings — stay in
 * current tab as overlays.
 */

const HUB_PATH_PREFIXES = [
  "/marketplace",
  "/creators",
  "/explore",
  "/feed",
];

/**
 * Check if a path is a hub page that should open in a new tab.
 */
export function isHubPath(path: string): boolean {
  const normalized = String(path || "").trim().toLowerCase();
  return HUB_PATH_PREFIXES.some((prefix) => normalized === prefix || normalized.startsWith(`${prefix}/`));
}

/**
 * Navigate to a path — opens hub pages in a new tab, chat pages in current tab.
 *
 * @param path - The path to navigate to
 * @param fallbackNavigate - Function to navigate within the chat shell (for overlay routes)
 */
export function navigateToRoute(path: string, fallbackNavigate: (path: string) => void): void {
  if (isHubPath(path)) {
    window.open(path, "_blank", "noopener,noreferrer");
  } else {
    fallbackNavigate(path);
  }
}

/**
 * Build props for an <a> tag that opens hub pages in new tab.
 * Returns { href, target, rel } for hub pages, or { href, onClick } for chat pages.
 */
export function hubLinkProps(path: string, onNavigate: (path: string) => void): Record<string, string | ((e: React.MouseEvent) => void)> {
  if (isHubPath(path)) {
    return {
      href: path,
      target: "_blank",
      rel: "noopener noreferrer",
    };
  }
  return {
    href: path,
    onClick: ((e: React.MouseEvent) => {
      e.preventDefault();
      onNavigate(path);
    }) as any,
  };
}
