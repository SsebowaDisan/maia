import { ClipboardPaste, FileUp, Plus } from "lucide-react";
import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import { cn } from "./ui/utils";

type ComposerQuickActionsCardProps = {
  onUploadFile: () => void;
  onPasteHighlights?: () => void;
  canPasteHighlights?: boolean;
  disableUpload?: boolean;
  triggerClassName?: string;
};

export function ComposerQuickActionsCard({
  onUploadFile,
  onPasteHighlights,
  canPasteHighlights = false,
  disableUpload = false,
  triggerClassName,
}: ComposerQuickActionsCardProps) {
  const [open, setOpen] = useState(false);

  const runAction = (action: () => void) => {
    action();
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="Open quick actions"
          title="Quick actions"
          className={cn(triggerClassName)}
        >
          <Plus className="h-4.5 w-4.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        sideOffset={8}
        className="w-[220px] rounded-2xl border-black/[0.08] bg-white p-2 shadow-[0_20px_34px_-24px_rgba(0,0,0,0.55)]"
      >
        <div className="space-y-1">
          <button
            type="button"
            disabled={disableUpload}
            onClick={() => runAction(onUploadFile)}
            className="inline-flex h-9 w-full items-center gap-2 rounded-xl px-2.5 text-left text-[12px] text-[#1d1d1f] transition-colors hover:bg-[#f5f5f7] disabled:opacity-50"
          >
            <FileUp className="h-4 w-4 text-[#6e6e73]" />
            <span>Upload file</span>
          </button>
          <button
            type="button"
            disabled={!canPasteHighlights || !onPasteHighlights}
            onClick={() => {
              if (onPasteHighlights) {
                runAction(onPasteHighlights);
              }
            }}
            className="inline-flex h-9 w-full items-center gap-2 rounded-xl px-2.5 text-left text-[12px] text-[#1d1d1f] transition-colors hover:bg-[#f5f5f7] disabled:opacity-50"
          >
            <ClipboardPaste className="h-4 w-4 text-[#6e6e73]" />
            <span>Paste highlights</span>
          </button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
