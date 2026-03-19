import { useMemo, useState } from "react";
import { CheckCircle2, Pencil, ShieldAlert, XCircle } from "lucide-react";

type GateApprovalCardProps = {
  runId: string;
  gateId: string;
  toolId: string;
  paramsPreview: string;
  actionLabel?: string;
  preview?: Record<string, unknown> | null;
  costEstimateUsd?: number | null;
  onApprove?: (
    runId: string,
    gateId: string,
    editedParams?: Record<string, unknown>,
  ) => Promise<void> | void;
  onReject?: (runId: string, gateId: string) => Promise<void> | void;
};

type LocalState =
  | "pending"
  | "approving"
  | "rejecting"
  | "approved"
  | "rejected"
  | "error";

function readPreviewType(preview: Record<string, unknown> | null | undefined): string {
  return String(preview?.type || "action").trim().toLowerCase();
}

function toReadableJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value || "");
  }
}

function initialEditableText(preview: Record<string, unknown> | null | undefined): string {
  const type = readPreviewType(preview);
  if (!preview) {
    return "";
  }
  if (type === "email") {
    return String(preview.body_preview || preview.body || "").trim();
  }
  if (type === "message") {
    return String(preview.text_preview || preview.text || "").trim();
  }
  if (type === "transaction") {
    return toReadableJson(preview.params_preview || preview.summary || preview);
  }
  return toReadableJson(preview.params_preview || preview);
}

function editedParamsFromText(
  preview: Record<string, unknown> | null | undefined,
  text: string,
): Record<string, unknown> {
  const type = readPreviewType(preview);
  if (type === "email") {
    return { body: text };
  }
  if (type === "message") {
    return { text };
  }
  if (type === "transaction") {
    return { edited_preview: text };
  }
  return { edited_preview: text };
}

export function GateApprovalCard({
  runId,
  gateId,
  toolId,
  paramsPreview,
  actionLabel,
  preview,
  costEstimateUsd,
  onApprove,
  onReject,
}: GateApprovalCardProps) {
  const [state, setState] = useState<LocalState>("pending");
  const [error, setError] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [draftText, setDraftText] = useState(() => initialEditableText(preview));

  const hasResolvableRun =
    Boolean(String(runId || "").trim()) && String(runId || "").trim() !== "active-run";
  const hasGateId = Boolean(String(gateId || "").trim());
  const canSubmit = hasResolvableRun && hasGateId && Boolean(onApprove) && Boolean(onReject);

  const previewType = readPreviewType(preview);
  const title = String(actionLabel || toolId || "Approval request").trim() || "Approval request";

  const displayBody = useMemo(() => {
    if (!preview) {
      return <p className="mt-1 text-[13px] leading-[1.5] text-[#9a3412]">{paramsPreview}</p>;
    }

    if (previewType === "email") {
      return (
        <div className="mt-2 rounded-xl border border-[#fed7aa] bg-white px-3 py-2 text-[12px] text-[#7c2d12]">
          <p>
            <span className="font-semibold">To:</span> {String(preview.to || "-")}
          </p>
          <p className="mt-0.5">
            <span className="font-semibold">Subject:</span> {String(preview.subject || "-")}
          </p>
          <p className="mt-1 whitespace-pre-wrap text-[#9a3412]">
            {String(preview.body_preview || preview.body || paramsPreview || "")}
          </p>
        </div>
      );
    }

    if (previewType === "message") {
      return (
        <div className="mt-2 rounded-xl border border-[#fed7aa] bg-white px-3 py-2 text-[12px] text-[#7c2d12]">
          <p>
            <span className="font-semibold">Channel:</span> {String(preview.channel || "-")}
          </p>
          <p className="mt-1 whitespace-pre-wrap text-[#9a3412]">
            {String(preview.text_preview || preview.text || paramsPreview || "")}
          </p>
        </div>
      );
    }

    if (previewType === "transaction") {
      return (
        <div className="mt-2 rounded-xl border border-[#fed7aa] bg-white px-3 py-2 text-[12px] text-[#7c2d12]">
          <p className="font-semibold">{String(preview.summary || "Transaction")}</p>
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded-lg bg-[#fff7ed] p-2 text-[11px] text-[#9a3412]">
            {toReadableJson(preview.params_preview || preview)}
          </pre>
        </div>
      );
    }

    return (
      <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-xl border border-[#fed7aa] bg-white px-3 py-2 text-[11px] text-[#9a3412]">
        {toReadableJson(preview.params_preview || preview)}
      </pre>
    );
  }, [paramsPreview, preview, previewType]);

  const approve = async () => {
    if (!canSubmit) {
      setState("error");
      setError("Waiting for active run details before approval can be submitted.");
      return;
    }
    setError("");
    setState("approving");
    try {
      const edited = isEditing ? editedParamsFromText(preview, draftText) : undefined;
      await onApprove?.(runId, gateId, edited);
      setState("approved");
      setIsEditing(false);
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
      setIsEditing(false);
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
      <h3 className="text-[16px] font-semibold text-[#7c2d12]">{title}</h3>
      {displayBody}

      {isEditing ? (
        <div className="mt-3 rounded-xl border border-[#fdba74] bg-white p-2.5">
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#9a3412]">
            Edit before approval
          </p>
          <textarea
            value={draftText}
            onChange={(event) => setDraftText(event.target.value)}
            className="h-28 w-full resize-y rounded-lg border border-[#fed7aa] bg-[#fff7ed] px-2 py-1.5 text-[12px] text-[#7c2d12] outline-none"
          />
        </div>
      ) : null}

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
            disabled={state === "approving" || state === "rejecting"}
            onClick={() => setIsEditing((prev) => !prev)}
            className="inline-flex items-center gap-1 rounded-full border border-[#fdba74] bg-white px-4 py-2 text-[13px] font-semibold text-[#9a3412] hover:bg-[#fff7ed] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Pencil size={12} />
            {isEditing ? "Stop editing" : "Edit"}
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

      {error ? <p className="mt-3 text-[12px] text-[#b91c1c]">{error}</p> : null}
      {!canSubmit ? (
        <p className="mt-2 text-[12px] text-[#92400e]">
          Waiting for live run and gate identifiers...
        </p>
      ) : null}
    </article>
  );
}
