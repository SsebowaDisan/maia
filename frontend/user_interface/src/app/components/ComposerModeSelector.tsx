import { Bot, ChevronDown, ChevronRight, Globe, Search, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import {
  AgentCommandMenu,
  type AgentCommandSelection,
} from "./chatMain/composer/AgentCommandMenu";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

type ComposerMode = "ask" | "company_agent" | "deep_search" | "web_search";

type ComposerModeSelectorProps = {
  value: ComposerMode;
  onChange: (mode: ComposerMode) => void;
  activeAgent?: { agent_id: string; name: string } | null;
  onAgentSelect?: (agent: AgentCommandSelection | null) => void;
};

type ModeOption = {
  value: ComposerMode;
  label: string;
  Icon: typeof Sparkles;
};

const MODE_OPTIONS: ModeOption[] = [
  { value: "ask", label: "Standard", Icon: Sparkles },
  { value: "company_agent", label: "Agent", Icon: Bot },
  { value: "deep_search", label: "Deep research", Icon: Search },
  { value: "web_search", label: "Web search", Icon: Globe },
];

const MODE_LABEL_CLASS: Record<ComposerMode, string> = {
  ask: "text-[#6e6e73]",
  company_agent: "text-[#1d4ed8]",
  deep_search: "text-[#1d4ed8]",
  web_search: "text-[#1d4ed8]",
};

function truncateAgentName(value: string, max = 18): string {
  const compact = String(value || "").trim();
  if (!compact) {
    return "";
  }
  return compact.length > max ? `${compact.slice(0, max - 1)}…` : compact;
}

export function ComposerModeSelector({
  value,
  onChange,
  activeAgent = null,
  onAgentSelect,
}: ComposerModeSelectorProps) {
  const [open, setOpen] = useState(false);
  const [agentMenuOpen, setAgentMenuOpen] = useState(false);

  const selected = useMemo(
    () => MODE_OPTIONS.find((item) => item.value === value) || MODE_OPTIONS[0],
    [value],
  );
  const triggerLabel = useMemo(() => {
    if (value !== "company_agent") {
      return selected.label;
    }
    const agentName = truncateAgentName(String(activeAgent?.name || ""));
    return agentName || selected.label;
  }, [activeAgent?.name, selected.label, value]);

  return (
    <div className="relative">
      <Popover
        open={open}
        onOpenChange={(nextOpen) => {
          if (nextOpen && value === "company_agent") {
            setOpen(false);
            setAgentMenuOpen(true);
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
            <span className={MODE_LABEL_CLASS[selected.value]}>{triggerLabel}</span>
            <ChevronDown className="h-3.5 w-3.5 text-[#8d8d93]" />
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="start"
          sideOffset={8}
          className="w-[210px] rounded-2xl border-black/[0.08] bg-white p-1.5 shadow-[0_20px_34px_-24px_rgba(0,0,0,0.55)]"
        >
          <div className="space-y-1">
            {MODE_OPTIONS.map((option) => {
              const opensAgentMenu = option.value === "company_agent";
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    if (opensAgentMenu) {
                      setOpen(false);
                      setAgentMenuOpen(true);
                      return;
                    }
                    onChange(option.value);
                    setOpen(false);
                  }}
                  className={`inline-flex h-9 w-full items-center justify-between rounded-xl px-2.5 text-left text-[12px] transition-colors ${
                    value === option.value
                      ? "bg-[#f1f5ff] text-[#1d4ed8]"
                      : "text-[#1d1d1f] hover:bg-[#f5f5f7]"
                  }`}
                >
                  <span className="inline-flex items-center gap-2">
                    <option.Icon className="h-4 w-4" />
                    <span>{option.label}</span>
                  </span>
                  {opensAgentMenu ? (
                    <ChevronRight className="h-3.5 w-3.5" />
                  ) : value === option.value ? (
                    <span className="text-[10px]">Active</span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </PopoverContent>
      </Popover>
      <AgentCommandMenu
        open={agentMenuOpen}
        onClose={() => setAgentMenuOpen(false)}
        onSelect={(agent) => {
          onChange("company_agent");
          onAgentSelect?.(agent);
          setAgentMenuOpen(false);
        }}
      />
    </div>
  );
}
