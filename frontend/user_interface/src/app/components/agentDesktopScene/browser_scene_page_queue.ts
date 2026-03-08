import { useEffect, useMemo, useState } from "react";

type OpenedPage = {
  url: string;
  title: string;
  pageIndex: number | null;
  reviewed: boolean;
};

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
    if (primary && (primary.startsWith("http://") || primary.startsWith("https://"))) {
      setSelectedPageUrl(primary);
      return;
    }
    if (!selectedPageUrl && dedupedOpenedPages.length) {
      setSelectedPageUrl(dedupedOpenedPages[dedupedOpenedPages.length - 1].url);
    }
  }, [browserUrl, dedupedOpenedPages, selectedPageUrl]);

  return {
    dedupedOpenedPages,
    selectedPageUrl,
    setSelectedPageUrl,
    activePageUrl: selectedPageUrl || browserUrl,
  };
}

export { useBrowserPageQueue };
export type { OpenedPage };
