/**
 * NodeTypePicker — step type selector for workflow nodes.
 * Shows primary types (AI Agent, Knowledge Search) by default.
 * Advanced automation types are behind a toggle.
 */
import { useState } from "react";
import {
  ArrowRightLeft,
  BookOpen,
  Braces,
  ChevronDown,
  ChevronRight,
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

const PRIMARY_OPTIONS: NodeTypeOption[] = [
  {
    type: "agent",
    label: "AI Agent",
    description: "Let an AI agent handle this step using its tools and knowledge.",
    icon: <Sparkles size={15} />,
    color: "text-[#7c3aed]",
  },
  {
    type: "knowledge_search",
    label: "Knowledge Search",
    description: "Search your uploaded documents, PDFs, and URLs for relevant information.",
    icon: <BookOpen size={15} />,
    color: "text-[#7c3aed]",
  },
];

const ADVANCED_OPTIONS: NodeTypeOption[] = [
  {
    type: "http_request",
    label: "API Call",
    description: "Make an outbound HTTP request to an external service.",
    icon: <Globe size={14} />,
    color: "text-[#0891b2]",
  },
  {
    type: "condition",
    label: "Condition",
    description: "Branch the workflow based on a true/false check.",
    icon: <GitFork size={14} />,
    color: "text-[#d97706]",
  },
  {
    type: "switch",
    label: "Switch",
    description: "Route to different paths by matching a value.",
    icon: <ArrowRightLeft size={14} />,
    color: "text-[#0d9488]",
  },
  {
    type: "transform",
    label: "Transform",
    description: "Reshape or rename data fields between steps.",
    icon: <Layers size={14} />,
    color: "text-[#7c3aed]",
  },
  {
    type: "code",
    label: "Code",
    description: "Run a sandboxed Python expression.",
    icon: <Code2 size={14} />,
    color: "text-[#475569]",
  },
  {
    type: "foreach",
    label: "For Each",
    description: "Repeat an action for every item in a list.",
    icon: <Repeat size={14} />,
    color: "text-[#9333ea]",
  },
  {
    type: "delay",
    label: "Wait",
    description: "Pause the workflow for a set amount of time.",
    icon: <Clock size={14} />,
    color: "text-[#64748b]",
  },
  {
    type: "merge",
    label: "Merge",
    description: "Combine results from parallel branches into one.",
    icon: <Braces size={14} />,
    color: "text-[#059669]",
  },
];

const NODE_TYPE_OPTIONS: NodeTypeOption[] = [...PRIMARY_OPTIONS, ...ADVANCED_OPTIONS];

type NodeTypePickerProps = {
  value: StepType;
  onChange: (type: StepType) => void;
};

function NodeTypePicker({ value, onChange }: NodeTypePickerProps) {
  const allOptions = NODE_TYPE_OPTIONS;
  const selected = allOptions.find((o) => o.type === value) || allOptions[0];
  const isAdvancedType = ADVANCED_OPTIONS.some((o) => o.type === value);
  const [showAdvanced, setShowAdvanced] = useState(isAdvancedType);

  return (
    <div>
      <p className="mb-2 text-[12px] font-semibold text-[#344054]">What should this step do?</p>

      {/* Primary options — large, friendly cards */}
      <div className="space-y-2">
        {PRIMARY_OPTIONS.map((opt) => (
          <button
            key={opt.type}
            type="button"
            onClick={() => onChange(opt.type)}
            className={`flex w-full items-center gap-3 rounded-xl border px-3 py-3 text-left transition-colors ${
              value === opt.type
                ? "border-[#7c3aed] bg-[#f5f3ff] shadow-sm"
                : "border-black/[0.08] bg-white hover:bg-[#f8fafc]"
            }`}
          >
            <span className={`shrink-0 ${opt.color}`}>{opt.icon}</span>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] font-semibold text-[#101828]">{opt.label}</p>
              <p className="mt-0.5 text-[11px] leading-snug text-[#667085]">{opt.description}</p>
            </div>
          </button>
        ))}
      </div>

      {/* Advanced toggle */}
      <button
        type="button"
        onClick={() => setShowAdvanced((o) => !o)}
        className="mt-3 flex w-full items-center gap-1.5 text-[11px] font-medium text-[#98a2b3] hover:text-[#667085]"
      >
        {showAdvanced ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        Automation steps
      </button>

      {showAdvanced ? (
        <div className="mt-2 grid grid-cols-3 gap-1.5">
          {ADVANCED_OPTIONS.map((opt) => (
            <button
              key={opt.type}
              type="button"
              onClick={() => onChange(opt.type)}
              title={opt.description}
              className={`flex flex-col items-center gap-1 rounded-xl border px-2 py-2 text-center transition-colors ${
                value === opt.type
                  ? "border-[#7c3aed] bg-[#f5f3ff] shadow-sm"
                  : "border-black/[0.08] bg-white hover:bg-[#f8fafc]"
              }`}
            >
              <span className={opt.color}>{opt.icon}</span>
              <span className="text-[10px] font-medium leading-tight text-[#344054]">{opt.label}</span>
            </button>
          ))}
        </div>
      ) : null}

      {/* Selected description */}
      {(showAdvanced || !PRIMARY_OPTIONS.some((o) => o.type === value)) && !PRIMARY_OPTIONS.some((o) => o.type === value) ? (
        <p className="mt-1.5 text-[11px] text-[#667085]">{selected.description}</p>
      ) : null}
    </div>
  );
}

export { NodeTypePicker, NODE_TYPE_OPTIONS };
export type { NodeTypeOption };
