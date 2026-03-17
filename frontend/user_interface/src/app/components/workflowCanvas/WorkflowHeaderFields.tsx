import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { useWorkflowStore } from "../../stores/workflowStore";

type WorkflowHeaderFieldsProps = {
  onBackToGallery?: () => void;
};

export function WorkflowHeaderFields({ onBackToGallery }: WorkflowHeaderFieldsProps) {
  const workflowName = useWorkflowStore((state) => state.workflowName);
  const workflowDescription = useWorkflowStore((state) => state.workflowDescription);
  const isDirty = useWorkflowStore((state) => state.isDirty);
  const setMetadata = useWorkflowStore((state) => state.setMetadata);

  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState("");
  const [descOpen, setDescOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const displayName = String(workflowName || "").trim() || "Untitled workflow";

  // Focus and select all when entering edit mode
  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!descOpen) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current) return;
      const target = event.target as Node | null;
      if (target && !rootRef.current.contains(target)) {
        setDescOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDescOpen(false);
    };
    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, [descOpen]);

  const commitEdit = useCallback(() => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== workflowName) {
      setMetadata({ workflowName: trimmed });
    }
    setEditing(false);
  }, [editValue, workflowName, setMetadata]);

  const startEditing = useCallback(() => {
    setEditValue(displayName);
    setEditing(true);
    setDescOpen(false);
  }, [displayName]);

  return (
    <div ref={rootRef} className="relative inline-flex items-center">
      {/* ── Breadcrumb pill ── */}
      <div className="inline-flex h-8 items-center rounded-lg bg-black/[0.04] backdrop-blur-xl transition-colors hover:bg-black/[0.06]">
        {/* "All Workflows" back link */}
        {onBackToGallery ? (
          <>
            <button
              type="button"
              onClick={onBackToGallery}
              className="flex h-full items-center px-3 text-[13px] font-medium text-[#86868b] transition-colors hover:text-[#1d1d1f]"
            >
              Workflows
            </button>
            <ChevronRight size={12} strokeWidth={2} className="shrink-0 text-[#c7c7cc]" />
          </>
        ) : null}

        {/* Editable workflow name */}
        {editing ? (
          <input
            ref={inputRef}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitEdit();
              if (e.key === "Escape") setEditing(false);
            }}
            className="h-full min-w-[80px] max-w-[200px] bg-transparent px-2.5 text-[13px] font-medium text-[#1d1d1f] outline-none selection:bg-[#0071e3]/20"
            style={{ width: `${Math.max(80, editValue.length * 7.5 + 24)}px` }}
          />
        ) : (
          <button
            type="button"
            onDoubleClick={startEditing}
            onClick={() => setDescOpen((v) => !v)}
            className="flex h-full cursor-default items-center gap-1.5 px-2.5"
          >
            <span className="max-w-[180px] truncate text-[13px] font-medium text-[#1d1d1f]">
              {displayName}
            </span>
            {isDirty ? (
              <span className="h-[5px] w-[5px] rounded-full bg-[#1d1d1f]/50" />
            ) : null}
          </button>
        )}

        {/* Chevron for description dropdown */}
        {!editing ? (
          <button
            type="button"
            onClick={() => setDescOpen((v) => !v)}
            className="flex h-full items-center border-l border-black/[0.08] px-2 text-[#86868b] transition-colors hover:text-[#1d1d1f]"
          >
            <ChevronDown
              size={11}
              strokeWidth={2.5}
              className={`transition-transform duration-200 ${descOpen ? "rotate-180" : ""}`}
            />
          </button>
        ) : null}
      </div>

      {/* ── Description popover ── */}
      {descOpen ? (
        <div className="absolute right-0 top-[calc(100%+6px)] z-[190] w-[280px] overflow-hidden rounded-xl border border-black/[0.08] bg-white/90 p-3 shadow-[0_12px_40px_-12px_rgba(0,0,0,0.18)] backdrop-blur-2xl">
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-[#86868b]">Name</span>
            <input
              aria-label="Workflow name"
              value={workflowName}
              onChange={(e) => setMetadata({ workflowName: e.target.value.slice(0, 60) })}
              maxLength={60}
              placeholder="Workflow name"
              className="mb-2 w-full rounded-lg border border-black/[0.06] bg-black/[0.03] px-2.5 py-1.5 text-[13px] font-medium text-[#1d1d1f] outline-none transition focus:border-[#0071e3]/40 focus:bg-white focus:ring-2 focus:ring-[#0071e3]/10"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] font-medium text-[#86868b]">Description</span>
            <input
              aria-label="Workflow description"
              value={workflowDescription}
              onChange={(e) => setMetadata({ workflowDescription: e.target.value })}
              placeholder="Optional"
              className="w-full rounded-lg border border-black/[0.06] bg-black/[0.03] px-2.5 py-1.5 text-[13px] text-[#1d1d1f] outline-none transition focus:border-[#0071e3]/40 focus:bg-white focus:ring-2 focus:ring-[#0071e3]/10"
            />
          </label>
          <button
            type="button"
            onClick={() => setDescOpen(false)}
            className="mt-2 w-full rounded-lg bg-black/[0.04] py-1.5 text-[12px] font-medium text-[#86868b] transition hover:bg-black/[0.06] hover:text-[#1d1d1f]"
          >
            Done
          </button>
        </div>
      ) : null}
    </div>
  );
}
