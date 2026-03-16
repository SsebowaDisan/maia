import { useEffect, useState } from "react";
import { TrendingUp } from "lucide-react";

type RoiSummaryPayload = {
  total_time_saved_hours?: number;
  total_cost_avoided_usd?: number;
};

function EmptyState() {
  const [roiSummary, setRoiSummary] = useState<RoiSummaryPayload | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadRoiSummary = async () => {
      try {
        const response = await fetch("/api/roi?days=30", { credentials: "include" });
        if (!response.ok || cancelled) {
          return;
        }
        const payload = (await response.json()) as RoiSummaryPayload;
        const totalCost = Number(payload.total_cost_avoided_usd ?? 0);
        if (!Number.isFinite(totalCost) || totalCost <= 0) {
          return;
        }
        setRoiSummary(payload);
      } catch {
        // Keep empty state stable when ROI service is unavailable.
      }
    };
    void loadRoiSummary();
    return () => {
      cancelled = true;
    };
  }, []);

  const navigateToRoi = () => {
    window.history.pushState({}, "", "/operations?tab=roi");
    window.dispatchEvent(new PopStateEvent("popstate"));
  };

  return (
    <div className="h-full flex flex-col items-center justify-center">
      <div className="max-w-2xl w-full text-center space-y-3">
        <div className="w-16 h-16 bg-gradient-to-br from-[#1d1d1f] to-[#3a3a3c] rounded-2xl mx-auto mb-4 flex items-center justify-center shadow-lg">
          <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
          </svg>
        </div>
        <h1 className="text-[28px] tracking-tight text-[#1d1d1f]">
          This is the beginning of a new conversation.
        </h1>
        <p className="text-[15px] text-[#86868b] leading-relaxed">
          Start by uploading files or URLs from the sidebar.
        </p>
        {roiSummary ? (
          <button
            type="button"
            onClick={navigateToRoi}
            className="mx-auto mt-5 inline-flex items-center gap-2 rounded-full border border-black/[0.08] bg-white px-4 py-2 text-[12px] font-medium text-[#3f4758] shadow-sm transition-colors hover:border-black/[0.15] hover:text-[#111827]"
          >
            <TrendingUp className="h-3.5 w-3.5 text-[#5f6b85]" />
            <span>
              This month: saved {Number(roiSummary.total_time_saved_hours ?? 0).toFixed(1)}h · $
              {Number(roiSummary.total_cost_avoided_usd ?? 0).toFixed(2)} cost avoided
            </span>
          </button>
        ) : null}
      </div>
    </div>
  );
}

export { EmptyState };
