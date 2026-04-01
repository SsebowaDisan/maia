import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { BarChart2, Clock, DollarSign, RefreshCw, TrendingUp } from "lucide-react";
import { request } from "../../../api/client/core";

type AgentRoi = {
  agent_id: string;
  runs_completed: number;
  time_saved_minutes: number;
  cost_avoided_usd: number;
};

type RoiSummary = {
  tenant_id: string;
  period_days: number;
  total_runs_completed: number;
  total_time_saved_hours: number;
  total_cost_avoided_usd: number;
  by_agent: AgentRoi[];
};

type RoiSummaryRaw = Partial<Omit<RoiSummary, "by_agent">> & {
  by_agent?: unknown;
};

function toNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function normalizeRoiSummary(raw: RoiSummaryRaw): RoiSummary {
  const byAgentRaw = Array.isArray(raw.by_agent) ? raw.by_agent : [];
  const byAgent = byAgentRaw
    .map((entry): AgentRoi | null => {
      if (!entry || typeof entry !== "object") {
        return null;
      }
      const candidate = entry as Record<string, unknown>;
      return {
        agent_id: String(candidate.agent_id ?? "unknown"),
        runs_completed: toNumber(candidate.runs_completed, 0),
        time_saved_minutes: toNumber(candidate.time_saved_minutes, 0),
        cost_avoided_usd: toNumber(candidate.cost_avoided_usd, 0),
      };
    })
    .filter((entry): entry is AgentRoi => entry !== null);

  return {
    tenant_id: String(raw.tenant_id ?? ""),
    period_days: toNumber(raw.period_days, 0),
    total_runs_completed: toNumber(raw.total_runs_completed, 0),
    total_time_saved_hours: toNumber(raw.total_time_saved_hours, 0),
    total_cost_avoided_usd: toNumber(raw.total_cost_avoided_usd, 0),
    by_agent: byAgent,
  };
}

function StatCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-border/60 bg-card p-4 flex flex-col gap-1">
      <div className="flex items-center gap-2 text-muted-foreground text-xs">
        {icon}
        <span>{label}</span>
      </div>
      <p className="text-2xl font-bold text-foreground">{value}</p>
      {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

type ROIDashboardProps = {
  className?: string;
};

export function ROIDashboard({ className = "" }: ROIDashboardProps) {
  const [data, setData] = useState<RoiSummary | null>(null);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const load = async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const payload = await request<RoiSummaryRaw>(`/api/roi?days=${days}`);
      setData(normalizeRoiSummary(payload));
    } catch (error) {
      setData(null);
      const message = String(error instanceof Error ? error.message : error || "").toLowerCase();
      if (message.includes("not authenticated") || message.includes("401")) {
        setErrorMessage("Sign in required to view ROI data.");
      } else {
        setErrorMessage("Could not load ROI data right now.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  const byAgent = data?.by_agent ?? [];
  const maxCost = useMemo(
    () => Math.max(...byAgent.map((agent) => agent.cost_avoided_usd), 1),
    [byAgent],
  );

  return (
    <div className={`flex flex-col gap-6 p-6 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">ROI Dashboard</h2>
          <p className="text-sm text-muted-foreground">Time and cost saved by your AI agents</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
            className="text-sm bg-background border border-border/60 rounded px-2 py-1.5"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="p-1.5 rounded hover:bg-accent text-muted-foreground transition-colors disabled:opacity-40"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard
          icon={<TrendingUp size={13} />}
          label="Runs completed"
          value={data ? String(data.total_runs_completed) : "--"}
          sub={`in the last ${days} days`}
        />
        <StatCard
          icon={<Clock size={13} />}
          label="Hours saved"
          value={data ? `${data.total_time_saved_hours}h` : "--"}
          sub="estimated human time"
        />
        <StatCard
          icon={<DollarSign size={13} />}
          label="Cost avoided"
          value={data ? `$${data.total_cost_avoided_usd.toFixed(2)}` : "--"}
          sub="at your configured hourly rate"
        />
      </div>

      {/* Per-agent breakdown */}
      {data && byAgent.length > 0 ? (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <BarChart2 size={14} className="text-muted-foreground" />
            <h3 className="text-sm font-medium text-foreground">By agent</h3>
          </div>
          <div className="space-y-2">
            {byAgent.map((agent) => (
              <div key={agent.agent_id} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-foreground font-mono truncate max-w-[200px]">{agent.agent_id}</span>
                  <span className="text-muted-foreground shrink-0 ml-2">
                    {agent.runs_completed} runs | {(agent.time_saved_minutes / 60).toFixed(1)}h | $
                    {agent.cost_avoided_usd.toFixed(2)}
                  </span>
                </div>
                <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${(agent.cost_avoided_usd / maxCost) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {errorMessage && !loading ? (
        <div className="text-center py-8 text-muted-foreground">
          <p className="text-sm">{errorMessage}</p>
        </div>
      ) : null}

      {data && byAgent.length === 0 && !loading && !errorMessage ? (
        <div className="text-center py-12 text-muted-foreground">
          <TrendingUp size={32} className="mx-auto mb-3 opacity-20" />
          <p className="text-sm">No ROI data yet for this period.</p>
          <p className="text-xs mt-1 opacity-60">
            Configure <code className="font-mono">estimated_minutes_per_run</code> for your agents via{" "}
            <code className="font-mono">PATCH /api/agents/&#123;id&#125;/roi-config</code>.
          </p>
        </div>
      ) : null}
    </div>
  );
}
