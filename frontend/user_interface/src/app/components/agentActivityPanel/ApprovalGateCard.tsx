"use client";

type ApprovalGateCardProps = {
  trustScore: number;
  gateColor: "amber" | "red";
  reason: string;
  onApprove: () => void;
  onCancel: () => void;
};

const GATE_RING: Record<ApprovalGateCardProps["gateColor"], string> = {
  amber: "border-[#ff9f0a]/60 shadow-[0_0_40px_rgba(255,159,10,0.35)]",
  red: "border-[#ff3b30]/60 shadow-[0_0_40px_rgba(255,59,48,0.35)]",
};

const GATE_LABEL: Record<ApprovalGateCardProps["gateColor"], string> = {
  amber: "Moderate Confidence",
  red: "Low Confidence — Review Required",
};

/**
 * T7: Approval Gate Spotlight — dims the theatre, centers this card, requires
 * explicit approval before MAIA continues. The backdrop dims everything else to 40%.
 */
function ApprovalGateCard({ trustScore, gateColor, reason, onApprove, onCancel }: ApprovalGateCardProps) {
  const pct = Math.round(Math.max(0, Math.min(1, trustScore)) * 100);

  return (
    <>
      {/* Dimming backdrop */}
      <div
        className="fixed inset-0 z-[9800]"
        style={{ backdropFilter: "brightness(0.4)" }}
        onClick={onCancel}
      />

      {/* Gate card */}
      <div
        className={`fixed left-1/2 top-1/2 z-[9900] w-80 -translate-x-1/2 -translate-y-1/2 rounded-2xl border-2 bg-white p-6 ${GATE_RING[gateColor]}`}
        style={{ animation: "gate-appear 400ms cubic-bezier(0.34, 1.56, 0.64, 1) forwards" }}
      >
        <style>{`
          @keyframes gate-appear {
            0%   { opacity: 0; transform: translate(-50%, -50%) scale(0.8); }
            100% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
          }
          @keyframes gate-pulse-ring {
            0%, 100% { box-shadow: 0 0 0 0 rgba(255,159,10,0.5); }
            50%       { box-shadow: 0 0 0 8px rgba(255,159,10,0); }
          }
        `}</style>

        <div className="mb-4 text-center">
          <div
            className={`mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full border-2 ${
              gateColor === "amber" ? "border-[#ff9f0a] bg-[#fff8eb]" : "border-[#ff3b30] bg-[#fff0f0]"
            }`}
            style={{ animation: "gate-pulse-ring 1.8s ease-out infinite" }}
          >
            <span className="text-2xl">{gateColor === "amber" ? "⚠️" : "🔴"}</span>
          </div>
          <p className={`text-[13px] font-semibold ${gateColor === "amber" ? "text-[#7a4800]" : "text-[#8b1a14]"}`}>
            {GATE_LABEL[gateColor]}
          </p>
          <p className="mt-1 text-[11px] text-[#6e6e73]">Trust score: {pct}%</p>
        </div>

        <div className="mb-4 rounded-xl border border-black/[0.08] bg-[#f7f7f9] px-3 py-2.5">
          <p className="text-[12px] text-[#3a3a3c]">{reason || "One or more claims could not be fully verified."}</p>
        </div>

        <div className="flex gap-2">
          <button
            type="button"
            onClick={onApprove}
            className={`flex-1 rounded-xl py-2 text-[13px] font-semibold text-white transition ${
              gateColor === "amber"
                ? "bg-[#ff9f0a] hover:bg-[#e08c00]"
                : "bg-[#ff3b30] hover:bg-[#cc2e25]"
            }`}
          >
            Approve
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 rounded-xl border border-black/[0.1] py-2 text-[13px] font-medium text-[#3a3a3c] transition hover:bg-[#f3f3f5]"
          >
            Cancel
          </button>
        </div>
      </div>
    </>
  );
}

export { ApprovalGateCard };
