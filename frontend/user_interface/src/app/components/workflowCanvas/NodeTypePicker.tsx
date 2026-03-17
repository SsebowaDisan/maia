/**
 * NodeTypePicker — dropdown to select the step_type for a workflow node.
 * Shows available deterministic node types with icons and descriptions.
 */
import {
  ArrowRightLeft,
  Braces,
  Clock,
  Code2,
  GitFork,
  Globe,
  Layers,
  Repeat,
  Sparkles,
} from "lucide-react";
import type { StepType } from "../../stores/workflowStore";

type NodeTypeOption = {
  type: StepType;
  label: string;
  description: string;
  icon: React.ReactNode;
  color: string;
};

const NODE_TYPE_OPTIONS: NodeTypeOption[] = [
  {
    type: "agent",
    label: "AI Agent",
    description: "Runs an LLM agent with tools",
    icon: <Sparkles size={14} />,
    color: "text-[#7c3aed]",
  },
  {
    type: "http_request",
    label: "HTTP Request",
    description: "Make an outbound API call",
    icon: <Globe size={14} />,
    color: "text-[#0891b2]",
  },
  {
    type: "condition",
    label: "Condition",
    description: "Branch based on a boolean expression",
    icon: <GitFork size={14} />,
    color: "text-[#d97706]",
  },
  {
    type: "switch",
    label: "Switch",
    description: "Route by matching a value to cases",
    icon: <ArrowRightLeft size={14} />,
    color: "text-[#0d9488]",
  },
  {
    type: "transform",
    label: "Transform",
    description: "Reshape data with field mapping",
    icon: <Layers size={14} />,
    color: "text-[#2563eb]",
  },
  {
    type: "code",
    label: "Code",
    description: "Run a sandboxed Python expression",
    icon: <Code2 size={14} />,
    color: "text-[#475569]",
  },
  {
    type: "foreach",
    label: "For Each",
    description: "Iterate over a list and collect results",
    icon: <Repeat size={14} />,
    color: "text-[#9333ea]",
  },
  {
    type: "delay",
    label: "Delay",
    description: "Pause execution for a set time",
    icon: <Clock size={14} />,
    color: "text-[#64748b]",
  },
  {
    type: "merge",
    label: "Merge",
    description: "Combine outputs from parallel branches",
    icon: <Braces size={14} />,
    color: "text-[#059669]",
  },
];

type NodeTypePickerProps = {
  value: StepType;
  onChange: (type: StepType) => void;
};

function NodeTypePicker({ value, onChange }: NodeTypePickerProps) {
  const selected = NODE_TYPE_OPTIONS.find((o) => o.type === value) || NODE_TYPE_OPTIONS[0];

  return (
    <div>
      <p className="mb-1.5 text-[12px] font-semibold text-[#344054]">Step type</p>
      <div className="grid grid-cols-3 gap-1.5">
        {NODE_TYPE_OPTIONS.map((opt) => (
          <button
            key={opt.type}
            type="button"
            onClick={() => onChange(opt.type)}
            title={opt.description}
            className={`flex flex-col items-center gap-1 rounded-xl border px-2 py-2 text-center transition-colors ${
              value === opt.type
                ? "border-[#6366f1] bg-[#eef2ff] shadow-sm"
                : "border-black/[0.08] bg-white hover:bg-[#f8fafc]"
            }`}
          >
            <span className={opt.color}>{opt.icon}</span>
            <span className="text-[10px] font-medium leading-tight text-[#344054]">{opt.label}</span>
          </button>
        ))}
      </div>
      <p className="mt-1.5 text-[11px] text-[#667085]">{selected.description}</p>
    </div>
  );
}

export { NodeTypePicker, NODE_TYPE_OPTIONS };
export type { NodeTypeOption };
