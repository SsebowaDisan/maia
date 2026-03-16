import { useEffect, useState } from "react";
import { TrendingUp, Clock, DollarSign, BarChart2, RefreshCw } from "lucide-react";

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

function StatCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: React.ReactNode;
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

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/roi?days=${days}`, { credentials: "include" });
      if (res.ok) {
        const d = await res.json() as RoiSummary;
        setData(d);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  const maxCost = data ? Math.max(...data.by_agent.map((a) => a.cost_avoided_usd), 1) : 1;

  return (
    <div className={`flex flex-col gap-6 p-6 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-foreground">ROI Dashboard</h2>
          <p className="text-sm text-muted-foreground">
            Time and cost saved by your AI agents
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
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
          value={data ? String(data.total_runs_completed) : "—"}
          sub={`in the last ${days} days`}
        />
        <StatCard
          icon={<Clock size={13} />}
          label="Hours saved"
          value={data ? `${data.total_time_saved_hours}h` : "—"}
          sub="estimated human time"
        />
        <StatCard
          icon={<DollarSign size={13} />}
          label="Cost avoided"
          value={data ? `$${data.total_cost_avoided_usd.toFixed(2)}` : "—"}
          sub="at your configured hourly rate"
        />
      </div>

      {/* Per-agent breakdown */}
      {data && data.by_agent.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <BarChart2 size={14} className="text-muted-foreground" />
            <h3 className="text-sm font-medium text-foreground">By agent</h3>
          </div>
          <div className="space-y-2">
            {data.by_agent.map((agent) => (
              <div key={agent.agent_id} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-foreground font-mono truncate max-w-[200px]">
                    {agent.agent_id}
                  </span>
                  <span className="text-muted-foreground shrink-0 ml-2">
                    {agent.runs_completed} runs ·{" "}
                    {(agent.time_saved_minutes / 60).toFixed(1)}h ·{" "}
                    ${agent.cost_avoided_usd.toFixed(2)}
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
      )}

      {data && data.by_agent.length === 0 && !loading && (
        <div className="text-center py-12 text-muted-foreground">
          <TrendingUp size={32} className="mx-auto mb-3 opacity-20" />
          <p className="text-sm">No ROI data yet for this period.</p>
          <p className="text-xs mt-1 opacity-60">
            Configure <code className="font-mono">estimated_minutes_per_run</code> for your agents
            via <code className="font-mono">PATCH /api/agents/&#123;id&#125;/roi-config</code>.
          </p>
        </div>
      )}
    </div>
  );
}
