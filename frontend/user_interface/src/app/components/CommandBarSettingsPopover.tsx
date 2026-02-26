import { SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { cn } from "./ui/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";

type CommandBarSettingsPopoverProps = {
  citationMode: string;
  onCitationModeChange: (mode: string) => void;
  isInfoPanelOpen: boolean;
  onToggleInfoPanel: () => void;
  triggerClassName?: string;
  triggerTabIndex?: number;
};

export function CommandBarSettingsPopover({
  citationMode,
  onCitationModeChange,
  isInfoPanelOpen,
  onToggleInfoPanel,
  triggerClassName,
  triggerTabIndex,
}: CommandBarSettingsPopoverProps) {
  const [open, setOpen] = useState(false);

  return (
    <Popover modal open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-open={open ? "true" : "false"}
          aria-label="Open command bar settings"
          title="Command settings"
          tabIndex={triggerTabIndex}
          className={cn(
            "inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/[0.08] bg-white text-[#6e6e73] transition-opacity duration-150 hover:opacity-85 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20",
            triggerClassName,
          )}
        >
          <SlidersHorizontal className="h-4 w-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={10}
        className="w-[292px] rounded-2xl border-black/[0.08] bg-[#f8f8fa] p-3.5 shadow-[0_24px_48px_-30px_rgba(0,0,0,0.55)]"
      >
        <div className="space-y-3.5">
          <div>
            <p className="text-[12px] font-semibold text-[#1d1d1f]">Command settings</p>
            <p className="text-[11px] text-[#6e6e73]">Tune citation and panel behavior.</p>
          </div>
          <div className="h-px w-full bg-black/[0.06]" />
          <div className="space-y-1.5">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">Citation</p>
            <Select value={citationMode} onValueChange={onCitationModeChange}>
              <SelectTrigger
                size="sm"
                className="h-10 rounded-xl border-black/[0.08] bg-white text-[12px] text-[#1d1d1f]"
              >
                <SelectValue placeholder="Select citation mode" />
              </SelectTrigger>
              <SelectContent>
                {["highlight", "footnote", "inline"].map((mode) => (
                  <SelectItem key={mode} value={mode}>
                    {mode}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">Panel</p>
            <button
              type="button"
              onClick={() => {
                onToggleInfoPanel();
                setOpen(false);
              }}
              className="inline-flex h-10 w-full items-center justify-center rounded-xl border border-black/[0.08] bg-white px-3 text-[12px] font-medium text-[#1d1d1f] transition-colors hover:bg-[#f5f5f7] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20"
            >
              {isInfoPanelOpen ? "Hide insights panel" : "Show insights panel"}
            </button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
