import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  Loader2,
  Settings2,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import {
  listConnectorCredentials,
  upsertConnectorCredentials,
} from "../../../api/client";
import { MANUAL_CONNECTOR_DEFINITIONS } from "../settings/connectorDefinitions";
import type { StepType, WorkflowCanvasEdge, WorkflowCanvasNode, WorkflowCanvasNodeData } from "../../stores/workflowStore";
import { NodeTypePicker } from "./NodeTypePicker";
import { StepTypeConfig } from "./StepTypeConfig";

type StepConfigPanelProps = {
  node: WorkflowCanvasNode | null;
  outgoingEdges: WorkflowCanvasEdge[];
  outputKeyLabels: Record<string, string>;
  onClose: () => void;
  onDeleteNode: (nodeId: string) => void;
  onRequestChangeAgent: (nodeId: string) => void;
  onUpdateNodeData: (nodeId: string, patch: Partial<WorkflowCanvasNodeData>) => void;
  onUpdateEdgeCondition: (edgeId: string, condition: string) => void;
};

// ── Connector row ──────────────────────────────────────────────────────────────

function ConnectorRow({ connectorId, onSaved }: { connectorId: string; onSaved: () => void }) {
  const def = MANUAL_CONNECTOR_DEFINITIONS.find((d) => d.id === connectorId);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [revealed, setRevealed] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);
  const checkedRef = useRef(false);

  useEffect(() => {
    if (checkedRef.current) return;
    checkedRef.current = true;
    listConnectorCredentials()
      .then((records) => {
        const match = records.find((r) => r.connector_id === connectorId);
        const hasValues = match && Object.values(match.values || {}).some((v) => String(v || "").length > 0);
        setConnected(Boolean(hasValues) || !def || def.fields.length === 0);
      })
      .catch(() => setConnected(false));
  }, [connectorId, def]);

  const label = def?.label || connectorId;
  const isPublic = !def || def.fields.length === 0;
  const statusDot = connected === null ? "bg-[#d0d5dd]" : connected ? "bg-[#17b26a]" : "bg-[#f04438]";

  const handleSave = async () => {
    setSaving(true);
    try {
      await upsertConnectorCredentials(connectorId, draft);
      setConnected(true);
      setExpanded(false);
      toast.success(`${label} connected`);
      onSaved();
    } catch {
      toast.error(`Failed to save ${label} credentials`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="rounded-xl border border-black/[0.08] bg-white">
      <button
        type="button"
        disabled={isPublic || connected === true}
        onClick={() => !isPublic && setExpanded((o) => !o)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left disabled:cursor-default"
      >
        <span className={`h-2 w-2 shrink-0 rounded-full ${statusDot}`} />
        <span className="flex-1 text-[13px] font-medium text-[#101828]">{label}</span>
        {connected === null ? (
          <Loader2 size={12} className="shrink-0 animate-spin text-[#98a2b3]" />
        ) : connected ? (
          <CheckCircle2 size={14} className="shrink-0 text-[#17b26a]" />
        ) : (
          <span className="shrink-0 text-[11px] font-semibold text-[#1d4ed8]">
            {expanded ? "Cancel" : "Connect"}
          </span>
        )}
      </button>

      {expanded && !isPublic && def ? (
        <div className="border-t border-black/[0.06] px-3 pb-3 pt-2.5">
          <div className="space-y-2">
            {def.fields.map((field) => (
              <label key={field.key} className="block">
                <span className="mb-1 block text-[11px] font-medium text-[#475467]">{field.label}</span>
                <div className="flex items-center gap-1.5">
                  <input
                    type={field.sensitive && !revealed[field.key] ? "password" : "text"}
                    value={draft[field.key] || ""}
                    onChange={(e) => setDraft((prev) => ({ ...prev, [field.key]: e.target.value }))}
                    placeholder={field.placeholder}
                    autoComplete="off"
                    className="min-w-0 flex-1 rounded-lg border border-black/[0.12] bg-[#f8fafc] px-2.5 py-1.5 text-[12px] text-[#101828] outline-none focus:border-[#94a3b8]"
                  />
                  {field.sensitive ? (
                    <button
                      type="button"
                      onClick={() => setRevealed((r) => ({ ...r, [field.key]: !r[field.key] }))}
                      className="shrink-0 text-[#98a2b3] hover:text-[#475467]"
                    >
                      {revealed[field.key] ? <EyeOff size={13} /> : <Eye size={13} />}
                    </button>
                  ) : null}
                </div>
              </label>
            ))}
          </div>
          <button
            type="button"
            disabled={saving}
            onClick={handleSave}
            className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-xl bg-[#111827] px-3 py-2 text-[12px] font-semibold text-white transition-colors hover:bg-[#1d2939] disabled:opacity-55"
          >
            {saving ? <Loader2 size={12} className="animate-spin" /> : null}
            Save & connect
          </button>
        </div>
      ) : null}
    </div>
  );
}

// ── Main panel ────────────────────────────────────────────────────────────────

function agentMonogram(name: string): string {
  const t = String(name || "").trim();
  return t ? t.charAt(0).toUpperCase() : "A";
}

const EDGE_CONDITION_ALLOWED_PATTERN = /^[A-Za-z0-9_\s().<>=!&|+\-*/%:'",]+$/;
function hasBalancedParentheses(v: string) {
  let b = 0;
  for (const c of v) { if (c === "(") b++; else if (c === ")") { b--; if (b < 0) return false; } }
  return b === 0;
}
function validateCondition(value: string): string {
  const n = String(value || "").trim();
  if (!n) return "";
  if (n.length > 220) return "Condition is too long (max 220 chars).";
  if (!EDGE_CONDITION_ALLOWED_PATTERN.test(n)) return "Condition has unsupported characters.";
  if (!hasBalancedParentheses(n)) return "Condition has unmatched parentheses.";
  return "";
}

function StepConfigPanel({
  node,
  outgoingEdges,
  outputKeyLabels,
  onClose,
  onDeleteNode,
  onRequestChangeAgent,
  onUpdateNodeData,
  onUpdateEdgeCondition,
}: StepConfigPanelProps) {
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [inputDescription, setInputDescription] = useState("");
  const [outputDescription, setOutputDescription] = useState("");
  const [conditionValues, setConditionValues] = useState<Record<string, string>>({});
  const [conditionErrors, setConditionErrors] = useState<Record<string, string>>({});
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [connectorRefreshKey, setConnectorRefreshKey] = useState(0);

  // Reset form fields only when the selected node IDENTITY changes, not on data updates.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!node) {
      setLabel("");
      setDescription("");
      setInputDescription("");
      setOutputDescription("");
      setAdvancedOpen(false);
      return;
    }
    setLabel(node.data.label || "");
    setDescription(node.data.description || "");
    setInputDescription(node.data.inputDescription || "");
    setOutputDescription(node.data.outputDescription || "");
  }, [node?.id]);

  // Sync condition values when the node or its outgoing edges change.
  useEffect(() => {
    if (!node) {
      setConditionValues({});
      setConditionErrors({});
      return;
    }
    const nextConditionValues: Record<string, string> = {};
    for (const edge of outgoingEdges) {
      nextConditionValues[edge.id] = String(edge.condition || "");
    }
    setConditionValues(nextConditionValues);
    setConditionErrors({});
  }, [node?.id, outgoingEdges]);

  if (!node) return null;

  const handleDone = () => {
    // Flush any pending field changes that might not have blurred yet
    onUpdateNodeData(node.id, { label, description, inputDescription, outputDescription });
    onClose();
  };

  const agentName = String(node.data.agentName || node.data.agentId || "").trim();
  const agentDescription = String(node.data.agentDescription || "").trim();
  const agentTags = Array.isArray(node.data.agentTags)
    ? node.data.agentTags.map((tag) => String(tag || "").trim()).filter(Boolean)
    : [];
  const requiredConnectors = Array.isArray(node.data.requiredConnectors)
    ? node.data.requiredConnectors.filter(Boolean)
    : [];
  const monogram = agentMonogram(agentName);
  const isTrigger = node.type === "trigger";
  const isOutput = node.type === "output";

  // Only show edge conditions when there are multiple outgoing edges (branching)
  const showConditions = outgoingEdges.length > 1;

  return (
    <aside className="flex h-full w-[340px] shrink-0 flex-col overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-[0_8px_32px_-12px_rgba(15,23,42,0.18)]">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-black/[0.06] bg-[#fcfcfd] px-4 py-3">
        <p className="text-[13px] font-semibold text-[#101828]">Configure step</p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleDone}
            className="rounded-full bg-[#111827] px-3.5 py-1.5 text-[12px] font-semibold text-white transition-colors hover:bg-[#1d2939]"
          >
            Done
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-black/[0.08] p-1.5 text-[#475467] hover:bg-[#f2f4f7]"
            aria-label="Close"
          >
            <X size={13} />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-4 px-4 py-4">

          {/* Step type selector */}
          <NodeTypePicker
            value={(node.data.stepType || "agent") as StepType}
            onChange={(type) => onUpdateNodeData(node.id, { stepType: type })}
          />

          {/* Agent card — only shown for agent step type */}
          {(!node.data.stepType || node.data.stepType === "agent") ? (
            <div className="rounded-2xl border border-black/[0.08] bg-[#f8fafc] p-3">
              <div className="flex items-start gap-3">
                <div className="inline-flex aspect-square w-12 shrink-0 items-center justify-center rounded-xl border border-black/[0.08] bg-gradient-to-br from-white to-[#e8eef8] text-[17px] font-bold text-[#344054] shadow-sm">
                  {monogram}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[14px] font-semibold leading-snug text-[#101828]">
                    {agentName || "No agent selected"}
                  </p>
                  {agentDescription ? (
                    <p className="mt-1 line-clamp-3 text-[12px] leading-[1.55] text-[#667085]">
                      {agentDescription}
                    </p>
                  ) : null}
                  {agentTags.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {agentTags.slice(0, 4).map((tag) => (
                        <span
                          key={`${node.id}:${tag}`}
                          className="rounded-full border border-black/[0.08] bg-white px-2 py-0.5 text-[10px] font-medium text-[#475467]"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
              <button
                type="button"
                onClick={() => onRequestChangeAgent(node.id)}
                className="mt-3 w-full rounded-xl border border-black/[0.12] bg-white px-3 py-2 text-[12px] font-semibold text-[#344054] transition-colors hover:bg-[#f2f4f7]"
              >
                Change agent
              </button>
            </div>
          ) : null}

          {/* Step-type-specific config */}
          <StepTypeConfig
            stepType={(node.data.stepType || "agent") as StepType}
            stepConfig={(node.data.stepConfig || {}) as Record<string, unknown>}
            onChange={(cfg) => onUpdateNodeData(node.id, { stepConfig: cfg })}
          />

          {/* Connected accounts */}
          {requiredConnectors.length > 0 ? (
            <div>
              <p className="mb-2 text-[12px] font-semibold text-[#344054]">Connected accounts</p>
              <div className="space-y-2">
                {requiredConnectors.map((connectorId) => (
                  <ConnectorRow
                    key={`${node.id}:${connectorId}:${connectorRefreshKey}`}
                    connectorId={connectorId}
                    onSaved={() => setConnectorRefreshKey((k) => k + 1)}
                  />
                ))}
              </div>
            </div>
          ) : null}

          {/* Step name */}
          <label className="block">
            <div className="mb-1.5 flex items-baseline justify-between">
              <span className="text-[12px] font-semibold text-[#344054]">Step name</span>
              <span className={`text-[10px] ${label.length > 72 ? "text-[#f59e0b]" : "text-[#aeaeb2]"}`}>
                {label.length}/80
              </span>
            </div>
            <textarea
              value={label}
              onChange={(event) => setLabel(event.target.value.slice(0, 80))}
              onBlur={() => onUpdateNodeData(node.id, { label })}
              placeholder="e.g. Analyze sales data"
              maxLength={80}
              rows={2}
              className="w-full resize-none rounded-xl border border-black/[0.12] px-3 py-2.5 text-[13px] text-[#101828] outline-none focus:border-[#94a3b8]"
            />
          </label>

          {/* Input format — trigger (first) node */}
          {isTrigger ? (
            <label className="block">
              <div className="mb-1.5 flex items-baseline justify-between">
                <span className="text-[12px] font-semibold text-[#344054]">Input format</span>
                <span className={`text-[10px] ${inputDescription.length > 180 ? "text-[#f59e0b]" : "text-[#aeaeb2]"}`}>
                  {inputDescription.length}/200
                </span>
              </div>
              <span className="mb-2 block text-[11px] text-[#86868b]">
                What type of input will this workflow receive?
              </span>
              <textarea
                value={inputDescription}
                onChange={(event) => setInputDescription(event.target.value.slice(0, 200))}
                onBlur={() => onUpdateNodeData(node.id, { inputDescription })}
                placeholder="e.g. PDF documents, images (PNG/JPG), plain text, CSV files, URLs…"
                maxLength={200}
                rows={2}
                className="w-full resize-none rounded-xl border border-[#c7d2fe] bg-[#f5f3ff] px-3 py-2.5 text-[13px] text-[#101828] outline-none placeholder:text-[#a5b4fc] focus:border-[#818cf8]"
              />
            </label>
          ) : null}

          {/* Output format — output (last) node */}
          {isOutput ? (
            <label className="block">
              <div className="mb-1.5 flex items-baseline justify-between">
                <span className="text-[12px] font-semibold text-[#344054]">Output format</span>
                <span className={`text-[10px] ${outputDescription.length > 180 ? "text-[#f59e0b]" : "text-[#aeaeb2]"}`}>
                  {outputDescription.length}/200
                </span>
              </div>
              <span className="mb-2 block text-[11px] text-[#86868b]">
                Describe the expected output — language, length, structure, etc.
              </span>
              <textarea
                value={outputDescription}
                onChange={(event) => setOutputDescription(event.target.value.slice(0, 200))}
                onBlur={() => onUpdateNodeData(node.id, { outputDescription })}
                placeholder="e.g. Summary in French, max 500 words, markdown format, JSON with specific fields…"
                maxLength={200}
                rows={2}
                className="w-full resize-none rounded-xl border border-[#a7f3d0] bg-[#ecfdf5] px-3 py-2.5 text-[13px] text-[#101828] outline-none placeholder:text-[#6ee7b7] focus:border-[#34d399]"
              />
            </label>
          ) : null}

          {/* Step instructions */}
          <label className="block">
            <div className="mb-1.5 flex items-baseline justify-between">
              <span className="text-[12px] font-semibold text-[#344054]">
                Instructions{" "}
                <span className="font-normal text-[#98a2b3]">(optional)</span>
              </span>
              <span className={`text-[10px] ${description.length > 450 ? "text-[#f59e0b]" : "text-[#aeaeb2]"}`}>
                {description.length}/500
              </span>
            </div>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value.slice(0, 500))}
              onBlur={() => onUpdateNodeData(node.id, { description })}
              placeholder="Describe what you want this step to accomplish…"
              maxLength={500}
              rows={3}
              className="w-full resize-none rounded-xl border border-black/[0.12] px-3 py-2.5 text-[13px] text-[#101828] outline-none focus:border-[#94a3b8]"
            />
          </label>

          {/* Edge conditions — only for branching workflows (>1 outgoing edge) */}
          {showConditions ? (
            <div>
              <p className="mb-1.5 text-[12px] font-semibold text-[#344054]">Branch conditions</p>
              <p className="mb-2 text-[11px] text-[#667085]">
                Set a condition for each path. Only the matching path will run.
              </p>
              <div className="space-y-2">
                {outgoingEdges.map((edge) => {
                  const targetLabel = outputKeyLabels[edge.target] || edge.target;
                  return (
                    <label key={edge.id} className="block">
                      <span className="mb-1 block text-[11px] font-medium text-[#475467]">
                        If… → {targetLabel}
                      </span>
                      <input
                        value={conditionValues[edge.id] ?? ""}
                        onChange={(event) => {
                          const v = event.target.value;
                          setConditionValues((prev) => ({ ...prev, [edge.id]: v }));
                          if (conditionErrors[edge.id]) {
                            setConditionErrors((prev) => ({ ...prev, [edge.id]: "" }));
                          }
                        }}
                        onBlur={(event) => {
                          const v = event.target.value;
                          const err = validateCondition(v);
                          if (err) { setConditionErrors((prev) => ({ ...prev, [edge.id]: err })); return; }
                          setConditionErrors((prev) => ({ ...prev, [edge.id]: "" }));
                          onUpdateEdgeCondition(edge.id, v.trim());
                        }}
                        placeholder="e.g. score > 0.8"
                        className={`w-full rounded-xl border px-3 py-2 text-[12px] text-[#101828] outline-none focus:border-[#94a3b8] ${
                          conditionErrors[edge.id] ? "border-[#fca5a5] bg-[#fff1f2]" : "border-black/[0.12]"
                        }`}
                      />
                      {conditionErrors[edge.id] ? (
                        <p className="mt-1 text-[11px] text-[#b42318]">{conditionErrors[edge.id]}</p>
                      ) : null}
                    </label>
                  );
                })}
              </div>
            </div>
          ) : null}

          {/* Advanced — for developers only */}
          <button
            type="button"
            onClick={() => setAdvancedOpen((o) => !o)}
            className="flex w-full items-center gap-2 rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[12px] font-semibold text-[#667085] transition-colors hover:bg-[#f2f4f7]"
          >
            <Settings2 size={12} className="shrink-0 text-[#98a2b3]" />
            <span className="flex-1 text-left text-[11px]">Developer settings</span>
            {advancedOpen ? (
              <ChevronDown size={12} className="shrink-0 text-[#98a2b3]" />
            ) : (
              <ChevronRight size={12} className="shrink-0 text-[#98a2b3]" />
            )}
          </button>

          {advancedOpen ? (
            <div className="space-y-3 rounded-xl border border-black/[0.08] bg-[#fcfcfd] p-3 text-[12px]">
              <div>
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.09em] text-[#98a2b3]">Output key</p>
                <p className="font-mono text-[12px] text-[#475467]">{node.data.outputKey || "—"}</p>
              </div>
              <div className="flex gap-3">
                <label className="block flex-1">
                  <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.09em] text-[#98a2b3]">Timeout (s)</span>
                  <input type="number" value={node.data.timeoutS || 300} onChange={(e) => onUpdateNodeData(node.id, { timeoutS: Number(e.target.value) || 300 })} className="w-full rounded-lg border border-black/[0.08] px-2 py-1 font-mono text-[12px] text-[#475467] outline-none" />
                </label>
                <label className="block flex-1">
                  <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.09em] text-[#98a2b3]">Max retries</span>
                  <input type="number" min={0} max={5} value={node.data.maxRetries || 0} onChange={(e) => onUpdateNodeData(node.id, { maxRetries: Number(e.target.value) || 0 })} className="w-full rounded-lg border border-black/[0.08] px-2 py-1 font-mono text-[12px] text-[#475467] outline-none" />
                </label>
              </div>
              <div>
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.09em] text-[#98a2b3]">Raw input mapping</p>
                <pre className="whitespace-pre-wrap break-all font-mono text-[11px] text-[#475467]">
                  {Object.entries(node.data.inputMapping || {}).map(([k, v]) => `${k}=${v}`).join("\n") || "—"}
                </pre>
              </div>
            </div>
          ) : null}

          {/* Remove step */}
          <button
            type="button"
            onClick={() => onDeleteNode(node.id)}
            className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl border border-black/[0.08] px-3 py-2 text-[12px] font-medium text-[#667085] transition-colors hover:border-[#fecaca] hover:bg-[#fff1f2] hover:text-[#b42318]"
          >
            <Trash2 size={13} />
            Remove step
          </button>

        </div>
      </div>
    </aside>
  );
}

export { StepConfigPanel };
export type { StepConfigPanelProps };
