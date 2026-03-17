import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";

type Direction = "up" | "down" | "flat";

type ScoreMetric = {
  label: string;
  value: string;
  change?: string;
  direction: Direction;
};

type ScorecardWidgetProps = {
  title?: string;
  subtitle?: string;
  metrics?: Array<Record<string, unknown>>;
};

function normalizeDirection(value: unknown): Direction {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "up") return "up";
  if (normalized === "down") return "down";
  return "flat";
}

function normalizeMetric(row: Record<string, unknown>): ScoreMetric | null {
  const label = String(row.label || row.name || row.metric || "").trim();
  const value = String(row.value ?? row.current ?? "").trim();
  if (!label || !value) {
    return null;
  }
  const change = String(row.change ?? row.delta ?? "").trim();
  return {
    label,
    value,
    change: change || undefined,
    direction: normalizeDirection(row.direction),
  };
}

function directionTone(direction: Direction): string {
  if (direction === "up") {
    return "border-[#bbf7d0] bg-[#f0fdf4] text-[#166534]";
  }
  if (direction === "down") {
    return "border-[#fecaca] bg-[#fff1f2] text-[#b42318]";
  }
  return "border-[#d0d5dd] bg-[#f8fafc] text-[#475467]";
}

function directionIcon(direction: Direction) {
  if (direction === "up") {
    return <ArrowUpRight size={14} />;
  }
  if (direction === "down") {
    return <ArrowDownRight size={14} />;
  }
  return <ArrowRight size={14} />;
}

function ScorecardWidget({ title, subtitle, metrics = [] }: ScorecardWidgetProps) {
  const rows = Array.isArray(metrics)
    ? metrics
        .map((entry) => (entry && typeof entry === "object" ? normalizeMetric(entry as Record<string, unknown>) : null))
        .filter((entry): entry is ScoreMetric => Boolean(entry))
    : [];

  return (
    <section className="rounded-2xl border border-black/[0.08] bg-white p-4 shadow-[0_16px_32px_rgba(15,23,42,0.05)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          {title ? <p className="text-[16px] font-semibold text-[#101828]">{title}</p> : null}
          {subtitle ? <p className="mt-1 text-[12px] text-[#667085]">{subtitle}</p> : null}
        </div>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
        {rows.length === 0 ? (
          <p className="rounded-xl border border-black/[0.08] bg-[#fcfcfd] px-3 py-2 text-[12px] text-[#667085]">
            No KPI metrics were provided.
          </p>
        ) : null}
        {rows.map((metric) => (
          <article
            key={`${metric.label}-${metric.value}`}
            className="rounded-xl border border-black/[0.08] bg-[#fcfcfd] px-3 py-2"
          >
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#667085]">{metric.label}</p>
            <p className="mt-1 text-[20px] font-semibold tracking-[-0.01em] text-[#111827]">{metric.value}</p>
            {metric.change ? (
              <div
                className={`mt-2 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${directionTone(
                  metric.direction,
                )}`}
              >
                {directionIcon(metric.direction)}
                {metric.change}
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

export { ScorecardWidget };
export type { ScorecardWidgetProps };
