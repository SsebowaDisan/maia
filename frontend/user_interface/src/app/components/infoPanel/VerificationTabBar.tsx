import { TrustMeter } from "./TrustMeter";

type VerificationTab = "sources" | "review" | "evidence" | "trail" | "compare";
type EvidenceMode = "exact" | "context";

type VerificationTabBarProps = {
  activeTab: VerificationTab;
  onChangeTab: (tab: VerificationTab) => void;
  evidenceMode: EvidenceMode;
  onChangeEvidenceMode: (mode: EvidenceMode) => void;
  searchQuery: string;
  onChangeSearchQuery: (next: string) => void;
  showTabs?: boolean;
  trustScore?: number | null;
  trustGateColor?: "green" | "amber" | "red" | null;
  trustReason?: string | null;
};

const VERIFICATION_TABS: Array<{ id: VerificationTab; label: string }> = [
  { id: "sources", label: "Sources" },
  { id: "review", label: "Review" },
  { id: "evidence", label: "Evidence" },
  { id: "trail", label: "Trail" },
  { id: "compare", label: "Compare" },
];

function VerificationTabBar({
  activeTab,
  onChangeTab,
  evidenceMode,
  onChangeEvidenceMode,
  searchQuery,
  onChangeSearchQuery,
  showTabs = true,
  trustScore = null,
  trustGateColor = null,
  trustReason = null,
}: VerificationTabBarProps) {
  return (
    <div className="space-y-2 rounded-2xl border border-[#d2d2d7] bg-white px-3 py-3 shadow-sm">
      {showTabs ? (
        <div className="flex gap-1 overflow-x-auto">
          {VERIFICATION_TABS.map((tab) => {
            const active = tab.id === activeTab;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => onChangeTab(tab.id)}
                className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] transition ${
                  active
                    ? "border-[#1d1d1f] bg-[#1d1d1f] text-white"
                    : "border-black/[0.08] bg-white text-[#4c4c50] hover:bg-[#f3f3f5]"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-2">
        <div className="inline-flex rounded-full border border-black/[0.08] bg-[#f6f7fb] p-0.5">
          <button
            type="button"
            onClick={() => onChangeEvidenceMode("exact")}
            className={`rounded-full px-2 py-1 text-[10px] uppercase tracking-wide ${
              evidenceMode === "exact" ? "bg-[#111827] text-white" : "text-[#4c4c50]"
            }`}
          >
            Exact
          </button>
          <button
            type="button"
            onClick={() => onChangeEvidenceMode("context")}
            className={`rounded-full px-2 py-1 text-[10px] uppercase tracking-wide ${
              evidenceMode === "context" ? "bg-[#111827] text-white" : "text-[#4c4c50]"
            }`}
          >
            Context
          </button>
        </div>

        <input
          value={searchQuery}
          onChange={(event) => onChangeSearchQuery(event.target.value)}
          placeholder="Semantic find"
          className="h-8 min-w-0 flex-1 rounded-lg border border-black/[0.08] bg-white px-2 text-[12px] text-[#1d1d1f] outline-none focus:border-[#0a84ff]/60"
        />
      </div>

      {trustScore !== null && trustGateColor ? (
        <TrustMeter
          score={trustScore}
          gateColor={trustGateColor}
          reason={trustReason ?? undefined}
        />
      ) : null}
    </div>
  );
}

export type { VerificationTab, EvidenceMode };
export { VerificationTabBar };
