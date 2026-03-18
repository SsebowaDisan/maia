import { useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Settings2,
  Trash2,
  X,
} from "lucide-react";

import type { WorkflowCanvasEdge, WorkflowCanvasNode, WorkflowCanvasNodeData } from "../../stores/workflowStore";
import { ConnectorRow } from "./ConnectorRow";

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
            className="rounded-full bg-[#7c3aed] px-3.5 py-1.5 text-[12px] font-semibold text-white transition-colors hover:bg-[#6d28d9]"
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
        {/* ── TRIGGER (Input) node — distinct purple theme ─────────────── */}
        {isTrigger ? (
          <div className="space-y-4 px-4 py-4">
            <div className="rounded-2xl border border-[#c7d2fe] bg-gradient-to-b from-[#ede9fe] to-[#f5f3ff] p-4">
              <p className="text-[15px] font-semibold text-[#4338ca]">Workflow input</p>
              <p className="mt-1.5 text-[12px] leading-relaxed text-[#5b51a3]">
                This is where your workflow begins. When you run it, a message will appear in the chat — you can type instructions, ask a question, or attach documents before sending.
              </p>
            </div>

            <label className="block">
              <span className="mb-1 block text-[12px] font-semibold text-[#344054]">Step name</span>
              <input
                value={label}
                onChange={(event) => setLabel(event.target.value.slice(0, 80))}
                onBlur={() => onUpdateNodeData(node.id, { label })}
                placeholder="e.g. Receive research topic"
                maxLength={80}
                className="w-full rounded-xl border border-[#c7d2fe] bg-white px-3 py-2.5 text-[13px] text-[#101828] outline-none focus:border-[#818cf8]"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-[12px] font-semibold text-[#344054]">
                Instructions for this step <span className="font-normal text-[#98a2b3]">(optional)</span>
              </span>
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value.slice(0, 500))}
                onBlur={() => onUpdateNodeData(node.id, { description })}
                placeholder="e.g. Accept the user's question and any attached documents…"
                maxLength={500}
                rows={3}
                className="w-full resize-none rounded-xl border border-[#c7d2fe] bg-white px-3 py-2.5 text-[13px] text-[#101828] outline-none placeholder:text-[#a5b4fc] focus:border-[#818cf8]"
              />
            </label>

            <button
              type="button"
              onClick={() => onDeleteNode(node.id)}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl border border-black/[0.08] px-3 py-2 text-[12px] font-medium text-[#667085] transition-colors hover:border-[#fecaca] hover:bg-[#fff1f2] hover:text-[#b42318]"
            >
              <Trash2 size={13} />
              Remove step
            </button>
          </div>

        /* ── OUTPUT node — distinct green theme ──────────────────────── */
        ) : isOutput ? (
          <div className="space-y-4 px-4 py-4">
            <div className="rounded-2xl border border-[#a7f3d0] bg-gradient-to-b from-[#d1fae5] to-[#ecfdf5] p-4">
              <p className="text-[15px] font-semibold text-[#065f46]">Workflow output</p>
              <p className="mt-1.5 text-[12px] leading-relaxed text-[#047857]">
                This is the final step. Describe what the finished result should look like — the format, language, length, or structure you need.
              </p>
            </div>

            <label className="block">
              <span className="mb-1 block text-[12px] font-semibold text-[#344054]">Step name</span>
              <input
                value={label}
                onChange={(event) => setLabel(event.target.value.slice(0, 80))}
                onBlur={() => onUpdateNodeData(node.id, { label })}
                placeholder="e.g. Final report"
                maxLength={80}
                className="w-full rounded-xl border border-[#a7f3d0] bg-white px-3 py-2.5 text-[13px] text-[#101828] outline-none focus:border-[#34d399]"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-[12px] font-semibold text-[#344054]">What should the output look like?</span>
              <textarea
                value={outputDescription}
                onChange={(event) => setOutputDescription(event.target.value.slice(0, 300))}
                onBlur={() => onUpdateNodeData(node.id, { outputDescription })}
                placeholder="e.g. A markdown report with citations, max 1000 words, in English…"
                maxLength={300}
                rows={3}
                className="w-full resize-none rounded-xl border border-[#a7f3d0] bg-white px-3 py-2.5 text-[13px] text-[#101828] outline-none placeholder:text-[#6ee7b7] focus:border-[#34d399]"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-[12px] font-semibold text-[#344054]">
                Additional instructions <span className="font-normal text-[#98a2b3]">(optional)</span>
              </span>
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value.slice(0, 500))}
                onBlur={() => onUpdateNodeData(node.id, { description })}
                placeholder="e.g. Include source references, use bullet points for key findings…"
                maxLength={500}
                rows={2}
                className="w-full resize-none rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2.5 text-[13px] text-[#101828] outline-none focus:border-[#94a3b8]"
              />
            </label>

            {agentName ? (
              <div className="rounded-xl border border-[#a7f3d0] bg-white px-3 py-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#a7f3d0] bg-[#ecfdf5] text-[13px] font-bold text-[#065f46]">
                    {monogram}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-[#101828]">{agentName}</p>
                  </div>
                  <button type="button" onClick={() => onRequestChangeAgent(node.id)} className="shrink-0 text-[11px] font-semibold text-[#059669] hover:text-[#047857]">Change</button>
                </div>
              </div>
            ) : null}

            <button
              type="button"
              onClick={() => onDeleteNode(node.id)}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl border border-black/[0.08] px-3 py-2 text-[12px] font-medium text-[#667085] transition-colors hover:border-[#fecaca] hover:bg-[#fff1f2] hover:text-[#b42318]"
            >
              <Trash2 size={13} />
              Remove step
            </button>
          </div>

        /* ── REGULAR step — neutral theme ────────────────────────────── */
        ) : (
          <div className="space-y-4 px-4 py-4">

            <label className="block">
              <span className="mb-2 block text-[13px] font-semibold text-[#101828]">
                What should this step do?
              </span>
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value.slice(0, 500))}
                onBlur={() => onUpdateNodeData(node.id, { description })}
                placeholder="e.g. Search my documents for relevant information, then summarize the key findings…"
                maxLength={500}
                rows={4}
                autoFocus
                className="w-full resize-none rounded-xl border border-black/[0.12] px-3 py-2.5 text-[13px] leading-relaxed text-[#101828] outline-none placeholder:text-[#b0b0b6] focus:border-[#7c3aed]"
              />
              <span className={`mt-1 block text-right text-[10px] ${description.length > 450 ? "text-[#f59e0b]" : "text-[#d0d5dd]"}`}>
                {description.length}/500
              </span>
            </label>

            <label className="block">
              <span className="mb-1 block text-[12px] font-medium text-[#667085]">Step name</span>
              <input
                value={label}
                onChange={(event) => setLabel(event.target.value.slice(0, 80))}
                onBlur={() => onUpdateNodeData(node.id, { label })}
                placeholder="Give this step a short name…"
                maxLength={80}
                className="w-full rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[13px] text-[#101828] outline-none focus:border-[#94a3b8]"
              />
            </label>

            {agentName ? (
              <div className="rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-black/[0.08] bg-white text-[13px] font-bold text-[#344054]">
                    {monogram}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-medium text-[#101828]">{agentName}</p>
                    {agentDescription ? (
                      <p className="line-clamp-1 text-[11px] text-[#667085]">{agentDescription}</p>
                    ) : null}
                  </div>
                  <button type="button" onClick={() => onRequestChangeAgent(node.id)} className="shrink-0 text-[11px] font-semibold text-[#7c3aed] hover:text-[#6d28d9]">Change</button>
                </div>
              </div>
            ) : null}

            {requiredConnectors.length > 0 ? (
              <div>
                <p className="mb-2 text-[12px] font-medium text-[#667085]">Connected accounts</p>
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
                        <span className="mb-1 block text-[11px] font-medium text-[#475467]">If… → {targetLabel}</span>
                        <input
                          value={conditionValues[edge.id] ?? ""}
                          onChange={(event) => {
                            const v = event.target.value;
                            setConditionValues((prev) => ({ ...prev, [edge.id]: v }));
                            if (conditionErrors[edge.id]) setConditionErrors((prev) => ({ ...prev, [edge.id]: "" }));
                          }}
                          onBlur={(event) => {
                            const v = event.target.value;
                            const err = validateCondition(v);
                            if (err) { setConditionErrors((prev) => ({ ...prev, [edge.id]: err })); return; }
                            setConditionErrors((prev) => ({ ...prev, [edge.id]: "" }));
                            onUpdateEdgeCondition(edge.id, v.trim());
                          }}
                          placeholder="e.g. score > 0.8"
                          className={`w-full rounded-xl border px-3 py-2 text-[12px] text-[#101828] outline-none focus:border-[#94a3b8] ${conditionErrors[edge.id] ? "border-[#fca5a5] bg-[#fff1f2]" : "border-black/[0.12]"}`}
                        />
                        {conditionErrors[edge.id] ? <p className="mt-1 text-[11px] text-[#b42318]">{conditionErrors[edge.id]}</p> : null}
                      </label>
                    );
                  })}
                </div>
              </div>
            ) : null}

            {/* Behaviour settings */}
            <button
              type="button"
              onClick={() => setAdvancedOpen((o) => !o)}
              className="flex w-full items-center gap-2 rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2.5 text-[12px] font-semibold text-[#667085] transition-colors hover:bg-[#f2f4f7]"
            >
              <Settings2 size={13} className="shrink-0 text-[#98a2b3]" />
              <span className="flex-1 text-left">Behaviour settings</span>
              {advancedOpen ? <ChevronDown size={12} className="shrink-0 text-[#98a2b3]" /> : <ChevronRight size={12} className="shrink-0 text-[#98a2b3]" />}
            </button>

            {advancedOpen ? (
              <div className="space-y-4 rounded-xl border border-black/[0.08] bg-[#fcfcfd] p-3.5">
                <label className="block">
                  <span className="mb-1 block text-[12px] font-semibold text-[#344054]">Time limit</span>
                  <span className="mb-2 block text-[11px] text-[#667085]">How long this step can run before it stops automatically.</span>
                  <div className="flex items-center gap-2">
                    <input type="number" min={10} max={3600} value={node.data.timeoutS || 300} onChange={(e) => onUpdateNodeData(node.id, { timeoutS: Math.max(10, Math.min(3600, Number(e.target.value) || 300)) })} className="w-20 rounded-lg border border-black/[0.10] bg-white px-2.5 py-1.5 text-[13px] text-[#101828] outline-none focus:border-[#94a3b8]" />
                    <span className="text-[12px] text-[#667085]">seconds</span>
                    <span className="ml-auto text-[11px] text-[#98a2b3]">≈ {Math.round((node.data.timeoutS || 300) / 60)} min</span>
                  </div>
                </label>
                <div>
                  <span className="mb-1 block text-[12px] font-semibold text-[#344054]">Retry on failure</span>
                  <span className="mb-2 block text-[11px] text-[#667085]">If this step fails, how many times should it try again?</span>
                  <div className="flex gap-1.5">
                    {([{ value: 0, label: "Don\u2019t retry" }, { value: 1, label: "Once" }, { value: 2, label: "2 times" }, { value: 3, label: "3 times" }] as const).map((opt) => (
                      <button key={opt.value} type="button" onClick={() => onUpdateNodeData(node.id, { maxRetries: opt.value })} className={`rounded-lg border px-2.5 py-1.5 text-[12px] font-medium transition-colors ${(node.data.maxRetries || 0) === opt.value ? "border-[#7c3aed] bg-[#f5f3ff] text-[#7c3aed]" : "border-black/[0.08] bg-white text-[#475467] hover:bg-[#f8fafc]"}`}>{opt.label}</button>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}

            <button
              type="button"
              onClick={() => onDeleteNode(node.id)}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl border border-black/[0.08] px-3 py-2 text-[12px] font-medium text-[#667085] transition-colors hover:border-[#fecaca] hover:bg-[#fff1f2] hover:text-[#b42318]"
            >
              <Trash2 size={13} />
              Remove step
            </button>

          </div>
        )}
      </div>
    </aside>
  );
}

export { StepConfigPanel };
export type { StepConfigPanelProps };
