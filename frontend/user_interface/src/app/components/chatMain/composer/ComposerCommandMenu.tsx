import { FileText, FolderOpen, Layers, Search } from "lucide-react";
import type { CommandOption, CommandQueryState } from "./commandPalette";

type ComposerCommandMenuProps = {
  query: CommandQueryState;
  options: CommandOption[];
  activeIndex: number;
  onSelect: (option: CommandOption) => void;
  onPreview?: (option: CommandOption) => void;
};

const TRIGGER_META: Record<string, { label: string; icon: typeof FileText; emptyText: string }> = {
  document: { label: "Documents", icon: FileText, emptyText: "No matching documents" },
  group: { label: "Groups", icon: FolderOpen, emptyText: "No matching groups" },
  project: { label: "Projects", icon: Layers, emptyText: "No matching projects" },
};

function fileExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1).toUpperCase() : "";
}

function extColor(ext: string): string {
  if (ext === "PDF") return "bg-[#fee2e2] text-[#dc2626]";
  if (ext === "DOCX" || ext === "DOC") return "bg-[#dbeafe] text-[#2563eb]";
  if (ext === "XLSX" || ext === "XLS" || ext === "CSV") return "bg-[#d1fae5] text-[#059669]";
  if (ext === "TXT" || ext === "MD") return "bg-[#f3f4f6] text-[#6b7280]";
  if (ext === "PPTX" || ext === "PPT") return "bg-[#fef3c7] text-[#d97706]";
  return "bg-[#f3f4f6] text-[#6b7280]";
}

function ComposerCommandMenu({ query, options, activeIndex, onSelect, onPreview }: ComposerCommandMenuProps) {
  if (!options.length) {
    return null;
  }
  const meta = TRIGGER_META[query.trigger] || TRIGGER_META.document;
  const Icon = meta.icon;

  return (
    <div className="overflow-hidden rounded-2xl border border-black/[0.06] bg-white/95 shadow-[0_12px_40px_-10px_rgba(0,0,0,0.15)] backdrop-blur-xl">
      {/* Header with live search hint */}
      <div className="border-b border-black/[0.05] px-3.5 py-2.5">
        <div className="flex items-center gap-2">
          <Search size={13} className="shrink-0 text-[#aeaeb2]" />
          <span className="flex-1 text-[12px] text-[#86868b]">
            {query.query ? (
              <>Searching <span className="font-semibold text-[#1d1d1f]">&ldquo;{query.query}&rdquo;</span></>
            ) : (
              <>Type to filter {meta.label.toLowerCase()}&hellip;</>
            )}
          </span>
          <span className="text-[11px] text-[#aeaeb2]">{options.length} found</span>
        </div>
      </div>

      {/* List */}
      <ul className="max-h-[280px] overflow-y-auto px-1.5 py-1.5">
        {options.map((option, index) => {
          const ext = query.trigger === "document" ? fileExtension(option.label) : "";
          const isActive = index === activeIndex;
          return (
            <li key={`${query.trigger}-${option.id}`}>
              <button
                type="button"
                onMouseDown={(event) => {
                  event.preventDefault();
                  onSelect(option);
                }}
                onDoubleClick={() => onPreview?.(option)}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
                  isActive
                    ? "bg-[#f5f3ff] shadow-sm"
                    : "hover:bg-[#f8f8fa]"
                }`}
              >
                {/* File type badge or icon */}
                {ext ? (
                  <span className={`inline-flex h-8 w-10 shrink-0 items-center justify-center rounded-lg text-[10px] font-bold ${extColor(ext)}`}>
                    {ext}
                  </span>
                ) : (
                  <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#f2f4f7] text-[#86868b]">
                    <Icon size={14} />
                  </span>
                )}

                {/* Name + subtitle */}
                <div className="min-w-0 flex-1">
                  <p className={`truncate text-[13px] font-medium ${isActive ? "text-[#1d1d1f]" : "text-[#344054]"}`}>
                    {option.label}
                  </p>
                  {option.subtitle && option.subtitle !== "Document" ? (
                    <p className="mt-0.5 text-[11px] text-[#aeaeb2]">{option.subtitle}</p>
                  ) : null}
                </div>

                {/* Keyboard hint for active item */}
                {isActive ? (
                  <span className="shrink-0 rounded-md bg-black/[0.04] px-1.5 py-0.5 text-[10px] font-medium text-[#aeaeb2]">
                    ↵
                  </span>
                ) : null}
              </button>
            </li>
          );
        })}
      </ul>

      {/* Footer hint */}
      <div className="border-t border-black/[0.05] px-3.5 py-2">
        <p className="text-[11px] text-[#aeaeb2]">
          <span className="rounded bg-black/[0.04] px-1 py-px font-medium">↑↓</span>{" "}
          navigate{" · "}
          <span className="rounded bg-black/[0.04] px-1 py-px font-medium">↵</span>{" "}
          attach{" · "}
          <span className="rounded bg-black/[0.04] px-1 py-px font-medium">esc</span>{" "}
          dismiss
        </p>
      </div>
    </div>
  );
}

export { ComposerCommandMenu };
