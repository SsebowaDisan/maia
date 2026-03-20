"use client";

import { useMemo, useState } from "react";
import { Loader2, Pencil, ShieldAlert, X } from "lucide-react";

type ApprovalGateCardProps = {
  trustScore: number;
  gateColor: "amber" | "red";
  reason: string;
  actionLabel?: string;
  paramsPreview?: string;
  preview?: Record<string, unknown> | null;
  onApprove: (editedPreviewText?: string) => Promise<void> | void;
  onReject: () => Promise<void> | void;
  onCancel: () => void;
};

const GATE_RING: Record<ApprovalGateCardProps["gateColor"], string> = {
  amber: "border-[#ff9f0a]/60 shadow-[0_0_40px_rgba(255,159,10,0.35)]",
  red: "border-[#ff3b30]/60 shadow-[0_0_40px_rgba(255,59,48,0.35)]",
};

const GATE_LABEL: Record<ApprovalGateCardProps["gateColor"], string> = {
  amber: "Moderate confidence",
  red: "Low confidence - review required",
};

function toText(value: unknown): string {
  return String(value || "").trim();
}

function toPreviewType(preview: Record<string, unknown> | null | undefined): string {
  return toText(preview?.type).toLowerCase();
}

function toJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value || "");
  }
}

function readInitialDraft(preview: Record<string, unknown> | null | undefined, paramsPreview: string): string {
  if (!preview) {
    return paramsPreview;
  }
  const type = toPreviewType(preview);
  if (type === "email") {
    return toText(preview.body_preview || preview.body || paramsPreview);
  }
  if (type === "message") {
    return toText(preview.text_preview || preview.text || paramsPreview);
  }
  return toJson(preview.params_preview || preview);
}

function renderPreviewCard(
  preview: Record<string, unknown> | null | undefined,
  paramsPreview: string,
): React.ReactNode {
  if (!preview) {
    return (
      <p className="mt-2 rounded-xl border border-[#fed7aa] bg-white px-3 py-2 text-[12px] text-[#9a3412]">
        {paramsPreview || "No action preview was provided."}
      </p>
    );
  }
  const type = toPreviewType(preview);
  if (type === "email") {
    return (
      <div className="mt-2 rounded-xl border border-[#fed7aa] bg-white px-3 py-2 text-[12px] text-[#9a3412]">
        <p><span className="font-semibold">To:</span> {toText(preview.to || "-")}</p>
        <p className="mt-0.5"><span className="font-semibold">Subject:</span> {toText(preview.subject || "-")}</p>
        <p className="mt-1 whitespace-pre-wrap">{toText(preview.body_preview || preview.body || paramsPreview)}</p>
      </div>
    );
  }
  if (type === "message") {
    return (
      <div className="mt-2 rounded-xl border border-[#fed7aa] bg-white px-3 py-2 text-[12px] text-[#9a3412]">
        <p><span className="font-semibold">Channel:</span> {toText(preview.channel || "-")}</p>
        <p className="mt-1 whitespace-pre-wrap">{toText(preview.text_preview || preview.text || paramsPreview)}</p>
      </div>
    );
  }
  if (type === "transaction") {
    return (
      <div className="mt-2 rounded-xl border border-[#fed7aa] bg-white px-3 py-2 text-[12px] text-[#9a3412]">
        <p className="font-semibold">{toText(preview.summary || "Transaction preview")}</p>
        <pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded-lg bg-[#fff7ed] p-2 text-[11px]">
          {toJson(preview.params_preview || preview)}
        </pre>
      </div>
    );
  }
  return (
    <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-xl border border-[#fed7aa] bg-white px-3 py-2 text-[11px] text-[#9a3412]">
      {toJson(preview.params_preview || preview)}
    </pre>
  );
}

function ApprovalGateCard({
  trustScore,
  gateColor,
  reason,
  actionLabel,
  paramsPreview = "",
  preview,
  onApprove,
  onReject,
  onCancel,
}: ApprovalGateCardProps) {
  const pct = Math.round(Math.max(0, Math.min(1, trustScore)) * 100);
  const [mode, setMode] = useState<"idle" | "approving" | "rejecting">("idle");
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(() => readInitialDraft(preview, paramsPreview));
  const [error, setError] = useState("");

  const actionTitle = useMemo(
    () => toText(actionLabel || preview?.action_label || preview?.tool_id || "Pending action"),
    [actionLabel, preview],
  );

  const approve = async () => {
    setError("");
    setMode("approving");
    try {
      await onApprove(isEditing ? draft : undefined);
    } catch (nextError) {
      setError(String(nextError || "Failed to approve."));
    } finally {
      setMode("idle");
    }
  };

  const reject = async () => {
    setError("");
    setMode("rejecting");
    try {
      await onReject();
    } catch (nextError) {
      setError(String(nextError || "Failed to reject."));
    } finally {
      setMode("idle");
    }
  };

  const busy = mode !== "idle";

  return (
    <>
      <div
        className="fixed inset-0 z-[9800]"
        style={{ backdropFilter: "brightness(0.4)" }}
        onClick={onCancel}
      />

      <div
        className={`fixed left-1/2 top-1/2 z-[9900] w-[min(560px,calc(100%-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-2xl border-2 bg-white p-5 ${GATE_RING[gateColor]}`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 text-[#92400e]">
            <ShieldAlert size={16} />
            <p className="text-[12px] font-semibold uppercase tracking-[0.1em]">Approval required</p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-full border border-black/[0.1] p-1.5 text-[#667085] hover:bg-[#f8fafc]"
            aria-label="Close approval modal"
          >
            <X size={14} />
          </button>
        </div>

        <h3 className="mt-2 text-[16px] font-semibold text-[#7c2d12]">{actionTitle || "Pending action"}</h3>
        <p className={`mt-1 text-[12px] font-semibold ${gateColor === "amber" ? "text-[#7a4800]" : "text-[#8b1a14]"}`}>
          {GATE_LABEL[gateColor]} - Trust score: {pct}%
        </p>
        <p className="mt-1 rounded-xl border border-black/[0.08] bg-[#f7f7f9] px-3 py-2 text-[12px] text-[#3a3a3c]">
          {reason || "One or more claims could not be fully verified."}
        </p>

        {renderPreviewCard(preview, paramsPreview)}

        {isEditing ? (
          <div className="mt-3 rounded-xl border border-[#fdba74] bg-white p-2.5">
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-[#9a3412]">
              Edit preview before approval
            </p>
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="h-28 w-full resize-y rounded-lg border border-[#fed7aa] bg-[#fff7ed] px-2 py-1.5 text-[12px] text-[#7c2d12] outline-none"
            />
          </div>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              void approve();
            }}
            className={`rounded-full px-4 py-2 text-[13px] font-semibold text-white disabled:opacity-60 ${
              gateColor === "amber"
                ? "bg-[#ff9f0a] hover:bg-[#e08c00]"
                : "bg-[#ff3b30] hover:bg-[#cc2e25]"
            }`}
          >
            {mode === "approving" ? (
              <span className="inline-flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Approving...</span>
            ) : "Approve"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => setIsEditing((prev) => !prev)}
            className="inline-flex items-center gap-1 rounded-full border border-[#fdba74] bg-white px-4 py-2 text-[13px] font-semibold text-[#9a3412] hover:bg-[#fff7ed] disabled:opacity-60"
          >
            <Pencil size={12} />
            {isEditing ? "Stop editing" : "Edit"}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              void reject();
            }}
            className="rounded-full border border-[#b91c1c]/30 bg-white px-4 py-2 text-[13px] font-semibold text-[#b91c1c] hover:bg-[#fff1f2] disabled:opacity-60"
          >
            {mode === "rejecting" ? (
              <span className="inline-flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Rejecting...</span>
            ) : "Reject"}
          </button>
        </div>

        {error ? <p className="mt-2 text-[12px] text-[#b42318]">{error}</p> : null}
      </div>
    </>
  );
}

export { ApprovalGateCard };
