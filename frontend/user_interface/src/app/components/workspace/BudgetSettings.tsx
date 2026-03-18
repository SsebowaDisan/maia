import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { getBudget, setBudget } from "../../../api/client";

type BudgetSettingsProps = {
  currentCostUsd: number;
};

export function BudgetSettings({ currentCostUsd }: BudgetSettingsProps) {
  const [dailyLimit, setDailyLimit] = useState(2);
  const [alertThreshold, setAlertThreshold] = useState(80);
  const [todayCost, setTodayCost] = useState(currentCostUsd);
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load budget settings from backend on mount
  useEffect(() => {
    let cancelled = false;
    getBudget()
      .then((data) => {
        if (cancelled) return;
        if (data.daily_limit_usd > 0) {
          setDailyLimit(data.daily_limit_usd);
        }
        if (data.alert_threshold_fraction > 0) {
          setAlertThreshold(Math.round(data.alert_threshold_fraction * 100));
        }
        if (data.today_cost_usd > 0) {
          setTodayCost(data.today_cost_usd);
        }
        setLoaded(true);
      })
      .catch(() => {
        setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Use backend cost if available, otherwise fall back to prop
  const effectiveCost = todayCost > 0 ? todayCost : currentCostUsd;

  const progress = useMemo(() => {
    if (dailyLimit <= 0) return 0;
    return Math.min(100, (effectiveCost / dailyLimit) * 100);
  }, [effectiveCost, dailyLimit]);

  // Debounced save to backend
  const persistBudget = useCallback(
    (limit: number, thresholdPct: number) => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
      saveTimerRef.current = setTimeout(() => {
        setSaving(true);
        setBudget(limit, thresholdPct / 100)
          .catch(() => {})
          .finally(() => setSaving(false));
      }, 800);
    },
    [],
  );

  const handleLimitChange = (value: number) => {
    setDailyLimit(value);
    persistBudget(value, alertThreshold);
  };

  const handleThresholdChange = (value: number) => {
    setAlertThreshold(value);
    persistBudget(dailyLimit, value);
  };

  return (
    <section className="rounded-2xl border border-black/[0.08] bg-white p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-[18px] font-semibold text-[#111827]">Budget settings</h3>
        {saving ? (
          <span className="text-[11px] text-[#667085]">Saving...</span>
        ) : null}
      </div>
      <p className="mt-1 text-[13px] text-[#667085]">Set daily spend limits and alert thresholds.</p>

      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label>
          <span className="text-[12px] font-semibold text-[#667085]">Daily limit (USD)</span>
          <input
            type="number"
            min={0}
            step={0.1}
            value={dailyLimit}
            onChange={(event) => handleLimitChange(Number(event.target.value || 0))}
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
            onChange={(event) => handleThresholdChange(Number(event.target.value || 80))}
            className="mt-1 w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px]"
          />
        </label>
      </div>

      <div className="mt-4 rounded-xl border border-black/[0.06] bg-[#f8fafc] p-3">
        <div className="mb-2 flex items-center justify-between text-[12px] text-[#667085]">
          <span>${effectiveCost.toFixed(2)} today</span>
          <span>${dailyLimit.toFixed(2)} limit</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-[#e4e7ec]">
          <div
            className={`h-full transition-all ${progress >= 90 ? "bg-[#ef4444]" : progress >= 70 ? "bg-[#f59e0b]" : "bg-[#7c3aed]"}`}
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="mt-2 text-[12px] text-[#475467]">
          Alert fires at {(dailyLimit * (alertThreshold / 100)).toFixed(2)} USD.
        </p>
      </div>
    </section>
  );
}

