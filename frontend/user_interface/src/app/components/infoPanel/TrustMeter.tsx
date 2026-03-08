"use client";

type TrustMeterProps = {
  score: number;
  gateColor: "green" | "amber" | "red";
  reason?: string;
};

const GATE_COLORS: Record<TrustMeterProps["gateColor"], { bar: string; text: string; label: string }> = {
  green: { bar: "bg-[#34c759]", text: "text-[#1a6630]", label: "Verified" },
  amber: { bar: "bg-[#ff9f0a]", text: "text-[#7a4800]", label: "Uncertain" },
  red: { bar: "bg-[#ff3b30]", text: "text-[#8b1a14]", label: "Contested" },
};

/**
 * T4: Live Trust Meter — animated confidence bar with spring overshoot.
 * Renders a slim progress bar colored by gate_color, with score label.
 */
function TrustMeter({ score, gateColor, reason }: TrustMeterProps) {
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
  const { bar, text, label } = GATE_COLORS[gateColor] ?? GATE_COLORS.amber;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className={`text-[10px] font-semibold uppercase tracking-wide ${text}`}>{label}</span>
        <span className={`text-[10px] tabular-nums ${text}`}>{pct}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-black/[0.07]">
        <div
          className={`h-full rounded-full ${bar}`}
          style={{
            width: `${pct}%`,
            transition: "width 800ms cubic-bezier(0.34, 1.56, 0.64, 1)",
          }}
        />
      </div>
      {reason ? (
        <p className="line-clamp-1 text-[10px] text-[#86868b]">{reason}</p>
      ) : null}
    </div>
  );
}

export { TrustMeter };
export type { TrustMeterProps };
