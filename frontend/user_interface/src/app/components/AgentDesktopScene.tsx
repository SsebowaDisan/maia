import { useEffect, useRef, useState } from "react";
import { renderRichText } from "../utils/richText";

type AgentDesktopSceneProps = {
  snapshotUrl: string;
  isBrowserScene: boolean;
  isEmailScene: boolean;
  isDocumentScene: boolean;
  isDocsScene: boolean;
  isSheetsScene: boolean;
  isSystemScene: boolean;
  canRenderPdfFrame: boolean;
  stageFileUrl: string;
  stageFileName: string;
  browserUrl: string;
  emailRecipient: string;
  emailSubject: string;
  emailBodyHint: string;
  docBodyHint: string;
  sheetBodyHint: string;
  sceneText: string;
  activeTitle: string;
  activeDetail: string;
  activeEventType: string;
  activeSceneData: Record<string, unknown>;
  sceneDocumentUrl?: string;
  sceneSpreadsheetUrl?: string;
  onSnapshotError?: () => void;
};

export function AgentDesktopScene({
  snapshotUrl,
  isBrowserScene,
  isEmailScene,
  isDocumentScene,
  isDocsScene,
  isSheetsScene,
  isSystemScene,
  canRenderPdfFrame,
  stageFileUrl,
  stageFileName,
  browserUrl,
  emailRecipient,
  emailSubject,
  emailBodyHint,
  docBodyHint,
  sheetBodyHint,
  sceneText,
  activeTitle,
  activeDetail,
  activeEventType,
  activeSceneData,
  sceneDocumentUrl,
  sceneSpreadsheetUrl,
  onSnapshotError,
}: AgentDesktopSceneProps) {
  const compactValue = (value: unknown): string => (typeof value === "string" ? value.trim() : "");
  const readStringList = (value: unknown, limit = 12): string[] => {
    if (!Array.isArray(value)) {
      return [];
    }
    const cleaned = value
      .map((item) => String(item || "").trim())
      .filter((item) => item.length > 0);
    return Array.from(new Set(cleaned)).slice(0, Math.max(1, limit));
  };

  const highlightRegions = Array.isArray(activeSceneData["highlight_regions"])
    ? activeSceneData["highlight_regions"]
        .map((item) => {
          if (!item || typeof item !== "object") {
            return null;
          }
          const row = item as Record<string, unknown>;
          const toPercent = (value: unknown, fallback: number) => {
            const parsed = typeof value === "number" ? value : Number(value);
            if (!Number.isFinite(parsed)) {
              return fallback;
            }
            return Math.max(0, Math.min(100, Number(parsed)));
          };
          const keyword = String(row["keyword"] || "").trim();
          const color = String(row["color"] || activeSceneData["highlight_color"] || "yellow")
            .trim()
            .toLowerCase() === "green"
            ? "green"
            : "yellow";
          const x = toPercent(row["x"], 0);
          const y = toPercent(row["y"], 0);
          const width = Math.max(1, toPercent(row["width"], 8));
          const height = Math.max(1, toPercent(row["height"], 3));
          return { keyword, color, x, y, width, height };
        })
        .filter(
          (
            item,
          ): item is {
            keyword: string;
            color: "yellow" | "green";
            x: number;
            y: number;
            width: number;
            height: number;
          } => Boolean(item),
        )
        .slice(0, 8)
    : [];
  const browserKeywords = [
    ...readStringList(activeSceneData["highlighted_keywords"], 10),
    ...readStringList(activeSceneData["keywords"], 10),
  ];
  const dedupedBrowserKeywords = Array.from(new Set(browserKeywords)).slice(0, 10);
  const explicitFindQuery = compactValue(activeSceneData["find_query"]);
  const findQuery =
    explicitFindQuery || dedupedBrowserKeywords.slice(0, 2).join(" ").trim();
  const matchCountRaw =
    typeof activeSceneData["match_count"] === "number"
      ? activeSceneData["match_count"]
      : Number(activeSceneData["match_count"]);
  const findMatchCount = Number.isFinite(matchCountRaw)
    ? Math.max(0, Number(matchCountRaw))
    : highlightRegions.length;
  const showFindOverlay =
    isBrowserScene &&
    Boolean(findQuery || dedupedBrowserKeywords.length || highlightRegions.length) &&
    (
      activeEventType === "browser_find_in_page" ||
      activeEventType === "browser_keyword_highlight" ||
      activeEventType === "browser_copy_selection" ||
      highlightRegions.length > 0
    );
  const documentHighlights = Array.isArray(activeSceneData["highlighted_words"])
    ? activeSceneData["highlighted_words"]
        .map((item) => {
          if (!item || typeof item !== "object") {
            return null;
          }
          const row = item as Record<string, unknown>;
          const word = String(row["word"] || "").trim();
          const snippet = String(row["snippet"] || "").trim();
          const color = String(row["color"] || activeSceneData["highlight_color"] || "yellow")
            .trim()
            .toLowerCase() === "green"
            ? "green"
            : "yellow";
          if (!word && !snippet) {
            return null;
          }
          return { word, snippet, color };
        })
        .filter((item): item is { word: string; snippet: string; color: "yellow" | "green" } => Boolean(item))
        .slice(0, 8)
    : [];
  const highlightPalette = (color: "yellow" | "green") =>
    color === "green"
      ? {
          border: "rgba(112, 216, 123, 0.95)",
          fill: "rgba(112, 216, 123, 0.22)",
          labelBackground: "rgba(112, 216, 123, 0.95)",
          labelText: "#102915",
        }
      : {
          border: "rgba(255, 213, 79, 0.95)",
          fill: "rgba(255, 213, 79, 0.22)",
          labelBackground: "rgba(255, 213, 79, 0.95)",
          labelText: "#2b2410",
        };
  const documentUrl = compactValue(sceneDocumentUrl) || compactValue(activeSceneData["document_url"]);
  const spreadsheetUrl = compactValue(sceneSpreadsheetUrl) || compactValue(activeSceneData["spreadsheet_url"]);
  const docsFrameUrl =
    documentUrl.startsWith("http://") || documentUrl.startsWith("https://") ? documentUrl : "";
  const sheetsFrameUrl =
    spreadsheetUrl.startsWith("http://") || spreadsheetUrl.startsWith("https://") ? spreadsheetUrl : "";
  const clipboardPreview = typeof activeSceneData["clipboard_text"] === "string"
    ? activeSceneData["clipboard_text"]
    : "";
  const copiedWords = readStringList(activeSceneData["copied_words"], 8);
  const clipboardWords = clipboardPreview
    .split(/\s+/)
    .map((word) => word.trim())
    .filter((word) => word.length > 0)
    .slice(0, 8);
  const liveCopiedWords = copiedWords.length ? copiedWords : clipboardWords;
  const liveCopiedWordsKey = liveCopiedWords.join("|");
  const canRenderLiveUrl =
    browserUrl.startsWith("http://") || browserUrl.startsWith("https://");
  const scrollPercentRaw =
    typeof activeSceneData["scroll_percent"] === "number"
      ? activeSceneData["scroll_percent"]
      : Number(activeSceneData["scroll_percent"]);
  const scrollPercent = Number.isFinite(scrollPercentRaw)
    ? Math.max(0, Math.min(100, Number(scrollPercentRaw)))
    : null;
  const emailBodyPreview = String(emailBodyHint || "").trim() || "Composing message body...";
  const emailBodyHtml = renderRichText(emailBodyPreview);
  const emailBodyScrollRef = useRef<HTMLDivElement | null>(null);
  const rawDocBodyPreview = String(docBodyHint || "").trim();
  const rawSheetBodyPreview = String(sheetBodyHint || "").trim();
  const [typedDocBodyPreview, setTypedDocBodyPreview] = useState("");
  const [typedSheetBodyPreview, setTypedSheetBodyPreview] = useState("");
  const [copyPulseText, setCopyPulseText] = useState("");
  const [copyPulseVisible, setCopyPulseVisible] = useState(false);
  const typedDocBodyRef = useRef("");
  const typedSheetBodyRef = useRef("");
  const docTypingTimerRef = useRef<number | null>(null);
  const sheetTypingTimerRef = useRef<number | null>(null);
  const copyPulseTimerRef = useRef<number | null>(null);
  const docBodyPreview = typedDocBodyPreview || rawDocBodyPreview;
  const docBodyHtml = renderRichText(docBodyPreview);
  const docBodyScrollRef = useRef<HTMLDivElement | null>(null);
  const sheetBodyPreview = typedSheetBodyPreview || rawSheetBodyPreview;
  const sheetStatusLine = sheetBodyPreview
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
    .slice(-1)[0] || "";
  const sheetPreviewRows = sheetBodyPreview
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0)
    .slice(-12);

  useEffect(() => {
    if (!isEmailScene) {
      return;
    }
    const node = emailBodyScrollRef.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [emailBodyPreview, isEmailScene]);

  useEffect(() => {
    typedDocBodyRef.current = typedDocBodyPreview;
  }, [typedDocBodyPreview]);

  useEffect(() => {
    typedSheetBodyRef.current = typedSheetBodyPreview;
  }, [typedSheetBodyPreview]);

  useEffect(() => {
    if (activeEventType !== "browser_copy_selection") {
      return;
    }
    const tokenFromKey = liveCopiedWordsKey
      .split("|")
      .map((item) => item.trim())
      .find((item) => item.length > 0) || "";
    const token =
      tokenFromKey ||
      clipboardPreview.split(/\s+/).map((item) => item.trim()).find((item) => item.length > 0) ||
      "";
    if (!token) {
      return;
    }
    setCopyPulseText(token);
    setCopyPulseVisible(true);
    if (copyPulseTimerRef.current) {
      window.clearTimeout(copyPulseTimerRef.current);
      copyPulseTimerRef.current = null;
    }
    copyPulseTimerRef.current = window.setTimeout(() => {
      setCopyPulseVisible(false);
      copyPulseTimerRef.current = null;
    }, 1900);
  }, [activeEventType, clipboardPreview, liveCopiedWordsKey]);

  useEffect(
    () => () => {
      if (copyPulseTimerRef.current) {
        window.clearTimeout(copyPulseTimerRef.current);
        copyPulseTimerRef.current = null;
      }
    },
    [],
  );

  useEffect(() => {
    if (!isDocsScene) {
      return;
    }
    const node = docBodyScrollRef.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [docBodyPreview, isDocsScene]);

  useEffect(() => {
    if (!isDocsScene) {
      return;
    }
    if (docTypingTimerRef.current) {
      window.clearInterval(docTypingTimerRef.current);
      docTypingTimerRef.current = null;
    }
    if (!rawDocBodyPreview) {
      setTypedDocBodyPreview("");
      return;
    }
    let cursor = 0;
    const current = typedDocBodyRef.current;
    const maxPrefix = Math.min(current.length, rawDocBodyPreview.length);
    while (cursor < maxPrefix && current[cursor] === rawDocBodyPreview[cursor]) {
      cursor += 1;
    }
    setTypedDocBodyPreview(rawDocBodyPreview.slice(0, cursor));
    if (cursor >= rawDocBodyPreview.length) {
      return;
    }
    docTypingTimerRef.current = window.setInterval(() => {
      cursor = Math.min(rawDocBodyPreview.length, cursor + Math.max(1, Math.ceil((rawDocBodyPreview.length - cursor) / 22)));
      setTypedDocBodyPreview(rawDocBodyPreview.slice(0, cursor));
      if (cursor >= rawDocBodyPreview.length && docTypingTimerRef.current) {
        window.clearInterval(docTypingTimerRef.current);
        docTypingTimerRef.current = null;
      }
    }, 16);
    return () => {
      if (docTypingTimerRef.current) {
        window.clearInterval(docTypingTimerRef.current);
        docTypingTimerRef.current = null;
      }
    };
  }, [isDocsScene, rawDocBodyPreview]);

  useEffect(() => {
    if (!isSheetsScene) {
      return;
    }
    if (sheetTypingTimerRef.current) {
      window.clearInterval(sheetTypingTimerRef.current);
      sheetTypingTimerRef.current = null;
    }
    if (!rawSheetBodyPreview) {
      setTypedSheetBodyPreview("");
      return;
    }
    let cursor = 0;
    const current = typedSheetBodyRef.current;
    const maxPrefix = Math.min(current.length, rawSheetBodyPreview.length);
    while (cursor < maxPrefix && current[cursor] === rawSheetBodyPreview[cursor]) {
      cursor += 1;
    }
    setTypedSheetBodyPreview(rawSheetBodyPreview.slice(0, cursor));
    if (cursor >= rawSheetBodyPreview.length) {
      return;
    }
    sheetTypingTimerRef.current = window.setInterval(() => {
      cursor = Math.min(rawSheetBodyPreview.length, cursor + Math.max(1, Math.ceil((rawSheetBodyPreview.length - cursor) / 26)));
      setTypedSheetBodyPreview(rawSheetBodyPreview.slice(0, cursor));
      if (cursor >= rawSheetBodyPreview.length && sheetTypingTimerRef.current) {
        window.clearInterval(sheetTypingTimerRef.current);
        sheetTypingTimerRef.current = null;
      }
    }, 16);
    return () => {
      if (sheetTypingTimerRef.current) {
        window.clearInterval(sheetTypingTimerRef.current);
        sheetTypingTimerRef.current = null;
      }
    };
  }, [isSheetsScene, rawSheetBodyPreview]);

  if (isBrowserScene) {
    const showSnapshotPrimary = Boolean(snapshotUrl);
    return (
      <div className="absolute inset-0 flex flex-col bg-[#0d1118] text-white/90">
        <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2">
          <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
          <div className="ml-2 flex-1 truncate rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[11px] text-white/85">
            {browserUrl || "Searching the web and opening result pages..."}
          </div>
        </div>
        {showSnapshotPrimary ? (
          <div className="relative flex-1 bg-[#0a0c10]">
            <img
              src={snapshotUrl}
              alt="Live browser capture"
              className="h-full w-full object-cover"
              onError={onSnapshotError}
            />
            {highlightRegions.length ? (
              <div className="pointer-events-none absolute inset-0">
                {highlightRegions.map((region, index) => {
                  const palette = highlightPalette(region.color);
                  return (
                    <div
                      key={`${region.keyword}-${index}`}
                      className="absolute rounded-md"
                      style={{
                        left: `${region.x}%`,
                        top: `${region.y}%`,
                        width: `${region.width}%`,
                        height: `${region.height}%`,
                        border: `1px solid ${palette.border}`,
                        backgroundColor: palette.fill,
                        boxShadow: `0 0 0 1px ${palette.fill}`,
                      }}
                    >
                      {region.keyword ? (
                        <span
                          className="absolute -top-5 left-0 rounded px-1.5 py-0.5 text-[10px] font-semibold"
                          style={{ backgroundColor: palette.labelBackground, color: palette.labelText }}
                        >
                          {region.keyword}
                        </span>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ) : null}
            {showFindOverlay ? (
              <div className="pointer-events-none absolute left-1/2 top-3 z-20 w-[min(74%,580px)] -translate-x-1/2 rounded-xl border border-black/15 bg-white/88 px-3 py-2 text-[#232327] shadow-[0_8px_22px_-16px_rgba(0,0,0,0.55)] backdrop-blur-sm">
                <div className="flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">
                  <span>Find in page</span>
                  <span>{findMatchCount ? `${Math.max(1, Math.round(findMatchCount))} matches` : "Scanning..."}</span>
                </div>
                <div className="mt-1.5 rounded-full border border-black/10 bg-white px-2.5 py-1 text-[12px] text-[#1f1f22]">
                  {findQuery || dedupedBrowserKeywords.join(" ").slice(0, 90) || "Searching highlighted terms..."}
                </div>
                {dedupedBrowserKeywords.length ? (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {dedupedBrowserKeywords.slice(0, 6).map((term) => (
                      <span
                        key={`find-chip-${term}`}
                        className="rounded-full border border-black/10 bg-white/90 px-2 py-0.5 text-[10px] text-[#4c4c50]"
                      >
                        {term}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            {copyPulseVisible ? (
              <div className="pointer-events-none absolute right-4 bottom-16 z-20 transition-all duration-300">
                <div className="rounded-full border border-[#ffdc80]/70 bg-[#fff5cf]/95 px-3 py-1.5 text-[11px] font-medium text-[#3a2d0d] shadow-[0_14px_30px_-22px_rgba(0,0,0,0.65)]">
                  Copied: <span className="font-semibold">{copyPulseText}</span>
                </div>
              </div>
            ) : null}
            <div className="pointer-events-none absolute left-3 right-3 bottom-3 rounded-lg border border-black/10 bg-white/78 px-3 py-1.5 text-[11px] text-[#3a3a3c] backdrop-blur-sm">
              {sceneText || activeDetail || activeTitle || "Inspecting website and gathering evidence."}
            </div>
            {typeof scrollPercent === "number" ? (
              <div className="pointer-events-none absolute right-2 top-20 bottom-6 flex flex-col items-center">
                <div className="h-full w-1.5 rounded-full bg-black/20">
                  <div
                    className="w-1.5 rounded-full bg-black/60 transition-all duration-300"
                    style={{ height: "24px", marginTop: `calc(${scrollPercent}% - 12px)` }}
                  />
                </div>
                <span className="mt-1 text-[10px] font-medium text-black/70">
                  {Math.round(scrollPercent)}%
                </span>
              </div>
            ) : null}
          </div>
        ) : canRenderLiveUrl ? (
          <div className="relative flex-1 bg-white">
            <iframe
              src={browserUrl}
              title="Live website preview"
              className="h-full w-full border-0"
              sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
              referrerPolicy="no-referrer-when-downgrade"
            />
            {highlightRegions.length ? (
              <div className="pointer-events-none absolute inset-0">
                {highlightRegions.map((region, index) => {
                  const palette = highlightPalette(region.color);
                  return (
                    <div
                      key={`${region.keyword}-iframe-${index}`}
                      className="absolute rounded-md"
                      style={{
                        left: `${region.x}%`,
                        top: `${region.y}%`,
                        width: `${region.width}%`,
                        height: `${region.height}%`,
                        border: `1px solid ${palette.border}`,
                        backgroundColor: palette.fill,
                        boxShadow: `0 0 0 1px ${palette.fill}`,
                      }}
                    >
                      {region.keyword ? (
                        <span
                          className="absolute -top-5 left-0 rounded px-1.5 py-0.5 text-[10px] font-semibold"
                          style={{ backgroundColor: palette.labelBackground, color: palette.labelText }}
                        >
                          {region.keyword}
                        </span>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            ) : null}
            {showFindOverlay ? (
              <div className="pointer-events-none absolute left-1/2 top-3 z-20 w-[min(74%,580px)] -translate-x-1/2 rounded-xl border border-black/15 bg-white/88 px-3 py-2 text-[#232327] shadow-[0_8px_22px_-16px_rgba(0,0,0,0.55)] backdrop-blur-sm">
                <div className="flex items-center justify-between gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">
                  <span>Find in page</span>
                  <span>{findMatchCount ? `${Math.max(1, Math.round(findMatchCount))} matches` : "Scanning..."}</span>
                </div>
                <div className="mt-1.5 rounded-full border border-black/10 bg-white px-2.5 py-1 text-[12px] text-[#1f1f22]">
                  {findQuery || dedupedBrowserKeywords.join(" ").slice(0, 90) || "Searching highlighted terms..."}
                </div>
                {dedupedBrowserKeywords.length ? (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {dedupedBrowserKeywords.slice(0, 6).map((term) => (
                      <span
                        key={`find-chip-iframe-${term}`}
                        className="rounded-full border border-black/10 bg-white/90 px-2 py-0.5 text-[10px] text-[#4c4c50]"
                      >
                        {term}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            {copyPulseVisible ? (
              <div className="pointer-events-none absolute right-4 bottom-16 z-20 transition-all duration-300">
                <div className="rounded-full border border-[#ffdc80]/70 bg-[#fff5cf]/95 px-3 py-1.5 text-[11px] font-medium text-[#3a2d0d] shadow-[0_14px_30px_-22px_rgba(0,0,0,0.65)]">
                  Copied: <span className="font-semibold">{copyPulseText}</span>
                </div>
              </div>
            ) : null}
            <div className="pointer-events-none absolute left-3 right-3 bottom-3 rounded-lg border border-black/10 bg-white/78 px-3 py-1.5 text-[11px] text-[#3a3a3c] backdrop-blur-sm">
              {sceneText || activeDetail || activeTitle || "Inspecting website and gathering evidence."}
            </div>
            {typeof scrollPercent === "number" ? (
              <div className="pointer-events-none absolute right-2 top-20 bottom-6 flex flex-col items-center">
                <div className="h-full w-1.5 rounded-full bg-black/20">
                  <div
                    className="w-1.5 rounded-full bg-black/60 transition-all duration-300"
                    style={{ height: "24px", marginTop: `calc(${scrollPercent}% - 12px)` }}
                  />
                </div>
                <span className="mt-1 text-[10px] font-medium text-black/70">
                  {Math.round(scrollPercent)}%
                </span>
              </div>
            ) : null}
          </div>
        ) : (
          <div className="relative flex-1 space-y-3 p-4">
            <p className="text-[13px] font-semibold text-white">{activeTitle || "Browser scene"}</p>
            <p className="text-[12px] text-white/80">
              {sceneText || activeDetail || "Inspecting page content and extracting evidence..."}
            </p>
            <div className="space-y-2">
              <div className="h-2 w-[92%] rounded-full bg-white/20" />
              <div className="h-2 w-[84%] rounded-full bg-white/15" />
              <div className="h-2 w-[88%] rounded-full bg-white/20" />
              <div className="h-2 w-[63%] rounded-full bg-white/15" />
            </div>
            {showFindOverlay ? (
              <div className="rounded-lg border border-white/20 bg-white/10 px-2.5 py-2 text-[11px] text-white/90">
                <p className="font-semibold">Find: {findQuery || dedupedBrowserKeywords.slice(0, 2).join(" ")}</p>
                {dedupedBrowserKeywords.length ? (
                  <p className="mt-0.5 text-white/75">
                    Terms: {dedupedBrowserKeywords.slice(0, 5).join(", ")}
                  </p>
                ) : null}
              </div>
            ) : null}
            {copyPulseVisible ? (
              <div className="rounded-lg border border-[#ffdc80]/60 bg-[#fff5cf]/90 px-2.5 py-1.5 text-[11px] text-[#2f250f]">
                Copied: {copyPulseText}
              </div>
            ) : null}
            {snapshotUrl ? (
              <img
                src={snapshotUrl}
                alt="Browser capture"
                className="absolute bottom-3 right-3 h-24 w-36 rounded-lg border border-white/20 object-cover"
                onError={onSnapshotError}
              />
            ) : null}
          </div>
        )}
      </div>
    );
  }

  if (
    snapshotUrl &&
    !isEmailScene &&
    !isDocumentScene &&
    !isDocsScene &&
    !isSheetsScene &&
    !isSystemScene
  ) {
    return (
      <div className="absolute inset-0">
        <img
          src={snapshotUrl}
          alt="Agent scene snapshot"
          className="absolute inset-0 h-full w-full object-cover"
          onError={onSnapshotError}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/55 via-black/15 to-black/20" />
        <div className="absolute left-3 right-3 top-3 rounded-xl border border-white/20 bg-black/45 px-3 py-2 text-white backdrop-blur-sm">
          <p className="text-[12px] font-semibold">
            {activeTitle || (isBrowserScene ? "Live browser capture" : "Live scene capture")}
          </p>
          <p className="mt-0.5 line-clamp-2 text-[11px] text-white/85">
            {sceneText ||
              activeDetail ||
              (isBrowserScene
                ? "Inspecting website and extracting evidence."
                : "Running live agent action.")}
          </p>
        </div>
      </div>
    );
  }

  if (isEmailScene) {
    return (
      <div className="absolute inset-0 bg-[linear-gradient(180deg,#e8eaef_0%,#dfe3ea_100%)] p-4 text-[#1d1d1f]">
        <div className="mx-auto h-full w-full max-w-[920px] rounded-[18px] border border-black/[0.08] bg-white shadow-[0_26px_60px_-40px_rgba(0,0,0,0.55)]">
          <div className="flex items-center gap-2 border-b border-black/[0.08] px-4 py-2.5">
            <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
            <span className="ml-2 text-[12px] font-semibold tracking-tight text-[#3a3a3c]">Compose</span>
          </div>
          <div className="space-y-2 p-4 text-[12px]">
            <div className="rounded-xl border border-black/[0.07] bg-[#fafafc] px-3 py-2.5">
              <span className="font-semibold text-[#6e6e73]">To:</span>{" "}
              <span className="text-[#1d1d1f]">{emailRecipient}</span>
            </div>
            <div className="rounded-xl border border-black/[0.07] bg-[#fafafc] px-3 py-2.5">
              <span className="font-semibold text-[#6e6e73]">Subject:</span>{" "}
              <span className="text-[#1d1d1f]">{emailSubject}</span>
            </div>
            <div
              ref={emailBodyScrollRef}
              className="h-[320px] overflow-y-auto rounded-xl border border-black/[0.07] bg-white px-3 py-3 text-[14px] leading-[1.6] text-[#1f1f22]"
            >
              <div
                className="[&_h1]:mb-2 [&_h1]:text-[21px] [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:text-[18px] [&_h2]:font-semibold [&_h3]:mb-1.5 [&_h3]:text-[16px] [&_h3]:font-semibold [&_p]:mb-2 [&_ul]:mb-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:mb-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_code]:rounded [&_code]:bg-[#f2f2f7] [&_code]:px-1 [&_code]:py-0.5 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-[#f2f2f7] [&_pre]:p-2 [&_a]:text-[#0a66d9] hover:[&_a]:underline"
                dangerouslySetInnerHTML={{ __html: emailBodyHtml }}
              />
            </div>
            {activeEventType === "email_click_send" ? (
              <div className="rounded-xl border border-[#0a84ff]/25 bg-[#0a84ff]/10 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#0756a8]">
                Send action confirmed
              </div>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  if (isSheetsScene) {
    return (
      <div className="absolute inset-0 bg-[linear-gradient(180deg,#e6e8ee_0%,#dce0e9_100%)] p-3 text-[#1d1d1f]">
        <div className="h-full w-full overflow-hidden rounded-[18px] border border-black/[0.08] bg-white shadow-[0_26px_60px_-40px_rgba(0,0,0,0.55)]">
          <div className="flex items-center gap-2 border-b border-black/[0.08] px-3 py-2">
            <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
            <span className="ml-2 text-[12px] font-semibold tracking-tight text-[#3a3a3c]">
              Google Sheets
            </span>
            {sheetsFrameUrl ? (
              <span className="ml-2 max-w-[65%] truncate rounded-full border border-black/[0.08] bg-[#f7f7f9] px-2.5 py-0.5 text-[10px] text-[#4c4c50]">
                {sheetsFrameUrl}
              </span>
            ) : null}
          </div>
          <div className="relative h-[calc(100%-42px)] bg-[#f5f6f8]">
            {sheetsFrameUrl ? (
              <iframe
                src={sheetsFrameUrl}
                title="Google Sheets live preview"
                className="h-full w-full border-0 bg-white"
                sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
                referrerPolicy="no-referrer-when-downgrade"
              />
            ) : (
              <div className="h-full p-5">
                <div className="h-full rounded-xl border border-black/[0.08] bg-white">
                  <div className="grid grid-cols-[120px_repeat(4,minmax(0,1fr))] border-b border-black/[0.06] bg-[#f8f9fc] text-[10px] font-semibold uppercase tracking-[0.08em] text-[#7b7b80]">
                    <div className="border-r border-black/[0.06] px-3 py-2">A</div>
                    <div className="border-r border-black/[0.06] px-3 py-2">B</div>
                    <div className="border-r border-black/[0.06] px-3 py-2">C</div>
                    <div className="border-r border-black/[0.06] px-3 py-2">D</div>
                    <div className="px-3 py-2">E</div>
                  </div>
                  <div className="space-y-0">
                    {sheetPreviewRows.length ? (
                      sheetPreviewRows.map((row, rowIndex) => (
                        <div
                          key={`sheet-row-${rowIndex}`}
                          className="grid grid-cols-[120px_repeat(4,minmax(0,1fr))] border-b border-black/[0.05] text-[12px] text-[#2a2a2d]"
                        >
                          <div className="border-r border-black/[0.05] px-3 py-2 text-[#6e6e73]">{rowIndex + 1}</div>
                          <div className="col-span-4 px-3 py-2 font-medium">{row}</div>
                        </div>
                      ))
                    ) : (
                      <div className="px-3 py-3 text-[12px] text-[#4c4c50]">
                        {sceneText || activeDetail || "Preparing Google Sheets tracker and writing execution roadmap."}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
            <div className="pointer-events-none absolute right-3 bottom-3 w-[min(42%,440px)] rounded-lg border border-black/[0.08] bg-white/90 px-3 py-2 shadow-[0_8px_18px_-16px_rgba(0,0,0,0.55)] backdrop-blur-sm">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">
                Live sheet typing
              </p>
              <div className="mt-1.5 max-h-[132px] overflow-y-auto rounded-md border border-black/[0.06] bg-white px-2.5 py-2 text-[12px] leading-[1.5] text-[#1f1f22]">
                {sheetPreviewRows.length ? (
                  <div className="space-y-1">
                    {sheetPreviewRows.map((row, index) => (
                      <p key={`sheet-stream-${index}`} className="line-clamp-2">
                        {row}
                      </p>
                    ))}
                    <span className="inline-block h-[12px] w-[1px] animate-pulse bg-[#1f1f22]" />
                  </div>
                ) : (
                  <p>
                    {sheetStatusLine || "Writing roadmap rows to Google Sheets..."}
                    <span className="ml-1 inline-block h-[12px] w-[1px] animate-pulse bg-[#1f1f22]" />
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (isDocsScene) {
    return (
      <div className="absolute inset-0 bg-[linear-gradient(180deg,#e8eaef_0%,#dde1ea_100%)] p-3 text-[#1d1d1f]">
        <div className="h-full w-full overflow-hidden rounded-[18px] border border-black/[0.08] bg-white shadow-[0_26px_60px_-40px_rgba(0,0,0,0.55)]">
          <div className="flex items-center gap-2 border-b border-black/[0.08] px-3 py-2">
            <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#ffbd2e]" />
            <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
            <span className="ml-2 text-[12px] font-semibold tracking-tight text-[#3a3a3c]">
              Google Docs
            </span>
            {docsFrameUrl ? (
              <span className="ml-2 max-w-[65%] truncate rounded-full border border-black/[0.08] bg-[#f7f7f9] px-2.5 py-0.5 text-[10px] text-[#4c4c50]">
                {docsFrameUrl}
              </span>
            ) : null}
          </div>
          <div className="relative h-[calc(100%-42px)] bg-[#f5f6f8]">
            {docsFrameUrl ? (
              <iframe
                src={docsFrameUrl}
                title="Google Docs live preview"
                className="h-full w-full border-0 bg-white"
                sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
                referrerPolicy="no-referrer-when-downgrade"
              />
            ) : (
              <div className="h-full p-5">
                <div className="mx-auto h-full w-full max-w-[860px] rounded-xl border border-black/[0.08] bg-white px-8 py-6">
                  <p className="text-[18px] font-semibold text-[#202024]">
                    {activeTitle || "Execution Plan & Notes"}
                  </p>
                  <p className="mt-1 text-[12px] text-[#6e6e73]">
                    {sceneText || activeDetail || "Writing planning blueprint and findings to Google Docs."}
                  </p>
                  <div className="mt-4 space-y-3">
                    {docBodyPreview ? (
                      <div
                        className="[&_h1]:mb-2 [&_h1]:text-[22px] [&_h1]:font-semibold [&_h2]:mb-1.5 [&_h2]:text-[18px] [&_h2]:font-semibold [&_h3]:mb-1 [&_h3]:text-[15px] [&_h3]:font-semibold [&_p]:mb-1.5 [&_ul]:mb-1.5 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:mb-1.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_code]:rounded [&_code]:bg-[#f2f2f7] [&_code]:px-1 [&_code]:py-0.5 text-[13px] leading-[1.65] text-[#232327]"
                        dangerouslySetInnerHTML={{ __html: docBodyHtml }}
                      />
                    ) : (
                      <p className="text-[13px] text-[#4c4c50]">Preparing document...</p>
                    )}
                    <span className="inline-block h-[14px] w-[1px] animate-pulse bg-[#1f1f22]" />
                  </div>
                </div>
              </div>
            )}
            {docBodyPreview ? (
              <div className="pointer-events-none absolute right-3 bottom-3 w-[min(42%,460px)] rounded-lg border border-black/[0.08] bg-white/88 px-3 py-2 shadow-[0_8px_18px_-16px_rgba(0,0,0,0.55)] backdrop-blur-sm">
                <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">
                  Live docs typing
                </p>
                <div
                  ref={docBodyScrollRef}
                  className="mt-1.5 max-h-[124px] overflow-y-auto rounded-md border border-black/[0.06] bg-white px-2.5 py-2 text-[12px] leading-[1.55] text-[#1f1f22]"
                >
                  <div
                    className="[&_h1]:mb-2 [&_h1]:text-[17px] [&_h1]:font-semibold [&_h2]:mb-1.5 [&_h2]:text-[15px] [&_h2]:font-semibold [&_h3]:mb-1 [&_h3]:text-[13px] [&_h3]:font-semibold [&_p]:mb-1.5 [&_ul]:mb-1.5 [&_ul]:list-disc [&_ul]:pl-4 [&_ol]:mb-1.5 [&_ol]:list-decimal [&_ol]:pl-4 [&_code]:rounded [&_code]:bg-[#f2f2f7] [&_code]:px-1 [&_code]:py-0.5"
                    dangerouslySetInnerHTML={{ __html: docBodyHtml }}
                  />
                  <span className="inline-block h-[12px] w-[1px] animate-pulse bg-[#1f1f22]" />
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  if (isDocumentScene && canRenderPdfFrame) {
    return (
      <div className="absolute inset-0">
        <iframe
          src={`${stageFileUrl}#toolbar=0&navpanes=0&scrollbar=0`}
          title="Agent PDF live preview"
          className="absolute inset-0 h-full w-full bg-white"
        />
        {documentHighlights.length ? (
          <div className="pointer-events-none absolute left-3 right-3 bottom-3 rounded-xl border border-black/15 bg-white/85 px-3 py-2 text-[11px] text-[#1d1d1f] backdrop-blur-sm">
            <p className="text-[11px] font-semibold">Copied highlights</p>
            <div className="mt-1 space-y-1">
              {documentHighlights.map((item, index) => (
                <p key={`${item.word}-${index}`} className="line-clamp-2">
                  <span
                    className="rounded px-1 py-0.5 font-semibold"
                    style={{
                      backgroundColor:
                        item.color === "green"
                          ? "rgba(112, 216, 123, 0.22)"
                          : "rgba(255, 213, 79, 0.22)",
                    }}
                  >
                    {item.word || "highlight"}
                  </span>{" "}
                  {item.snippet}
                </p>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    );
  }

  if (isDocumentScene) {
    return (
      <div className="absolute inset-0 px-4 py-3 text-white/85">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[12px] font-medium">{stageFileName}</span>
          <span className="text-[10px] uppercase tracking-[0.08em] text-white/65">editing</span>
        </div>
        <p className="mb-3 text-[11px] text-white/85">
          {sceneText || activeDetail || "Preparing and updating document blocks..."}
        </p>
        {documentHighlights.length ? (
          <div className="mb-3 space-y-1.5 rounded-lg border border-white/20 bg-white/10 px-2.5 py-2">
            {documentHighlights.map((item, index) => (
              <p key={`${item.word}-inline-${index}`} className="line-clamp-2 text-[10px] text-white/90">
                <span
                  className="rounded px-1 py-0.5 font-semibold"
                  style={{
                    backgroundColor:
                      item.color === "green"
                        ? "rgba(112, 216, 123, 0.22)"
                        : "rgba(255, 213, 79, 0.22)",
                  }}
                >
                  {item.word || "highlight"}
                </span>{" "}
                {item.snippet}
              </p>
            ))}
          </div>
        ) : null}
        {clipboardPreview ? (
          <div className="mb-3 rounded-lg border border-white/20 bg-white/10 px-2.5 py-1.5 text-[10px] text-white/90">
            Clipboard: {clipboardPreview}
          </div>
        ) : null}
        <div className="space-y-2">
          <div className="h-2 w-[88%] rounded-full bg-white/15" />
          <div className="h-2 w-[74%] rounded-full bg-white/10" />
          <div className="h-2 w-[91%] rounded-full bg-white/15" />
          <div className="h-2 w-[82%] rounded-full bg-white/10" />
          <div className="h-2 w-[66%] rounded-full bg-white/15" />
        </div>
      </div>
    );
  }

  if (isSystemScene) {
    return (
      <div className="absolute inset-0 flex items-center justify-center bg-[radial-gradient(circle_at_50%_35%,rgba(255,255,255,0.08),rgba(7,9,12,0.96)_62%)] px-6">
        <div className="w-full max-w-[680px] rounded-2xl border border-white/15 bg-black/45 p-5 backdrop-blur-sm">
          <p className="text-[11px] uppercase tracking-[0.1em] text-white/60">System activity</p>
          <p className="mt-1 text-[20px] font-semibold text-white">
            {activeTitle || "Processing secure agent workflow"}
          </p>
          <p className="mt-2 text-[13px] text-white/80">
            {sceneText || activeDetail || "Finalizing run events and preparing delivery output."}
          </p>
          <div className="mt-4 space-y-2">
            <div className="h-2 w-[92%] rounded-full bg-white/25" />
            <div className="h-2 w-[86%] rounded-full bg-white/18" />
            <div className="h-2 w-[95%] rounded-full bg-white/25" />
            <div className="h-2 w-[78%] rounded-full bg-white/18" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="absolute inset-0 px-4 py-3 text-white/85">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[12px] font-medium">{stageFileName}</span>
        <span className="text-[10px] uppercase tracking-[0.08em] text-white/65">
          {isSystemScene ? "system" : "reading"}
        </span>
      </div>
      <div className="space-y-2">
        <div className="h-2 w-[88%] rounded-full bg-white/15" />
        <div className="h-2 w-[74%] rounded-full bg-white/10" />
        <div className="h-2 w-[91%] rounded-full bg-white/15" />
        <div className="h-2 w-[82%] rounded-full bg-white/10" />
        <div className="h-2 w-[66%] rounded-full bg-white/15" />
        <div className="h-2 w-[92%] rounded-full bg-white/10" />
      </div>
    </div>
  );
}
