import { Brain, ChevronDown, ChevronRight, GitBranch, Globe, Search, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import {
  AgentCommandMenu,
  type AgentCommandSelection,
  type WorkflowCommandSelection,
} from "./chatMain/composer/AgentCommandMenu";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

type ComposerMode = "ask" | "company_agent" | "deep_search" | "web_search" | "brain";

type ComposerModeSelectorProps = {
  value: ComposerMode;
  onChange: (mode: ComposerMode) => void;
  activeAgent?: { agent_id: string; name: string } | null;
  onAgentSelect?: (agent: AgentCommandSelection | null) => void;
  onSelectWorkflow?: (workflow: WorkflowCommandSelection) => void;
};

type ModeOption = {
  value: ComposerMode;
  label: string;
  Icon: typeof Sparkles;
  description?: string;
};

const MODE_OPTIONS: ModeOption[] = [
  { value: "ask", label: "Standard", Icon: Sparkles, description: "Send directly to LLM" },
  { value: "brain", label: "Maia Brain", Icon: Brain, description: "Auto-builds a team and runs it" },
  { value: "company_agent", label: "Workflow", Icon: GitBranch, description: "Pick an existing workflow" },
  { value: "deep_search", label: "Deep research", Icon: Search, description: "Multi-source deep analysis" },
  { value: "web_search", label: "Web search", Icon: Globe, description: "Live web results" },
];

const MODE_LABEL_CLASS: Record<ComposerMode, string> = {
  ask: "text-[#6e6e73]",
  brain: "text-[#7c3aed]",
  company_agent: "text-[#7c3aed]",
  deep_search: "text-[#7c3aed]",
  web_search: "text-[#7c3aed]",
};

export function ComposerModeSelector({
  value,
  onChange,
  onAgentSelect,
  onSelectWorkflow,
}: ComposerModeSelectorProps) {
  const [open, setOpen] = useState(false);
  const [workflowMenuOpen, setWorkflowMenuOpen] = useState(false);

  const selected = useMemo(
    () => MODE_OPTIONS.find((item) => item.value === value) || MODE_OPTIONS[0],
    [value],
  );

  return (
    <div className="relative">
      <Popover
        open={open}
        onOpenChange={(nextOpen) => {
          if (nextOpen && value === "company_agent") {
            setOpen(false);
            setWorkflowMenuOpen(true);
            return;
          }
          setOpen(nextOpen);
        }}
      >
        <PopoverTrigger asChild>
          <button
            type="button"
            className="inline-flex h-8 items-center gap-1.5 rounded-full border border-black/[0.08] bg-white px-2.5 text-[13px] shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-colors hover:bg-[#f7f7f8]"
            aria-label="Select assistant mode"
            title="Select assistant mode"
          >
            <selected.Icon className={`h-3.5 w-3.5 ${MODE_LABEL_CLASS[selected.value]}`} />
            <span className={MODE_LABEL_CLASS[selected.value]}>{selected.label}</span>
            <ChevronDown className="h-3.5 w-3.5 text-[#8d8d93]" />
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="start"
          sideOffset={8}
          className="w-[260px] rounded-2xl border-black/[0.08] bg-white p-1.5 shadow-[0_20px_34px_-24px_rgba(0,0,0,0.55)]"
        >
          <div className="space-y-0.5">
            {MODE_OPTIONS.map((option) => {
              const opensWorkflowMenu = option.value === "company_agent";
              const isActive = value === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    if (opensWorkflowMenu) {
                      setOpen(false);
                      setWorkflowMenuOpen(true);
                      return;
                    }
                    onChange(option.value);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors ${
                    isActive ? "bg-[#f5f3ff]" : "hover:bg-[#f8f8fa]"
                  }`}
                >
                  <option.Icon className={`h-4 w-4 shrink-0 ${isActive ? "text-[#7c3aed]" : "text-[#667085]"}`} />
                  <div className="min-w-0 flex-1">
                    <p className={`text-[13px] font-medium ${isActive ? "text-[#7c3aed]" : "text-[#1d1d1f]"}`}>{option.label}</p>
                    {option.description ? (
                      <p className="text-[11px] text-[#94a3b8]">{option.description}</p>
                    ) : null}
                  </div>
                  {opensWorkflowMenu ? (
                    <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[#94a3b8]" />
                  ) : isActive ? (
                    <span className="shrink-0 text-[10px] font-semibold text-[#7c3aed]">Active</span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </PopoverContent>
      </Popover>
      <AgentCommandMenu
        open={workflowMenuOpen}
        onClose={() => setWorkflowMenuOpen(false)}
        onSelect={(agent) => {
          onChange("company_agent");
          onAgentSelect?.(agent);
          setWorkflowMenuOpen(false);
        }}
        onSelectWorkflow={(workflow) => {
          onSelectWorkflow?.(workflow);
          setWorkflowMenuOpen(false);
        }}
        onOpenWorkflow={(workflowId) => {
          setWorkflowMenuOpen(false);
          window.location.href = `/workflow-builder?id=${encodeURIComponent(workflowId)}`;
        }}
        onSelectStandard={() => {
          onChange("ask");
          setWorkflowMenuOpen(false);
        }}
      />
    </div>
  );
}
