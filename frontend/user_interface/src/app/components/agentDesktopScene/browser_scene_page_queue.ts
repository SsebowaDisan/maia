import { useEffect, useMemo, useState } from "react";

type OpenedPage = {
  url: string;
  title: string;
  pageIndex: number | null;
  reviewed: boolean;
};

function isSearchResultsUrl(value: string): boolean {
  try {
    const parsed = new URL(String(value || "").trim());
    const host = parsed.hostname.toLowerCase();
    const path = parsed.pathname.toLowerCase();
    if (host.includes("search.brave.com")) return true;
    if (host.includes("google.") && path.startsWith("/search")) return true;
    if (host.includes("bing.com") && path.startsWith("/search")) return true;
    if (host.includes("duckduckgo.com")) return true;
  } catch {
    return false;
  }
  return false;
}

function preferredLivePageUrl(browserUrl: string, openedPages: OpenedPage[]): string {
  const primary = String(browserUrl || "").trim();
  if (!primary) {
    return openedPages[openedPages.length - 1]?.url || "";
  }
  if (!isSearchResultsUrl(primary)) {
    return primary;
  }
  for (let idx = openedPages.length - 1; idx >= 0; idx -= 1) {
    const candidate = String(openedPages[idx]?.url || "").trim();
    if (!candidate) {
      continue;
    }
    if (!isSearchResultsUrl(candidate)) {
      return candidate;
    }
  }
  return primary;
}

function useBrowserPageQueue({
  browserUrl,
  openedPages,
  pageIndex,
}: {
  browserUrl: string;
  openedPages: OpenedPage[];
  pageIndex: number | null;
}) {
  const dedupedOpenedPages = useMemo(() => {
    const seen = new Set<string>();
    const rows: OpenedPage[] = [];
    for (const row of openedPages) {
      const url = String(row?.url || "").trim();
      if (!url || seen.has(url)) continue;
      seen.add(url);
      rows.push({
        url,
        title: String(row?.title || "").trim(),
        pageIndex: typeof row?.pageIndex === "number" ? row.pageIndex : null,
        reviewed: Boolean(row?.reviewed),
      });
    }
    const fallback = String(browserUrl || "").trim();
    if (fallback && (fallback.startsWith("http://") || fallback.startsWith("https://")) && !seen.has(fallback)) {
      rows.push({
        url: fallback,
        title: "",
        pageIndex,
        reviewed: false,
      });
    }
    return rows.slice(-24);
  }, [browserUrl, openedPages, pageIndex]);

  const [selectedPageUrl, setSelectedPageUrl] = useState<string>("");
  useEffect(() => {
    const primary = String(browserUrl || "").trim();
    const preferred = preferredLivePageUrl(primary, dedupedOpenedPages);
    setSelectedPageUrl((current) => {
      const currentUrl = String(current || "").trim();
      const hasCurrent = dedupedOpenedPages.some((row) => row.url === currentUrl);
      // Keep user's selected non-primary page while runtime remains on a search results page.
      if (
        hasCurrent &&
        currentUrl &&
        primary &&
        currentUrl !== primary &&
        isSearchResultsUrl(primary)
      ) {
        return currentUrl;
      }
      if (preferred) {
        return preferred;
      }
      if (hasCurrent) {
        return currentUrl;
      }
      return "";
    });
  }, [browserUrl, dedupedOpenedPages]);

  return {
    dedupedOpenedPages,
    selectedPageUrl,
    setSelectedPageUrl,
    activePageUrl: selectedPageUrl || browserUrl,
  };
}

export { useBrowserPageQueue };
export type { OpenedPage };
