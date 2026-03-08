import { CheckCircle2, Circle, Loader2 } from "lucide-react";
import type { AgentActivityEvent } from "../../types";

type TodoStatus = "pending" | "active" | "done";

type TodoItem = {
  id: string;
  label: string;
  status: TodoStatus;
};

type RoadmapStep = { toolId: string; title: string; whyThisStep: string };

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
  visibleEvents: AgentActivityEvent[],
  plannedRoadmapSteps: RoadmapStep[],
  roadmapActiveIndex: number,
): TodoItem[] {
  // Build from roadmap steps first (gives us ordering + pending states)
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

  // Overlay with live events (research branches, web search, etc.)
  for (const ev of visibleEvents) {
    const type = ev.event_type;
    if (!isTrackedEvent(type)) continue;
    const label = String(ev.title || "").trim();
    if (!label) continue;

    if (isStartEvent(type)) {
      // Try to find a matching roadmap step by label
      const matchKey = order.find((k) => {
        const item = items.get(k);
        return item && item.label.toLowerCase() === label.toLowerCase();
      });
      if (matchKey) {
        items.set(matchKey, { ...items.get(matchKey)!, status: "active" });
      } else {
        const key = `event:${ev.event_id || label}`;
        if (!order.includes(key)) order.push(key);
        items.set(key, { id: ev.event_id || key, label, status: "active" });
      }
    } else if (isDoneEvent(type)) {
      // Match to an active item by label
      const matchKey = order.find((k) => {
        const item = items.get(k);
        return (
          item &&
          item.status !== "pending" &&
          item.label.toLowerCase() === label.toLowerCase()
        );
      });
      if (matchKey) {
        items.set(matchKey, { ...items.get(matchKey)!, status: "done" });
      } else {
        const key = `event:done:${ev.event_id || label}`;
        if (!order.includes(key)) order.push(key);
        items.set(key, { id: ev.event_id || key, label, status: "done" });
      }
    }
  }

  return order.map((key) => items.get(key)!).filter(Boolean);
}

interface ResearchTodoListProps {
  visibleEvents: AgentActivityEvent[];
  plannedRoadmapSteps: RoadmapStep[];
  roadmapActiveIndex: number;
  streaming: boolean;
  /** Render with inverted (light-on-dark) colours for cinema / dark backgrounds */
  dark?: boolean;
}

export function ResearchTodoList({
  visibleEvents,
  plannedRoadmapSteps,
  roadmapActiveIndex,
  streaming,
  dark = false,
}: ResearchTodoListProps) {
  const items = deriveTodoItems(visibleEvents, plannedRoadmapSteps, roadmapActiveIndex);

  // Only show when we have tasks (during streaming or after agent runs)
  if (!items.length) return null;

  const doneCount = items.filter((i) => i.status === "done").length;
  const totalCount = items.length;

  if (dark) {
    return (
      <div className="space-y-1.5">
        {items.map((item) => (
          <div key={item.id} className="flex items-start gap-2">
            {item.status === "done" ? (
              <CheckCircle2 className="mt-[1px] h-3 w-3 shrink-0 text-[#34c759]" />
            ) : item.status === "active" ? (
              <Loader2
                className={`mt-[1px] h-3 w-3 shrink-0 text-[#6e6e73] ${streaming ? "animate-spin" : ""}`}
              />
            ) : (
              <Circle className="mt-[1px] h-3 w-3 shrink-0 text-white/20" />
            )}
            <p
              className={`text-[11px] leading-[1.35] ${
                item.status === "done"
                  ? "text-white/30 line-through"
                  : item.status === "active"
                    ? "font-medium text-white/90"
                    : "text-white/25"
              }`}
            >
              {item.label}
            </p>
          </div>
        ))}
        <p className="pt-1 text-[9px] tabular-nums text-white/25">{doneCount}/{totalCount} done</p>
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-2xl border border-black/[0.07] bg-white/70 px-4 py-3 backdrop-blur">
      <div className="mb-2.5 flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#86868b]">
          Tasks
        </p>
        <p className="text-[10px] tabular-nums text-[#aeaeb2]">
          {doneCount}/{totalCount}
        </p>
      </div>

      <div className="space-y-2">
        {items.map((item) => (
          <div key={item.id} className="flex items-start gap-2.5">
            {item.status === "done" ? (
              <CheckCircle2 className="mt-[1px] h-3.5 w-3.5 shrink-0 text-[#34c759]" />
            ) : item.status === "active" ? (
              <Loader2
                className={`mt-[1px] h-3.5 w-3.5 shrink-0 text-[#007aff] ${streaming ? "animate-spin" : ""}`}
              />
            ) : (
              <Circle className="mt-[1px] h-3.5 w-3.5 shrink-0 text-[#d1d1d6]" />
            )}
            <p
              className={`text-[12px] leading-[1.35] ${
                item.status === "done"
                  ? "text-[#aeaeb2] line-through decoration-[#c7c7cc]"
                  : item.status === "active"
                    ? "font-medium text-[#1d1d1f]"
                    : "text-[#c7c7cc]"
              }`}
            >
              {item.label}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
