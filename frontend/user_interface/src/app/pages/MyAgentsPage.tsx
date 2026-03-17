import { useEffect, useMemo, useState } from "react";

import { getAgent, listAgentRuns, listAgents, type AgentRunRecord } from "../../api/client";

type MyAgentsCard = {
  agentId: string;
  name: string;
  description: string;
  tags: string[];
  triggerFamily: string;
  cronExpression: string;
  scheduleLabel: string;
  status: "Active" | "Scheduled" | "Error";
  lastRunAt: string;
  lastRunSummary: string;
};

function navigateToPath(path: string) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function formatRelativeTime(isoString: string): string {
  if (!isoString) {
    return "Never";
  }
  const timestamp = new Date(isoString).getTime();
  if (!Number.isFinite(timestamp)) {
    return "Unknown";
  }
  const diffMs = Date.now() - timestamp;
  if (diffMs < 0) {
    return "Just now";
  }
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) {
    return "Just now";
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function describeCron(expr: string): string {
  const parts = String(expr || "").trim().split(/\s+/);
  if (parts.length !== 5) {
    return String(expr || "Custom schedule");
  }
  const [minuteRaw, hourRaw, , , dayOfWeek] = parts;
  const minute = Number(minuteRaw);
  const hour = Number(hourRaw);
  if (!Number.isFinite(minute) || !Number.isFinite(hour)) {
    return expr;
  }
  const timeLabel = `${hour % 12 === 0 ? 12 : hour % 12}:${String(minute).padStart(2, "0")} ${
    hour < 12 ? "AM" : "PM"
  }`;
  if (dayOfWeek === "*" || dayOfWeek === "0-6") {
    return `Daily at ${timeLabel}`;
  }
  if (dayOfWeek === "1-5" || dayOfWeek === "1,2,3,4,5") {
    return `Weekdays at ${timeLabel}`;
  }
  const weekdayMap: Record<string, string> = {
    "0": "Sunday",
    "1": "Monday",
    "2": "Tuesday",
    "3": "Wednesday",
    "4": "Thursday",
    "5": "Friday",
    "6": "Saturday",
    "7": "Sunday",
  };
  if (weekdayMap[dayOfWeek]) {
    return `Every ${weekdayMap[dayOfWeek]} at ${timeLabel}`;
  }
  return expr;
}

function readLatestRun(runs: AgentRunRecord[]): AgentRunRecord | null {
  if (!Array.isArray(runs) || runs.length === 0) {
    return null;
  }
  const sorted = [...runs].sort(
    (left, right) =>
      new Date(String(right.started_at || "")).getTime() -
      new Date(String(left.started_at || "")).getTime(),
  );
  return sorted[0] || null;
}

export function MyAgentsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cards, setCards] = useState<MyAgentsCard[]>([]);

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const rows = await listAgents();
        const nextCards = await Promise.all(
          (rows || []).map(async (row) => {
            const agentId = String(row.agent_id || row.id || "").trim();
            const [runs, detail] = await Promise.all([
              listAgentRuns(agentId, { limit: 12 }).catch(() => []),
              getAgent(agentId).catch(() => null),
            ]);
            const definition = ((detail?.definition || {}) as Record<string, unknown>) || {};
            const description = String(
              definition.description ||
                (row as unknown as { description?: string }).description ||
                "",
            ).trim();
            const tagsRaw = Array.isArray(definition.tags)
              ? definition.tags
              : Array.isArray((row as unknown as { tags?: unknown[] }).tags)
                ? (row as unknown as { tags?: unknown[] }).tags || []
                : [];
            const tags = tagsRaw
              .map((tag) => String(tag || "").trim())
              .filter(Boolean);
            const trigger = (definition.trigger || {}) as Record<string, unknown>;
            const triggerFamily = String(
              trigger.family ||
                (row as unknown as { trigger_family?: string }).trigger_family ||
                "",
            )
              .trim()
              .toLowerCase();
            const cronExpression = String(trigger.cron_expression || "").trim();
            const latestRun = readLatestRun(runs || []);
            const latestStatus = String(latestRun?.status || "").toLowerCase();
            const status: MyAgentsCard["status"] =
              latestStatus === "failed" || latestStatus === "error"
                ? "Error"
                : triggerFamily === "scheduled"
                  ? "Scheduled"
                  : "Active";
            return {
              agentId,
              name: String(row.name || agentId || "Untitled agent").trim(),
              description,
              tags,
              triggerFamily,
              cronExpression,
              scheduleLabel:
                triggerFamily === "scheduled" && cronExpression
                  ? describeCron(cronExpression)
                  : "",
              status,
              lastRunAt: String(latestRun?.started_at || "").trim(),
              lastRunSummary: String(latestRun?.result_summary || "").trim(),
            } satisfies MyAgentsCard;
          }),
        );
        if (!disposed) {
          setCards(nextCards);
        }
      } catch (nextError) {
        if (!disposed) {
          setError(String(nextError || "Failed to load agents."));
        }
      } finally {
        if (!disposed) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      disposed = true;
    };
  }, []);

  const sortedCards = useMemo(
    () =>
      [...cards].sort((left, right) =>
        String(left.name || "").localeCompare(String(right.name || "")),
      ),
    [cards],
  );

  return (
    <div className="h-full overflow-y-auto bg-[#eef1f5] p-5">
      <div className="mx-auto max-w-[1320px] space-y-4">
        <section className="rounded-[24px] border border-black/[0.08] bg-white px-6 py-5 shadow-[0_16px_40px_rgba(15,23,42,0.1)]">
          <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-[#667085]">
            Workspace
          </p>
          <h1 className="mt-1 text-[32px] font-semibold tracking-[-0.02em] text-[#101828]">
            My agents
          </h1>
          <p className="mt-2 text-[14px] text-[#475467]">
            Manage installed agents, review schedule context, and jump directly into chat.
          </p>
        </section>

        {loading ? (
          <section className="rounded-2xl border border-black/[0.08] bg-white p-4 text-[13px] text-[#667085]">
            Loading agents...
          </section>
        ) : null}

        {!loading && error ? (
          <section className="rounded-2xl border border-[#fca5a5] bg-[#fff1f2] p-4 text-[13px] text-[#9f1239]">
            {error}
          </section>
        ) : null}

        {!loading && !error ? (
          <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {sortedCards.map((agent) => (
              <article
                key={agent.agentId}
                className="rounded-2xl border border-black/[0.08] bg-white p-4 shadow-[0_10px_28px_rgba(15,23,42,0.07)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-[18px] font-semibold text-[#111827]">{agent.name}</h2>
                  <span
                    className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                      agent.status === "Error"
                        ? "bg-[#fff1f2] text-[#b42318]"
                        : agent.status === "Scheduled"
                          ? "bg-[#eff6ff] text-[#1d4ed8]"
                          : "bg-[#ecfdf3] text-[#166534]"
                    }`}
                  >
                    {agent.status}
                  </span>
                </div>

                {agent.description ? (
                  <p className="mt-2 line-clamp-3 text-[13px] leading-[1.45] text-[#475467]">
                    {agent.description}
                  </p>
                ) : (
                  <p className="mt-2 text-[12px] text-[#98a2b3]">No description provided.</p>
                )}

                <div className="mt-3 flex flex-wrap gap-1.5">
                  {agent.tags.slice(0, 5).map((tag) => (
                    <span
                      key={`${agent.agentId}:${tag}`}
                      className="rounded-full border border-black/[0.08] bg-[#f8fafc] px-2 py-0.5 text-[10px] font-medium text-[#475467]"
                    >
                      {tag}
                    </span>
                  ))}
                </div>

                {agent.scheduleLabel ? (
                  <p className="mt-3 text-[12px] font-medium text-[#1d4ed8]">
                    {agent.scheduleLabel}
                  </p>
                ) : null}

                <p className="mt-1 text-[12px] text-[#667085]">
                  Last run: {agent.lastRunAt ? formatRelativeTime(agent.lastRunAt) : "Never"}
                </p>
                {agent.lastRunSummary ? (
                  <p className="mt-1 line-clamp-2 text-[12px] text-[#667085]">
                    {agent.lastRunSummary}
                  </p>
                ) : null}

                <div className="mt-4 flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => navigateToPath(`/?agent=${encodeURIComponent(agent.agentId)}`)}
                    className="rounded-full bg-[#111827] px-3.5 py-1.5 text-[12px] font-semibold text-white"
                  >
                    Chat
                  </button>
                  <button
                    type="button"
                    onClick={() => navigateToPath(`/agents/${encodeURIComponent(agent.agentId)}`)}
                    className="rounded-full border border-black/[0.12] bg-white px-3.5 py-1.5 text-[12px] font-semibold text-[#344054]"
                  >
                    Open
                  </button>
                </div>
              </article>
            ))}
            {sortedCards.length === 0 ? (
              <article className="rounded-2xl border border-dashed border-black/[0.12] bg-white p-5 text-[13px] text-[#667085]">
                No installed agents yet.
              </article>
            ) : null}
          </section>
        ) : null}
      </div>
    </div>
  );
}
