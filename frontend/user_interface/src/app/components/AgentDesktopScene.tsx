import { useEffect, useRef } from "react";
import { renderRichText } from "../utils/richText";

type AgentDesktopSceneProps = {
  snapshotUrl: string;
  isBrowserScene: boolean;
  isEmailScene: boolean;
  isDocumentScene: boolean;
  isSystemScene: boolean;
  canRenderPdfFrame: boolean;
  stageFileUrl: string;
  stageFileName: string;
  browserUrl: string;
  emailRecipient: string;
  emailSubject: string;
  emailBodyHint: string;
  sceneText: string;
  activeTitle: string;
  activeDetail: string;
  activeEventType: string;
  activeSceneData: Record<string, unknown>;
  onSnapshotError?: () => void;
};

export function AgentDesktopScene({
  snapshotUrl,
  isBrowserScene,
  isEmailScene,
  isDocumentScene,
  isSystemScene,
  canRenderPdfFrame,
  stageFileUrl,
  stageFileName,
  browserUrl,
  emailRecipient,
  emailSubject,
  emailBodyHint,
  sceneText,
  activeTitle,
  activeDetail,
  activeEventType,
  activeSceneData,
  onSnapshotError,
}: AgentDesktopSceneProps) {
  const compactValue = (value: unknown): string => (typeof value === "string" ? value.trim() : "");
  const compactList = (value: unknown, limit = 12): string[] =>
    Array.isArray(value)
      ? Array.from(
          new Set(
            value
              .map((item) => String(item || "").trim())
              .filter((item) => item.length > 0),
          ),
        ).slice(0, Math.max(1, limit))
      : [];
  const compactObjectList = (value: unknown, limit = 10): Array<Record<string, unknown>> =>
    Array.isArray(value)
      ? value
          .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
          .slice(0, Math.max(1, limit))
      : [];
  const ellipsis = (value: string, limit = 56): string =>
    value.length <= limit ? value : `${value.slice(0, Math.max(1, limit - 1)).trimEnd()}...`;

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
  const keywordBadges = Array.isArray(activeSceneData["keywords"])
    ? activeSceneData["keywords"]
        .map((item) => String(item || "").trim())
        .filter((item) => item)
        .slice(0, 6)
    : [];
  const plannedSearchTerms =
    compactList(activeSceneData["planned_search_terms"], 8).length > 0
      ? compactList(activeSceneData["planned_search_terms"], 8)
      : compactList(activeSceneData["search_terms"], 8);
  const plannedKeywords = compactList(activeSceneData["planned_keywords"], 12);
  const stepIds = compactList(activeSceneData["step_ids"], 8);
  const copiedSnippets = (
    Array.isArray(activeSceneData["copied_snippets"])
      ? (activeSceneData["copied_snippets"] as unknown[])
      : []
  )
    .map((item) => {
      if (typeof item === "string") {
        return item.trim();
      }
      if (item && typeof item === "object") {
        const row = item as Record<string, unknown>;
        return compactValue(row["text"] || row["snippet"]);
      }
      return "";
    })
    .filter((item) => item.length > 0)
    .slice(0, 4);
  const highlightedWordsInline = compactObjectList(activeSceneData["highlighted_words"], 8)
    .map((item) => compactValue(item["word"]))
    .filter((item) => item.length > 0)
    .slice(0, 8);
  const workspaceStepName = compactValue(activeSceneData["step_name"]);
  const workspaceStatus = compactValue(activeSceneData["status"]);
  const documentUrl = compactValue(activeSceneData["document_url"]);
  const spreadsheetUrl = compactValue(activeSceneData["spreadsheet_url"]);
  const artifactPath = compactValue(activeSceneData["path"]);
  const pdfPath = compactValue(activeSceneData["pdf_path"]);
  const hasLiveInsights =
    plannedSearchTerms.length > 0 ||
    plannedKeywords.length > 0 ||
    stepIds.length > 0 ||
    workspaceStepName.length > 0 ||
    workspaceStatus.length > 0 ||
    documentUrl.length > 0 ||
    spreadsheetUrl.length > 0 ||
    artifactPath.length > 0 ||
    pdfPath.length > 0 ||
    copiedSnippets.length > 0 ||
    highlightedWordsInline.length > 0;

  const renderLiveInsights = (variant: "light" | "dark") => {
    if (!hasLiveInsights) {
      return null;
    }
    const frameClass =
      variant === "light"
        ? "rounded-xl border border-black/15 bg-white/88 px-3 py-2 text-[#1d1d1f] backdrop-blur-sm"
        : "rounded-xl border border-white/20 bg-black/45 px-3 py-2 text-white/90 backdrop-blur-sm";
    const mutedClass = variant === "light" ? "text-[#5a5a60]" : "text-white/70";
    const chipClass =
      variant === "light"
        ? "rounded-full border border-black/15 bg-white/80 px-1.5 py-0.5 text-[10px] text-[#1d1d1f]"
        : "rounded-full border border-white/20 bg-white/10 px-1.5 py-0.5 text-[10px] text-white/90";
    return (
      <div className={frameClass}>
        {plannedSearchTerms.length ? (
          <div className="mb-2">
            <p className={`text-[10px] uppercase tracking-[0.08em] ${mutedClass}`}>Search terms</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {plannedSearchTerms.map((term) => (
                <span key={`term-${term}`} className={chipClass}>
                  {term}
                </span>
              ))}
            </div>
          </div>
        ) : null}
        {plannedKeywords.length ? (
          <div className="mb-2">
            <p className={`text-[10px] uppercase tracking-[0.08em] ${mutedClass}`}>Keywords</p>
            <div className="mt-1 flex flex-wrap gap-1">
              {plannedKeywords.slice(0, 10).map((keyword) => (
                <span key={`keyword-${keyword}`} className={chipClass}>
                  {keyword}
                </span>
              ))}
            </div>
          </div>
        ) : null}
        {stepIds.length ? (
          <p className={`mb-2 text-[10px] ${mutedClass}`}>
            Roadmap steps: {stepIds.slice(0, 4).join(" -> ")}
          </p>
        ) : null}
        {workspaceStepName || workspaceStatus ? (
          <p className={`mb-1 text-[10px] ${mutedClass}`}>
            Tracker: {workspaceStepName || "Step update"} {workspaceStatus ? `(${workspaceStatus})` : ""}
          </p>
        ) : null}
        {spreadsheetUrl ? (
          <p className={`text-[10px] ${mutedClass}`}>Sheet: {ellipsis(spreadsheetUrl, 66)}</p>
        ) : null}
        {documentUrl ? (
          <p className={`text-[10px] ${mutedClass}`}>Doc: {ellipsis(documentUrl, 66)}</p>
        ) : null}
        {artifactPath ? (
          <p className={`text-[10px] ${mutedClass}`}>File: {ellipsis(artifactPath, 66)}</p>
        ) : null}
        {pdfPath ? (
          <p className={`text-[10px] ${mutedClass}`}>PDF: {ellipsis(pdfPath, 66)}</p>
        ) : null}
        {highlightedWordsInline.length ? (
          <p className={`mt-1 text-[10px] ${mutedClass}`}>
            Highlighted: {highlightedWordsInline.slice(0, 8).join(", ")}
          </p>
        ) : null}
        {copiedSnippets.length ? (
          <div className="mt-1.5 space-y-1">
            {copiedSnippets.map((snippet, index) => (
              <p key={`snippet-${index}`} className={`line-clamp-1 text-[10px] ${mutedClass}`}>
                Copied: {ellipsis(snippet, 90)}
              </p>
            ))}
          </div>
        ) : null}
      </div>
    );
  };
  const clipboardPreview = typeof activeSceneData["clipboard_text"] === "string"
    ? activeSceneData["clipboard_text"]
    : "";
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
            {hasLiveInsights ? (
              <div className="pointer-events-none absolute left-3 top-14 w-[min(42%,360px)]">
                {renderLiveInsights("light")}
              </div>
            ) : null}
            <div className="pointer-events-none absolute left-1/2 top-1/2 w-[min(92%,760px)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-black/10 bg-white/80 px-3 py-2 text-[#1d1d1f] backdrop-blur-sm">
              <p className="text-[12px] font-semibold">
                {activeTitle || "Live website capture"}
              </p>
              <p className="mt-0.5 line-clamp-2 text-[11px] text-[#3a3a3c]">
                {sceneText || activeDetail || "Opening and reviewing the website in real time."}
              </p>
              {keywordBadges.length ? (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {keywordBadges.map((keyword) => (
                    <span
                      key={keyword}
                      className="rounded-full border border-black/10 bg-white/70 px-2 py-0.5 text-[10px] text-[#1d1d1f]"
                    >
                      {keyword}
                    </span>
                  ))}
                </div>
              ) : null}
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
            {hasLiveInsights ? (
              <div className="pointer-events-none absolute left-3 top-14 w-[min(42%,360px)]">
                {renderLiveInsights("light")}
              </div>
            ) : null}
            <div className="pointer-events-none absolute left-1/2 top-1/2 w-[min(92%,760px)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-black/10 bg-white/80 px-3 py-2 text-[#1d1d1f] backdrop-blur-sm">
              <p className="text-[12px] font-semibold">
                {activeTitle || "Live website preview"}
              </p>
              <p className="mt-0.5 line-clamp-2 text-[11px] text-[#3a3a3c]">
                {sceneText || activeDetail || "Opening and reviewing the website in real time."}
              </p>
              {keywordBadges.length ? (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {keywordBadges.map((keyword) => (
                    <span
                      key={keyword}
                      className="rounded-full border border-black/10 bg-white/70 px-2 py-0.5 text-[10px] text-[#1d1d1f]"
                    >
                      {keyword}
                    </span>
                  ))}
                </div>
              ) : null}
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

  if (snapshotUrl) {
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
          {keywordBadges.length ? (
            <div className="mt-2 flex flex-wrap gap-1">
              {keywordBadges.map((keyword) => (
                <span
                  key={keyword}
                  className="rounded-full border border-white/25 bg-white/10 px-2 py-0.5 text-[10px] text-white/90"
                >
                  {keyword}
                </span>
              ))}
            </div>
          ) : null}
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

  if (isDocumentScene && canRenderPdfFrame) {
    return (
      <div className="absolute inset-0">
        <iframe
          src={`${stageFileUrl}#toolbar=0&navpanes=0&scrollbar=0`}
          title="Agent PDF live preview"
          className="absolute inset-0 h-full w-full bg-white"
        />
        {hasLiveInsights ? (
          <div className="pointer-events-none absolute left-3 top-3 w-[min(44%,360px)]">
            {renderLiveInsights("light")}
          </div>
        ) : null}
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
        {hasLiveInsights ? (
          <div className="mb-3">
            {renderLiveInsights("dark")}
          </div>
        ) : null}
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
          {hasLiveInsights ? (
            <div className="mt-3">
              {renderLiveInsights("dark")}
            </div>
          ) : null}
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
