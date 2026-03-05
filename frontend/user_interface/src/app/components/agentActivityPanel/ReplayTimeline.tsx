import type { RefObject } from "react";
import type { AgentActivityEvent } from "../../types";
import { styleForEvent } from "../agentActivityMeta";

interface ReplayTimelineProps {
  streaming: boolean;
  safeCursor: number;
  totalEvents: number;
  progressPercent: number;
  setCursor: (value: number) => void;
  setIsPlaying: (value: boolean) => void;
  activeEvent: AgentActivityEvent | null;
  sceneText: string;
  filmstripEvents: Array<{ event: AgentActivityEvent; index: number }>;
  visibleEvents: AgentActivityEvent[];
  onSelectEvent: (event: AgentActivityEvent, index: number) => void;
  listRef: RefObject<HTMLDivElement | null>;
}

function ReplayTimeline({
  streaming,
  safeCursor,
  totalEvents,
  progressPercent,
  setCursor,
  setIsPlaying,
  activeEvent,
  sceneText,
  filmstripEvents,
  visibleEvents,
  onSelectEvent,
  listRef,
}: ReplayTimelineProps) {
  const activeStyle = styleForEvent(activeEvent);
  const ActiveIcon = activeStyle.icon;
  const recentFilmstripEvents = streaming ? filmstripEvents.slice(-24) : filmstripEvents;

  return (
    <>
      {streaming ? (
        <div className="mb-3 rounded-2xl border border-black/[0.06] bg-white/85 px-3 py-2 text-[12px] text-[#4c4c50]">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium">Live timeline</span>
            <span className="text-[11px] text-[#6e6e73]">
              {totalEvents} event{totalEvents === 1 ? "" : "s"}
            </span>
          </div>
          <p className="mt-1 text-[11px] text-[#6e6e73]">
            Streaming every theatre event in real time.
          </p>
        </div>
      ) : (
        <div className="mb-3 rounded-2xl border border-black/[0.06] bg-white/85 px-3 py-2">
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-[11px] text-[#6e6e73]">
              Step {safeCursor + 1} of {totalEvents}
            </span>
            <span className="text-[11px] text-[#6e6e73]">{progressPercent}%</span>
          </div>
          <input
            type="range"
            min={0}
            max={Math.max(totalEvents - 1, 0)}
            value={safeCursor}
            onChange={(event) => {
              setCursor(Number(event.target.value));
              setIsPlaying(false);
            }}
            className="w-full accent-[#2f2f34]"
          />
        </div>
      )}

      <div className="mb-3 rounded-2xl border border-black/[0.06] bg-white/90 p-3">
        <div className="mb-1 flex items-center gap-2 text-[12px] text-[#6e6e73]">Current scene</div>
        {activeEvent ? (
          <div className="flex items-start gap-3">
            <span className="mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-full border border-black/[0.08] bg-[#f3f3f5]">
              <ActiveIcon className={`h-3.5 w-3.5 ${activeStyle.accent}`} />
            </span>
            <div className="min-w-0">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <p className="text-[14px] font-semibold text-[#1d1d1f]">{activeEvent.title}</p>
                <span className="rounded-full border border-black/[0.08] bg-[#fafafc] px-2 py-0.5 text-[10px] uppercase tracking-[0.08em] text-[#6e6e73]">
                  {activeStyle.label}
                </span>
              </div>
              <p className="text-[12px] leading-relaxed text-[#4c4c50]">
                {sceneText || activeEvent.detail || "Processing..."}
              </p>
            </div>
          </div>
        ) : null}
      </div>

      <div className="mb-2 overflow-x-auto pb-1">
        <div className="inline-flex min-w-full gap-2">
          {recentFilmstripEvents.map(({ event, index }) => {
            const isActive = index === safeCursor;
            return (
              <button
                key={`${event.event_id}-chip`}
                type="button"
                onClick={() => {
                  if (streaming) {
                    return;
                  }
                  onSelectEvent(event, index);
                }}
                className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition ${
                  isActive
                    ? "border-[#1d1d1f]/25 bg-[#1d1d1f] text-white"
                    : "border-black/[0.08] bg-white/80 text-[#4c4c50] hover:bg-white"
                }`}
              >
                <span className="font-semibold">{index + 1}</span>
                <span className="max-w-[140px] truncate">{event.title}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div
        ref={listRef}
        className={`${streaming ? "max-h-72" : "max-h-56"} space-y-1.5 overflow-y-auto pr-1`}
      >
        {visibleEvents.map((event, index) => {
          const style = styleForEvent(event);
          const Icon = style.icon;
          const isActive = index === safeCursor;
          const sequenceLabel =
            typeof event.seq === "number" && Number.isFinite(event.seq) ? `#${event.seq}` : `${index + 1}`;
          return (
            <button
              key={event.event_id || `${event.timestamp}-${index}`}
              type="button"
              data-activity-active={isActive ? "true" : "false"}
              onClick={() => {
                if (streaming) {
                  return;
                }
                onSelectEvent(event, index);
              }}
              className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                isActive ? "border-[#1d1d1f]/20 bg-white" : "border-black/[0.06] bg-white/80 hover:bg-white"
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <Icon className={`h-3.5 w-3.5 shrink-0 ${style.accent}`} />
                  <p className="truncate text-[12px] font-medium text-[#1d1d1f]">{event.title}</p>
                </div>
                <span className="shrink-0 text-[10px] text-[#86868b]">
                  {streaming ? sequenceLabel : new Date(event.timestamp).toLocaleTimeString()}
                </span>
              </div>
              {event.detail ? <p className="mt-0.5 line-clamp-2 text-[11px] text-[#6e6e73]">{event.detail}</p> : null}
            </button>
          );
        })}
      </div>
    </>
  );
}

export { ReplayTimeline };
