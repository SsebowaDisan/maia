import { Maximize2, Minimize2, X } from "lucide-react";
import type { ReactNode } from "react";
import type { AgentActivityEvent } from "../../types";
import { visibleTimelineEvents } from "./replayModePolicy";

interface FullscreenViewerOverlayProps {
  isOpen: boolean;
  isFocusMode: boolean;
  onToggleFocusMode: () => void;
  onClose: () => void;
  desktopViewer: ReactNode;
  visibleEvents: AgentActivityEvent[];
  activeEvent: AgentActivityEvent | null;
  sceneText: string;
  onSelectEvent: (event: AgentActivityEvent, index: number) => void;
}

function FullscreenViewerOverlay({
  isOpen,
  isFocusMode,
  onToggleFocusMode,
  onClose,
  desktopViewer,
  visibleEvents,
  activeEvent,
  sceneText,
  onSelectEvent,
}: FullscreenViewerOverlayProps) {
  const timelineEvents = visibleTimelineEvents(visibleEvents);
  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[120] bg-black/75 p-3 backdrop-blur-md md:p-6">
      <div className="mx-auto flex h-full w-full max-w-[1800px] flex-col overflow-hidden rounded-3xl border border-white/20 bg-[#090b10] p-4 shadow-2xl md:p-5">
        <div className="mb-3 flex items-center justify-between gap-3 text-white">
          <div>
            <p className="text-[11px] uppercase tracking-[0.14em] text-white/70">Agent Viewer</p>
            <p className="text-[16px] font-semibold">Fullscreen desktop</p>
            <p className="text-[11px] text-white/65">Press `Esc` to close</p>
          </div>
          <div className="inline-flex items-center gap-2">
            <button
              type="button"
              onClick={onToggleFocusMode}
              className="inline-flex items-center gap-1 rounded-xl border border-white/20 bg-white/5 px-3 py-1.5 text-[12px] text-white/85 transition hover:bg-white/10"
              title="Toggle focus mode"
            >
              <Maximize2 className="h-3.5 w-3.5" />
              {isFocusMode ? "Focus On" : "Focus Off"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex items-center gap-1 rounded-xl border border-white/20 bg-white/5 px-3 py-1.5 text-[12px] text-white/85 transition hover:bg-white/10"
              title="Exit fullscreen"
            >
              <Minimize2 className="h-3.5 w-3.5" />
              Exit
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-white/20 bg-white/5 p-2 text-white/85 transition hover:bg-white/10"
              title="Close fullscreen"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {desktopViewer}

        {!isFocusMode ? (
          <div className="mt-3 flex min-h-0 flex-1 gap-3 overflow-hidden">
            <div className="min-h-0 flex-1 overflow-y-auto rounded-2xl border border-white/10 bg-white/[0.03] p-3">
              <p className="mb-2 text-[12px] font-medium text-white/90">Current scene</p>
              <p className="text-[13px] text-white/85">{activeEvent?.title || "No active scene"}</p>
              <p className="mt-1 text-[12px] text-white/70">{sceneText || activeEvent?.detail || ""}</p>
            </div>
            <div className="min-h-0 w-[340px] overflow-y-auto rounded-2xl border border-white/10 bg-white/[0.03] p-3">
              <p className="mb-2 text-[12px] font-medium text-white/90">Live timeline</p>
              <div className="space-y-1.5">
                {timelineEvents.map((event) => {
                  const index = visibleEvents.findIndex((candidate) => candidate.event_id === event.event_id);
                  return (
                    <button
                      key={`fullscreen-row-${event.event_id || index}`}
                      type="button"
                      onClick={() => onSelectEvent(event, index)}
                      className="w-full rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-2 text-left text-white/90 transition hover:bg-white/[0.08]"
                    >
                      <p className="truncate text-[12px] font-medium">{event.title}</p>
                      {event.detail ? <p className="mt-0.5 line-clamp-2 text-[11px] text-white/70">{event.detail}</p> : null}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export { FullscreenViewerOverlay };
