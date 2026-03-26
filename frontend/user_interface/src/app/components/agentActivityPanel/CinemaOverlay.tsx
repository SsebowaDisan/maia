"use client";

import { Pause, Play } from "lucide-react";
import { useRef, useState } from "react";
import { ResearchTodoList } from "@maia/theatre";
import { DesktopViewer } from "./DesktopViewer";
import { visibleTimelineEvents } from "./replayModePolicy";
import type { AgentActivityEvent } from "../../types";

type PhaseTimelineEntry = {
  key: string;
  label: string;
  state: "active" | "completed" | "pending" | string;
  latestEventTitle?: string;
};

type CinemaOverlayProps = {
  open: boolean;
  phaseTimeline: PhaseTimelineEntry[];
  safeCursor: number;
  orderedEvents: AgentActivityEvent[];
  activeEvent: AgentActivityEvent | null;
  visibleEvents: AgentActivityEvent[];
  sharedViewerProps: React.ComponentProps<typeof DesktopViewer>;
  streaming: boolean;
  isPlaying: boolean;
  setIsPlaying: React.Dispatch<React.SetStateAction<boolean>>;
  setCursor: React.Dispatch<React.SetStateAction<number>>;
  onClose: () => void;
  plannedRoadmapSteps?: Array<{ toolId: string; title: string; whyThisStep: string }>;
  roadmapActiveIndex?: number;
};

/** Returns the event importance tier label, if worth surfacing */
function importanceBadge(ev: AgentActivityEvent): string | null {
  const tier = (ev.event_replay_importance ?? ev.replay_importance ?? "").toLowerCase();
  if (tier === "critical") return "CRIT";
  if (tier === "high") return "HIGH";
  return null;
}

/** Classify event surface from emitted metadata (not hardcoded event title words). */
function cleanToken(value: unknown): string {
  return String(value || "").trim().toLowerCase();
}

function titleFromToken(value: string): string {
  return value
    .split("_")
    .filter((item) => item.length > 0)
    .map((item) => item.slice(0, 1).toUpperCase() + item.slice(1))
    .join(" ");
}

function eventSurfaceToken(ev: AgentActivityEvent): string {
  const payload = (ev.data || ev.metadata || {}) as Record<string, unknown>;
  const sceneSurface = cleanToken(payload.scene_surface);
  if (sceneSurface) {
    return sceneSurface;
  }
  const eventFamily = cleanToken(payload.event_family);
  if (eventFamily) {
    return eventFamily;
  }
  const toolId = cleanToken(payload.tool_id);
  if (toolId.includes(".")) {
    return toolId.split(".")[0];
  }
  const eventType = cleanToken(ev.event_type);
  if (eventType.includes(".")) {
    return eventType.split(".")[0];
  }
  if (eventType.includes("_")) {
    return eventType.split("_")[0];
  }
  return eventType || "system";
}

function surfaceGroup(token: string): "website" | "file" | "platform" | "email" | "system" {
  const normalized = cleanToken(token);
  if (["website", "browser", "web"].includes(normalized)) return "website";
  if (["document", "google_docs", "google_sheets", "docs", "sheets", "drive", "pdf", "file"].includes(normalized)) {
    return "file";
  }
  if (["email", "gmail"].includes(normalized)) return "email";
  if (["api", "integration", "connector"].includes(normalized)) return "platform";
  return "system";
}

function surfaceKeyForEvent(ev: AgentActivityEvent): "website" | "file" | "platform" | "email" | "system" {
  return surfaceGroup(eventSurfaceToken(ev));
}

function eventSurfaceLabel(ev: AgentActivityEvent): string {
  const token = eventSurfaceToken(ev);
  const grouped = surfaceGroup(token);
  if (grouped === "system") {
    return titleFromToken(token || "system") || "System";
  }
  return titleFromToken(grouped);
}

function isAssemblyPlanningEvent(ev: AgentActivityEvent | null | undefined): boolean {
  const type = cleanToken(ev?.event_type);
  return type.startsWith("assembly_") || type === "workflow_saved";
}

function eventIcon(ev: AgentActivityEvent): string {
  const t = ev.event_type.toLowerCase();
  const surface = surfaceKeyForEvent(ev);
  if (surface === "platform") return "⚙";
  if (surface === "website") return "🌐";
  if (surface === "file") return "📄";
  if (surface === "email") return "✉️";
  if (t.includes("evidence") || t.includes("crystalliz")) return "💎";
  if (t.includes("plan") || t.includes("task")) return "🗂";
  if (t.includes("approval") || t.includes("gate")) return "⛔";
  if (t.includes("trust") || t.includes("verif")) return "✅";
  if (t.includes("search")) return "🔍";
  return "·";
}

/** Compute live stats from visible events */
function computeStats(events: AgentActivityEvent[]): { sources: number; evidence: number; platforms: number } {
  let sources = 0;
  let evidence = 0;
  let platforms = 0;
  for (const ev of events) {
    const t = ev.event_type.toLowerCase();
    const surface = surfaceKeyForEvent(ev);
    if (surface === "platform") {
      platforms += 1;
    }
    if (
      t.includes("navigate") ||
      t.includes("web_result_opened") ||
      t.includes("doc_open") ||
      t.includes("browser_load") ||
      t.includes("page_open") ||
      t.startsWith("docs.") ||
      t.startsWith("sheets.") ||
      t.startsWith("drive.")
    ) {
      sources += 1;
    }
    if (
      t.includes("evidence_crystalliz") ||
      t.includes("pdf_evidence") ||
      t.includes("evidence_found") ||
      t.includes("evidence_linked")
    ) {
      evidence += 1;
    }
  }
  return { sources, evidence, platforms };
}

function CinemaOverlay({
  open,
  phaseTimeline,
  safeCursor,
  orderedEvents,
  activeEvent,
  visibleEvents,
  sharedViewerProps,
  streaming,
  isPlaying,
  setIsPlaying,
  setCursor,
  onClose,
  plannedRoadmapSteps = [],
  roadmapActiveIndex = 0,
}: CinemaOverlayProps) {
  const timelineEvents = visibleTimelineEvents(visibleEvents);
  // Custom scrubber
  const scrubRef = useRef<HTMLDivElement>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const total = orderedEvents.length;
  const progressFraction = total > 1 ? safeCursor / (total - 1) : 0;

  function handleScrubberMove(e: React.MouseEvent) {
    if (!scrubRef.current) return;
    const rect = scrubRef.current.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    setHoverIndex(Math.round(frac * Math.max(total - 1, 0)));
  }

  function handleScrubberClick(e: React.MouseEvent) {
    if (!scrubRef.current || streaming) return;
    const rect = scrubRef.current.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const idx = Math.round(frac * Math.max(total - 1, 0));
    setCursor(idx);
    setIsPlaying(false);
  }

  const hoverEvent = hoverIndex != null ? (orderedEvents[hoverIndex] ?? null) : null;
  const stats = computeStats(visibleEvents);
  const executionStarted = visibleEvents.some(
    (event) => cleanToken(event.event_type) === "execution_starting",
  );
  const planningFocus =
    isAssemblyPlanningEvent(activeEvent) &&
    !executionStarted &&
    plannedRoadmapSteps.length > 0;

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex flex-col bg-[#0d1118]">
      <div className="flex min-h-0 flex-1 gap-0">

        {/* Left: Research Phases */}
        <div className="flex w-[240px] shrink-0 flex-col gap-3 overflow-y-auto border-r border-white/[0.08] p-4">
          <p className="text-[10px] uppercase tracking-widest text-white/50">Research Phases</p>
          {phaseTimeline.map((phase) => (
            <div key={phase.key} className="flex items-start gap-2">
              <span className={`mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full ${
                phase.state === "active"
                  ? "animate-pulse bg-white"
                  : phase.state === "completed"
                    ? "bg-white/40"
                    : "bg-white/15"
              }`} />
              <div className="min-w-0 space-y-0.5">
                <p className={`text-[11px] font-semibold leading-tight ${
                  phase.state === "active"
                    ? "text-white"
                    : phase.state === "completed"
                      ? "text-white/60"
                      : "text-white/25"
                }`}>{phase.label}</p>
                {phase.latestEventTitle && phase.state !== "pending" ? (
                  <p className="truncate text-[10px] text-white/35">{phase.latestEventTitle}</p>
                ) : null}
              </div>
            </div>
          ))}
          {/* Research todo list rendered dark for the cinema background */}
          {!planningFocus && (plannedRoadmapSteps.length > 0 || visibleEvents.length > 0) ? (
            <div className="mt-2 border-t border-white/[0.08] pt-3">
              <p className="mb-2 text-[10px] uppercase tracking-widest text-white/50">Tasks</p>
              <ResearchTodoList
                visibleEvents={visibleEvents}
                plannedRoadmapSteps={plannedRoadmapSteps}
                roadmapActiveIndex={roadmapActiveIndex}
                streaming={streaming}
                dark
              />
            </div>
          ) : null}

          <div className="mt-auto space-y-1 border-t border-white/[0.08] pt-3">
            <p className="text-[10px] text-white/40">Step {safeCursor + 1} / {total}</p>
            <p className="text-[11px] font-medium text-white/70">
              {activeEvent?.title ?? "Waiting..."}
            </p>
          </div>
        </div>

        {/* Center: DesktopViewer */}
        <div className="relative min-h-0 flex-1">
          <DesktopViewer
            {...sharedViewerProps}
            fullscreen
            onToggleTheaterView={sharedViewerProps.onToggleTheaterView}
            onToggleFocusMode={sharedViewerProps.onToggleFocusMode}
            onOpenFullscreen={() => {}}
          />
        </div>

        {/* Right: Evidence Trail */}
        <div className="flex w-[260px] shrink-0 flex-col gap-2 overflow-y-auto border-l border-white/[0.08] p-4">
          {/* Live stats row */}
          <div className="flex items-center justify-between">
            <p className="text-[10px] uppercase tracking-widest text-white/50">Evidence Trail</p>
            {streaming ? (
              <span className="inline-flex items-center gap-1">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/60" />
                <span className="text-[9px] text-white/40">Running</span>
              </span>
            ) : null}
          </div>
          {(stats.sources > 0 || stats.evidence > 0 || stats.platforms > 0) ? (
            <div className="flex gap-2 rounded-lg border border-white/[0.08] bg-white/[0.04] px-2.5 py-1.5">
              {stats.sources > 0 ? (
                <span className="text-[10px] text-white/55">
                  <span className="font-semibold text-white/80">{stats.sources}</span> pages
                </span>
              ) : null}
              {(stats.sources > 0 && stats.evidence > 0) || (stats.sources > 0 && stats.platforms > 0) ? (
                <span className="text-white/20">.</span>
              ) : null}
              {stats.evidence > 0 ? (
                <span className="text-[10px] text-white/55">
                  <span className="font-semibold text-[#ffd700]/90">{stats.evidence}</span> evidence
                </span>
              ) : null}
              {stats.evidence > 0 && stats.platforms > 0 ? (
                <span className="text-white/20">.</span>
              ) : null}
              {stats.platforms > 0 ? (
                <span className="text-[10px] text-white/55">
                  <span className="font-semibold text-[#9dd6ff]">{stats.platforms}</span> platforms
                </span>
              ) : null}
            </div>
          ) : null}

          {/* Event list */}
          <div className="space-y-1">
            {timelineEvents.map((ev) => {
              const eventIndex = visibleEvents.findIndex((candidate) => candidate.event_id === ev.event_id);
              const isActive = eventIndex === safeCursor;
              const badge = importanceBadge(ev);
              const icon = eventIcon(ev);
              const surfaceLabel = eventSurfaceLabel(ev);
              return (
                <button
                  key={ev.event_id || eventIndex}
                  type="button"
                  onClick={() => {
                    if (streaming) return;
                    setCursor(eventIndex);
                    setIsPlaying(false);
                  }}
                  className={`group w-full rounded-lg px-2.5 py-1.5 text-left transition ${
                    isActive
                      ? "bg-white/15 text-white"
                      : streaming
                        ? "cursor-default text-white/30"
                        : "text-white/50 hover:bg-white/10 hover:text-white/80"
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="shrink-0 text-[11px] leading-none">{icon}</span>
                    <p className="min-w-0 flex-1 truncate text-[10px] font-medium leading-tight">{ev.title}</p>
                    <span className="shrink-0 rounded border border-white/15 px-1 py-px text-[8px] font-semibold uppercase text-white/55">
                      {surfaceLabel}
                    </span>
                    {badge ? (
                      <span className={`shrink-0 rounded px-1 py-px text-[8px] font-bold uppercase leading-none ${
                        badge === "CRIT"
                          ? "bg-red-500/30 text-red-300"
                          : "bg-amber-500/25 text-amber-300"
                      }`}>
                        {badge}
                      </span>
                    ) : null}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Bottom: Custom scrubber + controls */}
      <div className="flex shrink-0 items-center gap-3 border-t border-white/[0.08] bg-[#0d1118]/90 px-4 py-3 backdrop-blur">
        <button
          type="button"
          onClick={() => setIsPlaying((prev) => !prev)}
          disabled={streaming}
          className="rounded-lg p-1.5 text-white/70 hover:bg-white/10 disabled:opacity-40"
        >
          {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </button>

        {/* Custom scrubber track */}
        <div
          ref={scrubRef}
          className="relative flex flex-1 cursor-pointer items-center py-2"
          onMouseMove={handleScrubberMove}
          onMouseLeave={() => setHoverIndex(null)}
          onClick={handleScrubberClick}
        >
          {/* Track background */}
          <div className="relative h-[3px] w-full rounded-full bg-white/15">
            {/* Progress fill */}
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-white/65 transition-[width] duration-150"
              style={{ width: `${progressFraction * 100}%` }}
            />
            {/* Thumb only shown on hover */}
            {!streaming ? (
              <div
                className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow-sm transition-[left] duration-150"
                style={{ left: `${progressFraction * 100}%` }}
              />
            ) : null}
            {/* Tick marks for manageable event sets */}
            {total <= 80 ? orderedEvents.map((_, i) => (
              <div
                key={i}
                className="absolute top-1/2 h-[5px] w-px -translate-y-1/2 bg-white/20"
                style={{ left: `${(i / Math.max(total - 1, 1)) * 100}%` }}
              />
            )) : null}
          </div>

          {/* Hover preview tooltip */}
          {hoverEvent && !streaming ? (
            <div
              className="pointer-events-none absolute bottom-full mb-3 z-20 -translate-x-1/2"
              style={{
                left: `${hoverIndex != null && total > 1 ? (hoverIndex / (total - 1)) * 100 : 0}%`,
              }}
            >
              <div className="w-[130px] overflow-hidden rounded-xl border border-white/15 bg-[#16192280] shadow-xl backdrop-blur-sm">
                {hoverEvent.snapshot_ref ? (
                  <img
                    src={hoverEvent.snapshot_ref}
                    alt=""
                    className="h-[72px] w-full object-cover"
                  />
                ) : (
                  <div className="flex h-[72px] w-full items-center justify-center bg-white/[0.04]">
                    <span className="text-[22px] opacity-60">{eventIcon(hoverEvent)}</span>
                  </div>
                )}
                <div className="border-t border-white/[0.08] px-2 py-1.5">
                  <p className="truncate text-center text-[9px] text-white/70">{hoverEvent.title}</p>
                  <p className="mt-px text-center text-[8px] text-white/35">
                    Step {(hoverIndex ?? 0) + 1}/{total}
                  </p>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <span className="shrink-0 text-[11px] tabular-nums text-white/50">
          {safeCursor + 1}/{total}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg px-2.5 py-1.5 text-[11px] text-white/50 hover:bg-white/10 hover:text-white/80"
        >
          Esc
        </button>
      </div>
    </div>
  );
}

export { CinemaOverlay };
