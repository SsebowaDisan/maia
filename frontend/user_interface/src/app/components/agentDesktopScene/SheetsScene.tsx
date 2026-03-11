import { ClickRipple } from "./ClickRipple";
import type { ClickRippleEntry } from "./ClickRipple";
import { GhostCursor } from "./GhostCursor";
import { InteractionOverlay } from "./InteractionOverlay";
import type { ZoomHistoryEntry } from "./types";

type SheetsSceneProps = {
  activeDetail: string;
  activeEventType: string;
  action: string;
  actionPhase: string;
  actionStatus: string;
  actionTargetLabel: string;
  sceneText: string;
  scrollDirection: string;
  scrollPercent: number | null;
  sheetPreviewRows: string[];
  sheetStatusLine: string;
  sheetsFrameUrl: string;
  zoomHistory: ZoomHistoryEntry[];
  compareLeft: string;
  compareRight: string;
  compareVerdict: string;
  verifierConflict: boolean;
  verifierConflictReason: string;
  verifierRecheckRequired: boolean;
  zoomEscalationRequested: boolean;
  cursorX?: number | null;
  cursorY?: number | null;
  isClickEvent?: boolean;
  clickRipples?: ClickRippleEntry[];
};

function zoomActionLabel(action: ZoomHistoryEntry["action"]): string {
  if (action === "zoom_in") {
    return "Zoom in";
  }
  if (action === "zoom_out") {
    return "Zoom out";
  }
  if (action === "zoom_reset") {
    return "Reset";
  }
  return "Focus";
}

function SheetsScene({
  activeDetail,
  activeEventType,
  action,
  actionPhase,
  actionStatus,
  actionTargetLabel,
  sceneText,
  scrollDirection,
  scrollPercent,
  sheetPreviewRows,
  sheetStatusLine,
  sheetsFrameUrl,
  zoomHistory,
  compareLeft,
  compareRight,
  compareVerdict,
  verifierConflict,
  verifierConflictReason,
  verifierRecheckRequired,
  zoomEscalationRequested,
  cursorX = null,
  cursorY = null,
  isClickEvent = false,
  clickRipples = [],
}: SheetsSceneProps) {
  const normalizedEventType = String(activeEventType || "").trim().toLowerCase();
  const isTypingAction = action === "type";
  const typingPulse = isTypingAction && (actionPhase === "start" || actionPhase === "active");
  const sheetWriteEvent =
    normalizedEventType === "sheet_cell_update" ||
    normalizedEventType === "sheet_append_row" ||
    normalizedEventType === "sheets.append_started";
  const showLiveTypingPanel = !sheetsFrameUrl || isTypingAction || sheetWriteEvent;
  const livePanelTitle = typingPulse ? "Live sheet typing" : "Recent sheet activity";
  const activeRowIndex = sheetPreviewRows.length ? Math.max(0, sheetPreviewRows.length - 1) : -1;
  const sheetsViewportOffsetPx =
    typeof scrollPercent === "number"
      ? Math.max(-12, Math.min(12, (50 - scrollPercent) * 0.26))
      : 0;
  return (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_8%,rgba(168,216,255,0.92),rgba(122,176,244,0.72)_40%,rgba(98,148,232,0.9)_100%)] p-9 text-[#1d1d1f]">
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
        <div className="relative h-[calc(100%-42px)] bg-[#f3f3f5]">
          <InteractionOverlay
            sceneSurface="google_sheets"
            activeEventType={activeEventType}
            activeDetail={activeDetail}
            scrollDirection={scrollDirection}
            action={action}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabel}
          />
          {verifierConflict ? (
            <div className="pointer-events-none absolute left-3 top-3 z-10 w-[min(42%,360px)] rounded-lg border border-[#f2b05b]/45 bg-[#fff5e9]/94 px-2.5 py-2 text-[10px] text-[#7a430a]">
              <p className="font-semibold uppercase tracking-[0.08em]">Verifier conflict</p>
              <p className="mt-0.5 line-clamp-2">
                {verifierConflictReason || "Conflicting evidence detected during verification."}
              </p>
              <p className="mt-0.5 text-[#8a5d1a]">
                {verifierRecheckRequired ? "Re-check required" : ""}
                {verifierRecheckRequired && zoomEscalationRequested ? "  -  " : ""}
                {zoomEscalationRequested ? "Zoom escalation requested" : ""}
              </p>
            </div>
          ) : null}
          {sheetsFrameUrl ? (
            <iframe
              src={sheetsFrameUrl}
              title="Google Sheets live preview"
              className="h-full w-full border-0 bg-white"
              style={{
                transform: `translate3d(0, ${sheetsViewportOffsetPx}px, 0)`,
                transition: "transform 220ms ease-out",
              }}
              sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
              referrerPolicy="no-referrer-when-downgrade"
            />
          ) : (
            <div className="h-full p-5">
              <div
                className="mx-auto h-full w-[96%] max-w-[1120px] rounded-xl border border-black/[0.08] bg-white"
                style={{
                  transform: `translate3d(0, ${sheetsViewportOffsetPx}px, 0)`,
                  transition: "transform 220ms ease-out",
                }}
              >
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
                        className={`grid grid-cols-[120px_repeat(4,minmax(0,1fr))] border-b text-[12px] text-[#2a2a2d] ${
                          rowIndex === activeRowIndex && typingPulse
                            ? "border-black/20 bg-black/[0.03]"
                            : "border-black/[0.05]"
                        }`}
                      >
                        <div className="border-r border-black/[0.05] px-3 py-2 text-[#6e6e73]">
                          {rowIndex + 1}
                        </div>
                        <div className="col-span-4 px-3 py-2 font-medium">{row}</div>
                      </div>
                    ))
                  ) : (
                    <div className="px-3 py-3 text-[12px] text-[#4c4c50]">
                      {sceneText ||
                        activeDetail ||
                        "Preparing Google Sheets tracker and writing execution roadmap."}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
          {showLiveTypingPanel ? (
            <div className="pointer-events-none absolute right-3 bottom-3 z-10 w-[min(42%,440px)] rounded-lg border border-black/[0.08] bg-white/90 px-3 py-2 shadow-[0_8px_18px_-16px_rgba(0,0,0,0.55)] backdrop-blur-sm">
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">
                {livePanelTitle}
              </p>
              <div className="mt-1.5 max-h-[132px] overflow-y-auto rounded-md border border-black/[0.06] bg-white px-2.5 py-2 text-[12px] leading-[1.5] text-[#1f1f22]">
                {sheetPreviewRows.length ? (
                  <div className="space-y-1">
                    {sheetPreviewRows.map((row, index) => (
                      <p key={`sheet-stream-${index}`} className="line-clamp-2">
                        {row}
                      </p>
                    ))}
                    {typingPulse ? (
                      <span className="inline-block h-[12px] w-[1px] animate-pulse bg-[#1f1f22]" />
                    ) : null}
                  </div>
                ) : (
                  <p>
                    {sheetStatusLine || "Writing roadmap rows to Google Sheets..."}
                    {typingPulse ? (
                      <span className="ml-1 inline-block h-[12px] w-[1px] animate-pulse bg-[#1f1f22]" />
                    ) : null}
                  </p>
                )}
              </div>
            </div>
          ) : null}
          {zoomHistory.length ? (
            <div className="pointer-events-none absolute left-3 top-16 z-10 w-[min(44%,360px)] rounded-lg border border-black/[0.08] bg-white/90 px-2.5 py-2 text-[10px] text-[#2a2a2d] shadow-[0_8px_18px_-16px_rgba(0,0,0,0.55)] backdrop-blur-sm">
              <p className="font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">Zoom history</p>
              <div className="mt-1.5 space-y-1">
                {zoomHistory.slice(-3).reverse().map((item) => (
                  <div
                    key={`sheet-zoom-history-${item.eventRef || item.timestamp}`}
                    className="rounded-md border border-black/[0.06] bg-white px-2 py-1"
                  >
                    <p className="font-semibold">
                      {zoomActionLabel(item.action)}
                      {item.zoomLevel !== null ? ` ${Math.round(item.zoomLevel * 100)}%` : ""}
                      {item.eventIndex !== null ? `  #${item.eventIndex}` : ""}
                    </p>
                    {item.zoomReason ? <p className="line-clamp-1 text-[#4c4c50]">{item.zoomReason}</p> : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {compareLeft && compareRight ? (
            <div className="pointer-events-none absolute left-3 bottom-3 z-10 w-[min(44%,420px)] rounded-lg border border-black/[0.08] bg-white/90 px-2.5 py-2 text-[10px] text-[#2a2a2d] shadow-[0_8px_18px_-16px_rgba(0,0,0,0.55)] backdrop-blur-sm">
              <p className="font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">Compare</p>
              <div className="mt-1 grid grid-cols-2 gap-1.5">
                <p className="line-clamp-3 rounded-md border border-black/[0.06] bg-white px-2 py-1">{compareLeft}</p>
                <p className="line-clamp-3 rounded-md border border-black/[0.06] bg-white px-2 py-1">{compareRight}</p>
              </div>
              {compareVerdict ? <p className="mt-1 line-clamp-2 text-[#4c4c50]">{compareVerdict}</p> : null}
            </div>
          ) : null}
          {typeof scrollPercent === "number" ? (
            <div className="pointer-events-none absolute right-2 top-16 bottom-4 flex flex-col items-center">
              <div className="h-full w-1.5 rounded-full bg-black/15">
                <div
                  className="w-1.5 rounded-full bg-black/45 transition-all duration-300"
                  style={{ height: "20px", marginTop: `calc(${scrollPercent}% - 10px)` }}
                />
              </div>
            </div>
          ) : null}
          <GhostCursor cursorX={cursorX} cursorY={cursorY} isClick={isClickEvent} />
          <ClickRipple ripples={clickRipples} />
        </div>
      </div>
    </div>
  );
}

export { SheetsScene };
