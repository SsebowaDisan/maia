import { useEffect, useRef } from "react";

type MultiAgentEvent = {
  text: string;
  type?: "info" | "warning" | "error";
};

type MultiAgentColumn = {
  agentId: string;
  agentName: string;
  skillId?: string;
  skillName?: string;
  status: "pending" | "running" | "done" | "blocked";
  events: MultiAgentEvent[];
};

type MultiAgentTheatreProps = {
  columns: MultiAgentColumn[];
};

function badgeClass(status: MultiAgentColumn["status"]): string {
  if (status === "done") {
    return "bg-[#ecfdf3] text-[#166534]";
  }
  if (status === "running") {
    return "bg-[#f5f3ff] text-[#7c3aed]";
  }
  if (status === "blocked") {
    return "bg-[#fff7ed] text-[#9a3412]";
  }
  return "bg-[#f2f4f7] text-[#475467]";
}

function eventTone(eventType: MultiAgentEvent["type"]): string {
  if (eventType === "error") {
    return "border-[#fecaca] bg-[#fef2f2] text-[#991b1b]";
  }
  if (eventType === "warning") {
    return "border-[#fed7aa] bg-[#fffbeb] text-[#9a3412]";
  }
  return "border-black/[0.06] bg-white text-[#344054]";
}

function initials(name: string): string {
  const tokens = String(name || "")
    .trim()
    .split(/[\s_\-.]+/)
    .filter(Boolean);
  if (!tokens.length) {
    return "A";
  }
  if (tokens.length === 1) {
    return tokens[0].slice(0, 2).toUpperCase();
  }
  return `${tokens[0][0] || ""}${tokens[1][0] || ""}`.toUpperCase();
}

function avatarColor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash |= 0;
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue} 70% 92%)`;
}

export function MultiAgentTheatre({ columns }: MultiAgentTheatreProps) {
  const eventListRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      Object.values(eventListRefs.current).forEach((node) => {
        if (!node) {
          return;
        }
        node.scrollTop = node.scrollHeight;
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [columns]);

  return (
    <div className="overflow-x-auto rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="flex min-w-max gap-3">
        {columns.map((column, index) => (
          <section key={column.agentId} className="w-[300px] rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <span
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-white/80 text-[10px] font-semibold text-[#1f2937]"
                  style={{ backgroundColor: avatarColor(column.agentId || column.agentName) }}
                >
                  {initials(column.agentName || column.agentId)}
                </span>
                <div className="min-w-0">
                  <h3 className="truncate text-[14px] font-semibold text-[#111827]">{column.agentName}</h3>
                  {column.skillName || column.skillId ? (
                    <p className="mt-0.5 truncate text-[11px] text-[#667085]">{column.skillName || column.skillId}</p>
                  ) : null}
                </div>
              </div>
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${badgeClass(column.status)}`}>
                {column.status}
              </span>
            </div>
            <div
              ref={(node) => {
                eventListRefs.current[column.agentId] = node;
              }}
              className="max-h-[220px] space-y-1 overflow-y-auto pr-1"
            >
              {column.events.length ? (
                column.events.map((event, eventIndex) => (
                  <p
                    key={`${column.agentId}-${eventIndex}-${event.text}`}
                    className={`rounded-lg border px-2 py-1 text-[12px] ${eventTone(event.type)}`}
                  >
                    {event.text}
                  </p>
                ))
              ) : (
                <p className="rounded-lg border border-black/[0.06] bg-white px-2 py-1 text-[12px] text-[#98a2b3]">
                  No live events for this step yet.
                </p>
              )}
            </div>
            {index < columns.length - 1 ? (
              <div className="mt-3 text-center text-[12px] text-[#667085]">Delegates to next</div>
            ) : null}
          </section>
        ))}
      </div>
    </div>
  );
}

export type { MultiAgentColumn, MultiAgentEvent };
