import { FileDown, FileImage, FileJson, MoreVertical, Save } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";

import type { MindmapMapType } from "./types";

type MindMapToolbarProps = {
  activeMapType: MindmapMapType;
  availableMapTypes: MindmapMapType[];
  maxDepth: number;
  showReasoningMap: boolean;
  hasReasoningMap: boolean;
  focusNodeId: string | null;
  onSwitchMapType: (mapType: MindmapMapType) => void;
  onExpand: () => void;
  onCollapse: () => void;
  onFitView: () => void;
  onMaxDepthChange: (depth: number) => void;
  onToggleReasoningMap: () => void;
  onClearFocus: () => void;
  onExportPng: () => void;
  onExportJson: () => void;
  onExportMarkdown: () => void;
  onSave: () => void;
  onShare: () => void | Promise<void>;
};

type MindMapActionMenuProps = Pick<
  MindMapToolbarProps,
  "onExportPng" | "onExportJson" | "onExportMarkdown" | "onSave" | "onShare"
> & {
  className?: string;
};

const MAP_TYPE_LABELS: Record<MindmapMapType, string> = {
  structure: "Concept",
  evidence: "Evidence",
  work_graph: "Execution",
  context_mindmap: "Sources",
};

export function MindMapActionMenuButton({
  onExportPng,
  onExportJson,
  onExportMarkdown,
  onSave,
  onShare,
  className,
}: MindMapActionMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={
            className ||
            "inline-flex h-8 w-8 items-center justify-center rounded-full bg-transparent text-[#575b66] transition-colors hover:bg-black/[0.05]"
          }
          title="Map actions"
        >
          <MoreVertical className="h-4 w-4" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="min-w-[180px] rounded-xl border-black/[0.08] bg-white p-1.5 shadow-[0_10px_30px_rgba(15,23,42,0.14)]"
      >
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault();
            void onShare();
          }}
          className="rounded-lg text-[12px] font-medium text-[#4a4f58]"
        >
          Share link
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault();
            onExportPng();
          }}
          className="rounded-lg text-[12px] font-medium text-[#4a4f58]"
        >
          <FileImage className="mr-1.5 h-3.5 w-3.5" />
          PNG
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault();
            onExportJson();
          }}
          className="rounded-lg text-[12px] font-medium text-[#4a4f58]"
        >
          <FileJson className="mr-1.5 h-3.5 w-3.5" />
          JSON
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault();
            onExportMarkdown();
          }}
          className="rounded-lg text-[12px] font-medium text-[#4a4f58]"
        >
          <FileDown className="mr-1.5 h-3.5 w-3.5" />
          Markdown
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={(event) => {
            event.preventDefault();
            onSave();
          }}
          className="rounded-lg text-[12px] font-medium text-[#4a4f58]"
        >
          <Save className="mr-1.5 h-3.5 w-3.5" />
          Save
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function MindMapToolbar(props: MindMapToolbarProps) {
  const availableTypes =
    props.availableMapTypes.length > 0 ? props.availableMapTypes : [props.activeMapType];

  return (
    <div className="inline-flex max-w-full flex-wrap items-center rounded-[20px] border border-white/70 bg-white/82 p-1 shadow-[0_18px_36px_rgba(15,23,42,0.16)] backdrop-blur-xl">
      {availableTypes.map((mapType) => (
        <button
          key={mapType}
          type="button"
          onClick={() => props.onSwitchMapType(mapType)}
          className={`h-8 rounded-full px-3.5 text-[12px] font-medium transition-colors ${
            props.activeMapType === mapType
              ? "bg-[#17171b] text-white"
              : "text-[#3a3a40] hover:bg-[#f4f4f6]"
          }`}
        >
          {MAP_TYPE_LABELS[mapType]}
        </button>
      ))}
    </div>
  );
}
