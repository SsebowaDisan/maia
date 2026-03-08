import { useEffect, useRef, useState, type RefObject } from "react";
import type { AgentActivityEvent } from "../../types";
import { styleForEvent } from "../agentActivityMeta";
import { filmstripRowsForMode, readReplayMode, timelineRowsForMode } from "./replayModePolicy";
import { useWorkGraphStore } from "../workGraph/useWorkGraphStore";
import {
  deriveActiveNodeIdsForEvent,
  findTimelineIndexForJumpTarget,
  readActivityEventIndex,
  subscribeWorkGraphJumpTarget,
} from "../workGraph/theatreSync";

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

function replayImportance(event: AgentActivityEvent): string {
  const direct = String(event.replay_importance || event.event_replay_importance || "").trim().toLowerCase();
  if (direct) {
    return direct;
  }
  const payload = (event.data || event.metadata || {}) as Record<string, unknown>;
  return String(payload.replay_importance || payload.event_replay_importance || "").trim().toLowerCase();
}

function replayImportanceBadge(importance: string): { label: string; className: string } | null {
  if (importance === "critical") {
    return { label: "Critical", className: "border-[#d64c4c]/40 bg-[#fff0f0] text-[#9a1f1f]" };
  }
  if (importance === "high") {
    return { label: "High", className: "border-[#d8912b]/35 bg-[#fff8eb] text-[#8a5610]" };
  }
  return null;
}

function zoomSummary(event: AgentActivityEvent): string {
  const payload = (event.data || event.metadata || {}) as Record<string, unknown>;
  const zoomEvent =
    payload.zoom_event && typeof payload.zoom_event === "object"
      ? (payload.zoom_event as Record<string, unknown>)
      : null;
  const action = String(zoomEvent?.action || payload.action || "").trim().toLowerCase();
  if (!["zoom_in", "zoom_out", "zoom_reset", "zoom_to_region"].includes(action)) {
    return "";
  }
  const zoomLevelRaw = Number(zoomEvent?.zoom_level ?? payload.zoom_level);
  const zoomLevelLabel = Number.isFinite(zoomLevelRaw) && zoomLevelRaw > 0 ? `${Math.round(zoomLevelRaw * 100)}%` : "";
  const reason = String(zoomEvent?.zoom_reason || payload.zoom_reason || "").trim();
  if (!zoomLevelLabel && !reason) {
    return "Zoom action";
  }
  if (zoomLevelLabel && reason) {
    return `${zoomLevelLabel} - ${reason}`;
  }
  return zoomLevelLabel || reason;
}

function copyProvenanceSummary(event: AgentActivityEvent): string {
  const payload = (event.data || event.metadata || {}) as Record<string, unknown>;
  const copyRole = String(payload.copy_role || "").trim().toLowerCase();
  const copyProvenance =
    payload.copy_provenance && typeof payload.copy_provenance === "object"
      ? (payload.copy_provenance as Record<string, unknown>)
      : null;
  const copyUsageRefs = Array.isArray(payload.copy_usage_refs)
    ? payload.copy_usage_refs.map((item) => String(item || "").trim()).filter((item) => item.length > 0)
    : [];
  if (copyRole === "source") {
    const snippet = String(copyProvenance?.snippet || payload.clipboard_text || "").trim();
    return snippet ? `Copied source: ${snippet.slice(0, 88)}` : "Copied source captured";
  }
  if (copyRole === "usage" || copyUsageRefs.length) {
    const refs = copyUsageRefs.length
      ? copyUsageRefs.slice(0, 2)
      : [String(copyProvenance?.copy_event_ref || "").trim()].filter((item) => item.length > 0);
    if (!refs.length) {
      return "Uses copied source evidence";
    }
    return `Uses copied source ${refs.join(", ")}`;
  }
  return "";
}

function verifierConflictSummary(event: AgentActivityEvent): string {
  const payload = (event.data || event.metadata || {}) as Record<string, unknown>;
  const conflict = Boolean(payload.verifier_conflict);
  if (!conflict) {
    return "";
  }
  const reason = String(payload.verifier_conflict_reason || "").trim();
  const recheck = Boolean(payload.verifier_recheck_required);
  const zoomEscalation = Boolean(payload.zoom_escalation_requested);
  const tail =
    recheck || zoomEscalation
      ? ` (${[recheck ? "re-check" : "", zoomEscalation ? "zoom escalation" : ""]
          .filter((item) => item.length > 0)
          .join(", ")})`
      : "";
  return `${reason || "Verifier conflict detected"}${tail}`;
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
  useEffect(() => {
    const unsubscribe = subscribeWorkGraphJumpTarget((jumpTarget) => {
      let nextIndex = -1;
      if (typeof jumpTarget.eventIndexStart === "number" && jumpTarget.eventIndexStart > 0) {
        nextIndex = Math.max(0, Math.min(totalEvents - 1, Math.round(jumpTarget.eventIndexStart) - 1));
      } else {
        nextIndex = findTimelineIndexForJumpTarget(visibleEvents, jumpTarget);
      }
      if (nextIndex < 0) {
        return;
      }
      setCursor(nextIndex);
      setIsPlaying(false);
    });
    return () => unsubscribe();
  }, [setCursor, setIsPlaying, totalEvents, visibleEvents]);

  useEffect(() => {
    if (!activeEvent) {
      useWorkGraphStore.setState({ activeNodeIds: [] });
      return;
    }
    const graphState = useWorkGraphStore.getState();
    if (!graphState.nodes.length) {
      return;
    }
    const activeNodeIds = deriveActiveNodeIdsForEvent(graphState.nodes, activeEvent);
    const eventIndex = readActivityEventIndex(activeEvent);
    useWorkGraphStore.setState((state) => ({
      activeNodeIds,
      replayCursor: eventIndex > 0 ? eventIndex : state.replayCursor,
    }));
  }, [activeEvent?.event_id, activeEvent?.event_index, safeCursor]);

  // T2: Timeline Scrub Preview
  const scrubTrackRef = useRef<HTMLDivElement>(null);
  const [scrubHover, setScrubHover] = useState<{ index: number; x: number } | null>(null);

  const scrubEventAt = (clientX: number): number | null => {
    const track = scrubTrackRef.current;
    if (!track || totalEvents < 2) return null;
    const rect = track.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return Math.round(ratio * (totalEvents - 1));
  };

  const activeStyle = styleForEvent(activeEvent);
  const ActiveIcon = activeStyle.icon;
  const replayMode = readReplayMode(visibleEvents);
  const baseFilmstripEvents = streaming ? filmstripEvents.slice(-24) : filmstripEvents;
  const recentFilmstripEvents = filmstripRowsForMode({
    filmstripRows: baseFilmstripEvents,
    safeCursor,
    replayMode,
  });
  const timelineRows = timelineRowsForMode({
    visibleEvents,
    safeCursor,
    replayMode,
  });

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
            <span className="text-[11px] text-[#6e6e73]">
              {progressPercent}% {replayMode === "fast" ? "- compressed" : replayMode === "full_theatre" ? "- full" : ""}
            </span>
          </div>
          <div
            ref={scrubTrackRef}
            className="relative"
            onMouseMove={(e) => {
              const idx = scrubEventAt(e.clientX);
              if (idx !== null) setScrubHover({ index: idx, x: e.clientX });
            }}
            onMouseLeave={() => setScrubHover(null)}
          >
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
            {scrubHover !== null && (() => {
              const hoverEvent = visibleEvents[scrubHover.index] ?? null;
              const payload = ((hoverEvent?.data ?? hoverEvent?.metadata) ?? {}) as Record<string, unknown>;
              const snapshotUrl =
                String(payload.snapshot_url ?? payload.snapshot_ref ?? "").trim() || null;
              const track = scrubTrackRef.current;
              const rect = track?.getBoundingClientRect();
              const leftPx = rect ? scrubHover.x - rect.left : 0;
              return (
                <div
                  className="pointer-events-none absolute bottom-8 z-50 -translate-x-1/2 rounded-xl border border-black/[0.1] bg-white shadow-lg"
                  style={{ left: leftPx }}
                >
                  {snapshotUrl ? (
                    <img
                      src={snapshotUrl}
                      alt="preview"
                      className="h-20 w-32 rounded-t-xl object-cover"
                    />
                  ) : null}
                  <div className="px-2 py-1">
                    <p className="max-w-[128px] truncate text-[10px] font-medium text-[#1d1d1f]">
                      {hoverEvent?.title ?? `Event ${scrubHover.index + 1}`}
                    </p>
                    <p className="text-[9px] text-[#86868b]">
                      {scrubHover.index + 1} / {totalEvents}
                    </p>
                  </div>
                </div>
              );
            })()}
          </div>
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
            const sequence =
              Number(event.event_index) > 0
                ? Number(event.event_index)
                : typeof event.seq === "number" && Number.isFinite(event.seq)
                  ? Number(event.seq)
                  : index + 1;
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
                <span className="font-semibold">{sequence}</span>
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
        {timelineRows.map(({ event, index }) => {
          const style = styleForEvent(event);
          const Icon = style.icon;
          const isActive = index === safeCursor;
          const importance = replayImportance(event);
          const importanceBadge = replayImportanceBadge(importance);
          const eventIndexFromPayload = Number(event.event_index);
          const zoomDetail = zoomSummary(event);
          const copyDetail = copyProvenanceSummary(event);
          const verifierDetail = verifierConflictSummary(event);
          const payloadEventIndex =
            Number.isFinite(eventIndexFromPayload) && eventIndexFromPayload > 0
              ? eventIndexFromPayload
              : Number((event.data as Record<string, unknown> | undefined)?.event_index || 0);
          const sequenceLabel =
            Number.isFinite(payloadEventIndex) && payloadEventIndex > 0
              ? `#${Math.round(payloadEventIndex)}`
              : typeof event.seq === "number" && Number.isFinite(event.seq)
                ? `#${event.seq}`
                : `${index + 1}`;
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
                  {importanceBadge ? (
                    <span
                      className={`rounded-full border px-1.5 py-0.5 text-[9px] uppercase tracking-[0.06em] ${importanceBadge.className}`}
                    >
                      {importanceBadge.label}
                    </span>
                  ) : null}
                </div>
                <span className="shrink-0 text-[10px] text-[#86868b]">
                  {streaming ? sequenceLabel : new Date(event.timestamp).toLocaleTimeString()}
                </span>
              </div>
              {event.detail ? <p className="mt-0.5 line-clamp-2 text-[11px] text-[#6e6e73]">{event.detail}</p> : null}
              {zoomDetail ? (
                <p className="mt-0.5 line-clamp-1 text-[10px] font-medium text-[#365f9c]">{zoomDetail}</p>
              ) : null}
              {copyDetail ? (
                <p className="mt-0.5 line-clamp-1 text-[10px] font-medium text-[#7d4f16]">{copyDetail}</p>
              ) : null}
              {verifierDetail ? (
                <p className="mt-0.5 line-clamp-1 text-[10px] font-medium text-[#a14913]">{verifierDetail}</p>
              ) : null}
            </button>
          );
        })}
      </div>
    </>
  );
}

export { ReplayTimeline };
