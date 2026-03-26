import { useMemo, useState } from "react";
import { Circle, Loader2 } from "lucide-react";

type TodoStatus = "pending" | "active" | "done";

type TodoItem = {
  id: string;
  label: string;
  status: TodoStatus;
};

export type RoadmapStep = { toolId: string; title: string; whyThisStep: string };
export type TodoEvent = { event_id?: string; event_type?: string; title?: string };

export interface ResearchTodoListProps {
  visibleEvents: TodoEvent[];
  plannedRoadmapSteps: RoadmapStep[];
  roadmapActiveIndex: number;
  streaming: boolean;
  dark?: boolean;
}

const MAX_VISIBLE_TASK_ROWS = 6;
const RESEARCH_PREFIXES = [
  "research_",
  "web_search_",
  "plan_step_",
  "agent_step_",
  "agent_phase_",
  "analysis_",
  "synthesis_",
  "source_",
];
const DONE_SUFFIXES = ["_completed", "_done", "_finished"];

function isTrackedEvent(eventType: string): boolean {
  return RESEARCH_PREFIXES.some((prefix) => eventType.startsWith(prefix));
}

function isStartEvent(eventType: string): boolean {
  return eventType.endsWith("_started");
}

function isDoneEvent(eventType: string): boolean {
  return DONE_SUFFIXES.some((suffix) => eventType.endsWith(suffix));
}

function deriveTodoItems(
  visibleEvents: TodoEvent[],
  plannedRoadmapSteps: RoadmapStep[],
  roadmapActiveIndex: number,
): TodoItem[] {
  const items = new Map<string, TodoItem>();
  const order: string[] = [];

  if (Array.isArray(plannedRoadmapSteps) && plannedRoadmapSteps.length > 0) {
    plannedRoadmapSteps.forEach((step, i) => {
      const label = String(step.title || step.toolId || "").trim();
      if (!label) return;
      const key = `roadmap:${i}:${label}`;
      const status: TodoStatus =
        i < roadmapActiveIndex ? "done" : i === roadmapActiveIndex ? "active" : "pending";
      order.push(key);
      items.set(key, { id: key, label, status });
    });
  }

  for (const ev of visibleEvents) {
    const type = String(ev.event_type || "").trim().toLowerCase();
    if (!isTrackedEvent(type)) continue;
    const label = String(ev.title || "").trim();
    if (!label) continue;

    if (isStartEvent(type)) {
      const matchKey = order.find((k) => {
        const item = items.get(k);
        return item && item.label.toLowerCase() === label.toLowerCase();
      });
      if (matchKey) {
        items.set(matchKey, { ...items.get(matchKey)!, status: "active" });
      } else {
        const key = `event:${ev.event_id || label}`;
        if (!order.includes(key)) order.push(key);
        items.set(key, { id: String(ev.event_id || key), label, status: "active" });
      }
    } else if (isDoneEvent(type)) {
      const matchKey = order.find((k) => {
        const item = items.get(k);
        return item && item.status !== "pending" && item.label.toLowerCase() === label.toLowerCase();
      });
      if (matchKey) {
        items.set(matchKey, { ...items.get(matchKey)!, status: "done" });
      } else {
        const key = `event:done:${ev.event_id || label}`;
        if (!order.includes(key)) order.push(key);
        items.set(key, { id: String(ev.event_id || key), label, status: "done" });
      }
    }
  }

  return order.map((key) => items.get(key)!).filter(Boolean);
}

function dedupeTodoItems(items: TodoItem[]): TodoItem[] {
  const seen = new Set<string>();
  const result: TodoItem[] = [];
  for (const item of items) {
    const normalizedLabel = String(item.label || "").trim().toLowerCase().replace(/\s+/g, " ");
    if (!normalizedLabel || seen.has(normalizedLabel)) {
      continue;
    }
    seen.add(normalizedLabel);
    result.push(item);
  }
  return result;
}

export function ResearchTodoList({
  visibleEvents,
  plannedRoadmapSteps,
  roadmapActiveIndex,
  streaming,
  dark = false,
}: ResearchTodoListProps) {
  const [showAll, setShowAll] = useState(false);
  const items = useMemo(
    () => deriveTodoItems(visibleEvents, plannedRoadmapSteps, roadmapActiveIndex),
    [visibleEvents, plannedRoadmapSteps, roadmapActiveIndex],
  );
  const visibleItems = useMemo(
    () => dedupeTodoItems(items.filter((item) => item.status !== "done")),
    [items],
  );

  if (!visibleItems.length) return null;

  const openCount = visibleItems.length;
  const compactMode = openCount > MAX_VISIBLE_TASK_ROWS;
  const displayedItems = showAll ? visibleItems : visibleItems.slice(0, MAX_VISIBLE_TASK_ROWS);
  const hiddenCount = Math.max(0, openCount - displayedItems.length);

  if (dark) {
    return (
      <div className="space-y-1.5 rounded-[14px] border border-white/12 bg-[#131821] p-3">
        {displayedItems.map((item) => (
          <div key={item.id} className="flex items-start gap-2">
            {item.status === "active" ? (
              <Loader2
                className={`mt-[1px] h-3 w-3 shrink-0 text-[#6e6e73] ${streaming ? "animate-spin" : ""}`}
              />
            ) : (
              <Circle className="mt-[1px] h-3 w-3 shrink-0 text-white/20" />
            )}
            <p
              className={`text-[11px] leading-[1.35] ${
                item.status === "active" ? "font-medium text-white/90" : "text-white/25"
              }`}
            >
              {item.label}
            </p>
          </div>
        ))}
        {compactMode ? (
          <button
            type="button"
            onClick={() => setShowAll((value) => !value)}
            className="rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-[10px] font-semibold text-white/70 transition hover:bg-white/10"
          >
            {showAll ? "Show less" : `Show ${hiddenCount} more`}
          </button>
        ) : null}
        <p className="pt-1 text-[9px] tabular-nums text-white/30">{openCount} open</p>
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-2xl border border-[#e3e5e8] bg-white px-4 py-3">
      <div className="mb-2.5 flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7a7a83]">Tasks</p>
        <p className="text-[10px] tabular-nums text-[#9d9da6]">{openCount} open</p>
      </div>

      <div className="space-y-2.5">
        {displayedItems.map((item) => (
          <div key={item.id} className="flex items-start gap-2.5">
            {item.status === "active" ? (
              <Loader2
                className={`mt-[1px] h-3.5 w-3.5 shrink-0 text-[#7c3aed] ${streaming ? "animate-spin" : ""}`}
              />
            ) : (
              <Circle className="mt-[1px] h-3.5 w-3.5 shrink-0 text-[#d1d1d6]" />
            )}
            <p
              className={`text-[12px] leading-[1.35] ${
                item.status === "active" ? "font-medium text-[#1f2937]" : "text-[#9ca3af]"
              }`}
            >
              {item.label}
            </p>
          </div>
        ))}
        {compactMode ? (
          <button
            type="button"
            onClick={() => setShowAll((value) => !value)}
            className="rounded-full border border-[#d0d5dd] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#475467] hover:bg-[#f9fafb]"
          >
            {showAll ? "Show less" : `Show ${hiddenCount} more`}
          </button>
        ) : null}
      </div>
    </div>
  );
}
