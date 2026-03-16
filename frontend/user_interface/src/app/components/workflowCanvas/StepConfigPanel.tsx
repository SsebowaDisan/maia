import { useEffect, useMemo, useState } from "react";
import { Trash2, X } from "lucide-react";

import type { AgentSummaryRecord } from "../../../api/client";
import type { WorkflowCanvasEdge, WorkflowCanvasNode, WorkflowCanvasNodeData } from "../../stores/workflowStore";

type StepConfigPanelProps = {
  node: WorkflowCanvasNode | null;
  agents: AgentSummaryRecord[];
  outgoingEdges: WorkflowCanvasEdge[];
  onClose: () => void;
  onDeleteNode: (nodeId: string) => void;
  onUpdateNodeData: (nodeId: string, patch: Partial<WorkflowCanvasNodeData>) => void;
  onUpdateEdgeCondition: (edgeId: string, condition: string) => void;
};

function StepConfigPanel({
  node,
  agents,
  outgoingEdges,
  onClose,
  onDeleteNode,
  onUpdateNodeData,
  onUpdateEdgeCondition,
}: StepConfigPanelProps) {
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [agentId, setAgentId] = useState("");
  const [outputKey, setOutputKey] = useState("");
  const [toolIdsText, setToolIdsText] = useState("");

  useEffect(() => {
    if (!node) {
      setLabel("");
      setDescription("");
      setAgentId("");
      setOutputKey("");
      setToolIdsText("");
      return;
    }
    setLabel(node.data.label || "");
    setDescription(node.data.description || "");
    setAgentId(node.data.agentId || "");
    setOutputKey(node.data.outputKey || "");
    setToolIdsText((node.data.toolIds || []).join(", "));
  }, [node]);

  const normalizedToolIds = useMemo(
    () =>
      toolIdsText
        .split(",")
        .map((row) => String(row || "").trim())
        .filter(Boolean),
    [toolIdsText],
  );

  if (!node) {
    return null;
  }

  return (
    <aside className="w-[360px] shrink-0 overflow-y-auto rounded-2xl border border-black/[0.08] bg-white">
      <div className="flex items-center justify-between border-b border-black/[0.06] px-4 py-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
            Step configuration
          </p>
          <p className="text-[14px] font-semibold text-[#101828]">{node.id}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-black/[0.08] p-2 text-[#475467] hover:bg-[#f8fafc]"
          aria-label="Close step configuration"
        >
          <X size={14} />
        </button>
      </div>

      <div className="space-y-3 px-4 py-4">
        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.09em] text-[#667085]">
            Label
          </span>
          <input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            onBlur={() => onUpdateNodeData(node.id, { label })}
            className="w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px] text-[#101828] outline-none focus:border-[#94a3b8]"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.09em] text-[#667085]">
            Agent
          </span>
          <select
            value={agentId}
            onChange={(event) => {
              const next = event.target.value;
              setAgentId(next);
              onUpdateNodeData(node.id, { agentId: next });
            }}
            className="w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px] text-[#101828] outline-none focus:border-[#94a3b8]"
          >
            <option value="">Select an agent</option>
            {agents.map((agent) => (
              <option key={agent.agent_id} value={agent.agent_id}>
                {agent.name || agent.agent_id}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.09em] text-[#667085]">
            Output key
          </span>
          <input
            value={outputKey}
            onChange={(event) => setOutputKey(event.target.value)}
            onBlur={() => onUpdateNodeData(node.id, { outputKey })}
            className="w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px] text-[#101828] outline-none focus:border-[#94a3b8]"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.09em] text-[#667085]">
            Description
          </span>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            onBlur={() => onUpdateNodeData(node.id, { description })}
            rows={3}
            className="w-full resize-none rounded-xl border border-black/[0.12] px-3 py-2 text-[13px] text-[#101828] outline-none focus:border-[#94a3b8]"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-[0.09em] text-[#667085]">
            Tools
          </span>
          <input
            value={toolIdsText}
            onChange={(event) => setToolIdsText(event.target.value)}
            onBlur={() => onUpdateNodeData(node.id, { toolIds: normalizedToolIds })}
            placeholder="web_search, summarize, send_email"
            className="w-full rounded-xl border border-black/[0.12] px-3 py-2 text-[13px] text-[#101828] outline-none focus:border-[#94a3b8]"
          />
        </label>

        {outgoingEdges.length ? (
          <div className="rounded-xl border border-black/[0.08] bg-[#fcfcfd] p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.09em] text-[#667085]">
              Edge conditions
            </p>
            <div className="mt-2 space-y-2">
              {outgoingEdges.map((edge) => (
                <label key={edge.id} className="block">
                  <span className="mb-1 block text-[11px] text-[#667085]">
                    {edge.source} {"->"} {edge.target}
                  </span>
                  <input
                    defaultValue={edge.condition || ""}
                    onBlur={(event) => onUpdateEdgeCondition(edge.id, event.target.value)}
                    placeholder="output.score > 0.8"
                    className="w-full rounded-lg border border-black/[0.12] px-2.5 py-1.5 text-[12px] text-[#101828] outline-none focus:border-[#94a3b8]"
                  />
                </label>
              ))}
            </div>
          </div>
        ) : null}

        <button
          type="button"
          onClick={() => onDeleteNode(node.id)}
          className="inline-flex w-full items-center justify-center gap-1.5 rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] font-semibold text-[#b42318] hover:bg-[#ffe4e6]"
        >
          <Trash2 size={13} />
          Remove step
        </button>
      </div>
    </aside>
  );
}

export { StepConfigPanel };
export type { StepConfigPanelProps };
