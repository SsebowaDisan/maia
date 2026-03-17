import { useMemo, useState } from "react";

type BudgetSettingsProps = {
  currentCostUsd: number;
};

export function BudgetSettings({ currentCostUsd }: BudgetSettingsProps) {
  const [dailyLimit, setDailyLimit] = useState(2);
  const [alertThreshold, setAlertThreshold] = useState(80);
  const progress = useMemo(() => {
    if (dailyLimit <= 0) {
      return 0;
    }
    return Math.min(100, (currentCostUsd / dailyLimit) * 100);
  }, [currentCostUsd, dailyLimit]);

  return (
    <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <h3 className="text-[18px] font-semibold text-[#111827]">Budget settings</h3>
      <p className="mt-1 text-[13px] text-[#667085]">Set daily spend limits and alert thresholds.</p>

      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label>
          <span className="text-[12px] font-semibold text-[#667085]">Daily limit (USD)</span>
          <input
            type="number"
            min={0}
            step={0.1}
            value={dailyLimit}
            onChange={(event) => setDailyLimit(Number(event.target.value || 0))}
            className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
          />
        </label>
        <label>
          <span className="text-[12px] font-semibold text-[#667085]">Alert threshold (%)</span>
          <input
            type="number"
            min={1}
            max={100}
            value={alertThreshold}
            onChange={(event) => setAlertThreshold(Number(event.target.value || 80))}
            className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
          />
        </label>
      </div>

      <div className="mt-4 rounded-xl border border-black/[0.06] bg-[#f8fafc] p-3">
        <div className="mb-2 flex items-center justify-between text-[12px] text-[#667085]">
          <span>${currentCostUsd.toFixed(2)} today</span>
          <span>${dailyLimit.toFixed(2)} limit</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-[#e4e7ec]">
          <div className="h-full bg-[#7c3aed]" style={{ width: `${progress}%` }} />
        </div>
        <p className="mt-2 text-[12px] text-[#475467]">
          Alert fires at {(dailyLimit * (alertThreshold / 100)).toFixed(2)} USD.
        </p>
      </div>
    </section>
  );
}

