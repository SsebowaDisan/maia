import { AlertTriangle, Bot, ClipboardCheck, FileText, GitBranch, Mail, Search, ShieldCheck, Table2 } from "lucide-react";
import type { NodeProps } from "@xyflow/react";

type WorkGraphNodeRenderData = {
  title: string;
  detail: string;
  nodeType: string;
  status: string;
  role: string;
  confidence: number | null;
  progress: number | null;
  evidenceCount: number;
  artifactCount: number;
  sceneCount: number;
  riskReason?: string | null;
  isActive: boolean;
  onAsk?: (nodeId: string) => void;
  onInspectEvidence?: (nodeId: string) => void;
  onInspectVerifier?: (nodeId: string) => void;
};

function nodeTypeLabel(nodeType: string): string {
  const normalized = String(nodeType || "").trim().toLowerCase();
  if (normalized === "browser_action") {
    return "Browser";
  }
  if (normalized === "document_review") {
    return "Document";
  }
  if (normalized === "email_draft") {
    return "Email";
  }
  if (normalized === "spreadsheet_analysis") {
    return "Sheet";
  }
  if (normalized === "verification") {
    return "Verification";
  }
  if (normalized === "decision") {
    return "Decision";
  }
  if (normalized === "artifact") {
    return "Artifact";
  }
  return "Step";
}

function statusColor(status: string): string {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "completed") {
    return "#16a34a";
  }
  if (normalized === "running") {
    return "#2563eb";
  }
  if (normalized === "failed") {
    return "#dc2626";
  }
  if (normalized === "blocked") {
    return "#ea580c";
  }
  return "#6b7280";
}

function nodeIcon(nodeType: string, role: string) {
  const normalized = String(nodeType || "").trim().toLowerCase();
  if (normalized === "browser_action") {
    return <Search className="h-3.5 w-3.5" />;
  }
  if (normalized === "document_review") {
    return <FileText className="h-3.5 w-3.5" />;
  }
  if (normalized === "email_draft") {
    return <Mail className="h-3.5 w-3.5" />;
  }
  if (normalized === "spreadsheet_analysis") {
    return <Table2 className="h-3.5 w-3.5" />;
  }
  if (normalized === "verification") {
    return <ShieldCheck className="h-3.5 w-3.5" />;
  }
  if (normalized === "decision") {
    return <GitBranch className="h-3.5 w-3.5" />;
  }
  if (normalized === "artifact") {
    return <ClipboardCheck className="h-3.5 w-3.5" />;
  }
  if (String(role || "").trim().toLowerCase() === "system") {
    return <Bot className="h-3.5 w-3.5" />;
  }
  return <GitBranch className="h-3.5 w-3.5" />;
}

function isLowConfidence(value: number | null): boolean {
  return typeof value === "number" && value >= 0 && value < 0.6;
}

function WorkGraphNodeCard({ id, data }: NodeProps<WorkGraphNodeRenderData>) {
  const borderColor = statusColor(data.status);
  const lowConfidence = isLowConfidence(data.confidence);
  const progressValue = typeof data.progress === "number" ? Math.max(0, Math.min(100, data.progress)) : null;
  const riskReason = String(data.riskReason || "").trim();
  const canInspectEvidence = Boolean(data.evidenceCount > 0 && data.onInspectEvidence);
  const canInspectVerifier = Boolean(data.onInspectVerifier && (lowConfidence || riskReason || data.status === "failed"));
  return (
    <div
      className={`min-w-[230px] max-w-[290px] rounded-2xl border bg-white/95 px-3 py-2 shadow-sm ${
        data.isActive ? "ring-2 ring-[#2563eb]/40" : ""
      }`}
      style={{ borderColor }}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-[#8e8e93]">
          {nodeIcon(data.nodeType, data.role)}
          <span>{nodeTypeLabel(data.nodeType)}</span>
        </div>
        <span className="text-[10px] text-[#6e6e73]">{data.role || "system"}</span>
      </div>
      <p className="mt-1 line-clamp-2 text-[13px] font-medium text-[#1d1d1f]">{data.title}</p>
      {data.detail ? <p className="mt-1 line-clamp-2 text-[11px] text-[#6e6e73]">{data.detail}</p> : null}

      {progressValue !== null ? (
        <div className="mt-2">
          <div className="h-1.5 overflow-hidden rounded-full bg-[#e5e7eb]">
            <div className="h-full rounded-full bg-[#2563eb]" style={{ width: `${progressValue}%` }} />
          </div>
        </div>
      ) : null}

      <div className="mt-2 grid grid-cols-2 gap-1 text-[10px] text-[#6e6e73]">
        <span>Status: {data.status || "queued"}</span>
        <span className="text-right">
          Confidence: {typeof data.confidence === "number" ? `${Math.round(data.confidence * 100)}%` : "n/a"}
        </span>
        {canInspectEvidence ? (
          <button
            type="button"
            className="inline-flex items-center justify-start rounded-md border border-black/[0.08] bg-white px-1.5 py-0.5 text-[10px] text-[#1d1d1f] transition hover:bg-[#f5f5f7]"
            onClick={(event) => {
              event.stopPropagation();
              data.onInspectEvidence?.(id);
            }}
            title="Inspect node evidence"
          >
            Evidence: {data.evidenceCount}
          </button>
        ) : (
          <span>Evidence: {data.evidenceCount}</span>
        )}
        <span className="text-right">Artifacts: {data.artifactCount}</span>
      </div>

      {lowConfidence ? (
        <div
          className="mt-2 inline-flex items-center gap-1 rounded-md bg-[#fff7ed] px-2 py-1 text-[10px] text-[#9a3412]"
          title={riskReason || "Confidence below threshold. Inspect evidence and verification details."}
        >
          <AlertTriangle className="h-3 w-3" />
          {riskReason || "Low confidence, needs verification"}
        </div>
      ) : null}

      {canInspectVerifier ? (
        <button
          type="button"
          className="mt-2 rounded-md border border-[#f5a524]/30 bg-[#fff7e6] px-2 py-1 text-[10px] text-[#8a5610] transition hover:bg-[#fff1cc]"
          onClick={(event) => {
            event.stopPropagation();
            data.onInspectVerifier?.(id);
          }}
          title="Open verifier details"
        >
          Verifier details
        </button>
      ) : null}

      {data.onAsk ? (
        <button
          type="button"
          className="mt-2 rounded-md border border-black/[0.08] px-2 py-1 text-[10px] text-[#1d1d1f] transition hover:bg-[#f5f5f7]"
          onClick={(event) => {
            event.stopPropagation();
            data.onAsk?.(id);
          }}
        >
          Ask about this node
        </button>
      ) : null}
    </div>
  );
}

export { WorkGraphNodeCard, isLowConfidence, nodeTypeLabel, statusColor };
export type { WorkGraphNodeRenderData };
