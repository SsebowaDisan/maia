import { useState } from "react";
import { CheckCircle2, ShieldAlert, XCircle } from "lucide-react";

type GateApprovalCardProps = {
  runId: string;
  gateId: string;
  toolId: string;
  paramsPreview: string;
  costEstimateUsd?: number | null;
  onApprove?: (runId: string, gateId: string) => Promise<void> | void;
  onReject?: (runId: string, gateId: string) => Promise<void> | void;
};

type LocalState = "pending" | "approving" | "rejecting" | "approved" | "rejected" | "error";

export function GateApprovalCard({
  runId,
  gateId,
  toolId,
  paramsPreview,
  costEstimateUsd,
  onApprove,
  onReject,
}: GateApprovalCardProps) {
  const [state, setState] = useState<LocalState>("pending");
  const [error, setError] = useState("");
  const hasResolvableRun = Boolean(String(runId || "").trim()) && String(runId || "").trim() !== "active-run";
  const hasGateId = Boolean(String(gateId || "").trim());
  const canSubmit = hasResolvableRun && hasGateId && Boolean(onApprove) && Boolean(onReject);

  const approve = async () => {
    if (!canSubmit) {
      setState("error");
      setError("Waiting for active run details before approval can be submitted.");
      return;
    }
    setError("");
    setState("approving");
    try {
      await onApprove?.(runId, gateId);
      setState("approved");
    } catch (nextError) {
      setError(String(nextError));
      setState("error");
    }
  };

  const reject = async () => {
    if (!canSubmit) {
      setState("error");
      setError("Waiting for active run details before rejection can be submitted.");
      return;
    }
    setError("");
    setState("rejecting");
    try {
      await onReject?.(runId, gateId);
      setState("rejected");
    } catch (nextError) {
      setError(String(nextError));
      setState("error");
    }
  };

  const terminalMessage =
    state === "approved"
      ? "Approved - continuing run."
      : state === "rejected"
        ? "Rejected - run cancelled."
        : "";

  return (
    <article className="rounded-2xl border border-[#fde68a] bg-[#fffbeb] p-4 shadow-[0_12px_28px_rgba(120,53,15,0.14)]">
      <div className="mb-3 flex items-center gap-2 text-[#92400e]">
        <ShieldAlert size={16} />
        <p className="text-[13px] font-semibold uppercase tracking-[0.12em]">Approval required</p>
      </div>
      <h3 className="text-[16px] font-semibold text-[#7c2d12]">{toolId}</h3>
      <p className="mt-1 text-[13px] leading-[1.5] text-[#9a3412]">{paramsPreview}</p>
      <p className="mt-2 text-[12px] text-[#b45309]">
        {typeof costEstimateUsd === "number"
          ? `Estimated cost: $${costEstimateUsd.toFixed(2)}`
          : "Estimated cost: unknown"}
      </p>

      {terminalMessage ? (
        <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-[#fdba74] bg-white px-3 py-1 text-[12px] font-semibold text-[#9a3412]">
          {state === "approved" ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
          {terminalMessage}
        </div>
      ) : (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!canSubmit || state === "approving" || state === "rejecting"}
            onClick={() => void approve()}
            className="rounded-full bg-[#7c3aed] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[#6d28d9] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {state === "approving" ? "Approving..." : "Approve"}
          </button>
          <button
            type="button"
            disabled={!canSubmit || state === "approving" || state === "rejecting"}
            onClick={() => void reject()}
            className="rounded-full border border-[#b91c1c]/30 bg-white px-4 py-2 text-[13px] font-semibold text-[#b91c1c] hover:bg-[#fff1f2] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {state === "rejecting" ? "Rejecting..." : "Reject"}
          </button>
        </div>
      )}

      {error ? (
        <p className="mt-3 text-[12px] text-[#b91c1c]">{error}</p>
      ) : null}
      {!canSubmit ? (
        <p className="mt-2 text-[12px] text-[#92400e]">
          Waiting for live run and gate identifiers...
        </p>
      ) : null}
    </article>
  );
}
