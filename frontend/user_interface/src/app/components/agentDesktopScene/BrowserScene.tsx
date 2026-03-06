import { highlightPalette } from "./helpers";
import { InteractionOverlay } from "./InteractionOverlay";
import type { HighlightRegion } from "./types";

type BrowserSceneProps = {
  activeDetail: string;
  activeEventType: string;
  activeTitle: string;
  action: string;
  actionPhase: string;
  actionStatus: string;
  actionTargetLabel: string;
  browserUrl: string;
  blockedSignal: boolean;
  canRenderLiveUrl: boolean;
  copyPulseText: string;
  copyPulseVisible: boolean;
  dedupedBrowserKeywords: string[];
  findMatchCount: number;
  findQuery: string;
  highlightRegions: HighlightRegion[];
  onSnapshotError?: () => void;
  providerLabel: string;
  renderQualityLabel: string;
  contentDensityLabel: string;
  sceneText: string;
  scrollDirection: string;
  scrollPercent: number | null;
  showFindOverlay: boolean;
  snapshotUrl: string;
};

function HighlightOverlay({
  highlightRegions,
  keyPrefix,
}: {
  highlightRegions: HighlightRegion[];
  keyPrefix: string;
}) {
  if (!highlightRegions.length) {
    return null;
  }
  return (
    <div className="pointer-events-none absolute inset-0">
      {highlightRegions.map((region, index) => {
        const palette = highlightPalette(region.color);
        return (
          <div
            key={`${keyPrefix}-${region.keyword}-${index}`}
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
  );
}

function FindOverlay({
  dedupedBrowserKeywords,
  findMatchCount,
  findQuery,
}: {
  dedupedBrowserKeywords: string[];
  findMatchCount: number;
  findQuery: string;
}) {
  return (
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
  );
}

function CopyPulse({ copyPulseText, copyPulseVisible }: { copyPulseText: string; copyPulseVisible: boolean }) {
  if (!copyPulseVisible) {
    return null;
  }
  return (
    <div className="pointer-events-none absolute right-4 bottom-16 z-20 transition-all duration-300">
      <div className="rounded-full border border-[#ffdc80]/70 bg-[#fff5cf]/95 px-3 py-1.5 text-[11px] font-medium text-[#3a2d0d] shadow-[0_14px_30px_-22px_rgba(0,0,0,0.65)]">
        Copied: <span className="font-semibold">{copyPulseText}</span>
      </div>
    </div>
  );
}

function SceneFooter({
  activeDetail,
  activeTitle,
  sceneText,
}: {
  activeDetail: string;
  activeTitle: string;
  sceneText: string;
}) {
  return (
    <div className="pointer-events-none absolute left-3 right-3 bottom-3 rounded-lg border border-black/10 bg-white/78 px-3 py-1.5 text-[11px] text-[#3a3a3c] backdrop-blur-sm">
      {sceneText || activeDetail || activeTitle || "Inspecting website and gathering evidence."}
    </div>
  );
}

function ScrollMeter({ scrollPercent }: { scrollPercent: number | null }) {
  if (typeof scrollPercent !== "number") {
    return null;
  }
  return (
    <div className="pointer-events-none absolute right-2 top-20 bottom-6 flex flex-col items-center">
      <div className="h-full w-1.5 rounded-full bg-black/20">
        <div
          className="w-1.5 rounded-full bg-black/60 transition-all duration-300"
          style={{ height: "24px", marginTop: `calc(${scrollPercent}% - 12px)` }}
        />
      </div>
      <span className="mt-1 text-[10px] font-medium text-black/70">{Math.round(scrollPercent)}%</span>
    </div>
  );
}

function BrowserScene({
  activeDetail,
  activeEventType,
  activeTitle,
  action,
  actionPhase,
  actionStatus,
  actionTargetLabel,
  browserUrl,
  blockedSignal,
  canRenderLiveUrl,
  copyPulseText,
  copyPulseVisible,
  dedupedBrowserKeywords,
  findMatchCount,
  findQuery,
  highlightRegions,
  onSnapshotError,
  providerLabel,
  renderQualityLabel,
  contentDensityLabel,
  sceneText,
  scrollDirection,
  scrollPercent,
  showFindOverlay,
  snapshotUrl,
}: BrowserSceneProps) {
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
        <div className="flex items-center gap-1.5 text-[10px]">
          {providerLabel ? (
            <span className="rounded-full border border-white/25 bg-white/10 px-2 py-0.5 text-white/85">
              {providerLabel}
            </span>
          ) : null}
          {renderQualityLabel ? (
            <span className="rounded-full border border-white/25 bg-white/10 px-2 py-0.5 text-white/85">
              quality: {renderQualityLabel}
            </span>
          ) : null}
          {contentDensityLabel ? (
            <span className="rounded-full border border-white/25 bg-white/10 px-2 py-0.5 text-white/85">
              density: {contentDensityLabel}
            </span>
          ) : null}
          {blockedSignal ? (
            <span className="rounded-full border border-[#ff9b6a]/60 bg-[#ff9b6a]/20 px-2 py-0.5 text-[#ffd7c2]">
              blocked
            </span>
          ) : null}
        </div>
      </div>

      {showSnapshotPrimary ? (
        <div className="relative flex-1 bg-[#0a0c10]">
          <img
            src={snapshotUrl}
            alt="Live browser capture"
            className="h-full w-full object-contain"
            onError={onSnapshotError}
          />
          <HighlightOverlay highlightRegions={highlightRegions} keyPrefix="browser-image" />
          <InteractionOverlay
            activeEventType={activeEventType}
            activeDetail={activeDetail}
            scrollDirection={scrollDirection}
            action={action}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabel}
          />
          {showFindOverlay ? (
            <FindOverlay
              dedupedBrowserKeywords={dedupedBrowserKeywords}
              findMatchCount={findMatchCount}
              findQuery={findQuery}
            />
          ) : null}
          <CopyPulse copyPulseText={copyPulseText} copyPulseVisible={copyPulseVisible} />
          <SceneFooter activeDetail={activeDetail} activeTitle={activeTitle} sceneText={sceneText} />
          <ScrollMeter scrollPercent={scrollPercent} />
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
          <HighlightOverlay highlightRegions={highlightRegions} keyPrefix="browser-iframe" />
          <InteractionOverlay
            activeEventType={activeEventType}
            activeDetail={activeDetail}
            scrollDirection={scrollDirection}
            action={action}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabel}
          />
          {showFindOverlay ? (
            <FindOverlay
              dedupedBrowserKeywords={dedupedBrowserKeywords}
              findMatchCount={findMatchCount}
              findQuery={findQuery}
            />
          ) : null}
          <CopyPulse copyPulseText={copyPulseText} copyPulseVisible={copyPulseVisible} />
          <SceneFooter activeDetail={activeDetail} activeTitle={activeTitle} sceneText={sceneText} />
          <ScrollMeter scrollPercent={scrollPercent} />
        </div>
      ) : (
        <div className="relative flex-1 space-y-3 p-4">
          <InteractionOverlay
            activeEventType={activeEventType}
            activeDetail={activeDetail}
            scrollDirection={scrollDirection}
            action={action}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabel}
          />
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
              <p className="font-semibold">
                Find: {findQuery || dedupedBrowserKeywords.slice(0, 2).join(" ")}
              </p>
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
              className="absolute bottom-3 right-3 h-24 w-36 rounded-lg border border-white/20 object-contain bg-black/25"
              onError={onSnapshotError}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}

export { BrowserScene };
