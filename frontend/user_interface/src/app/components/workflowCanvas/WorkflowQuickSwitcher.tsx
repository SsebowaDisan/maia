import { useCallback, useEffect, useRef, useState } from "react";
import { Clock, Command, Plus, Route, Search } from "lucide-react";

import { getWorkflowRecord, listWorkflowRecords } from "../../../api/client/workflows";
import type { WorkflowRecord } from "../../../api/client/types";

type WorkflowQuickSwitcherProps = {
  open: boolean;
  onClose: () => void;
  onSelectWorkflow: (record: WorkflowRecord) => void;
  onNewWorkflow: () => void;
};

function timeAgo(ts?: number): string {
  if (!ts) return "";
  const seconds = Math.floor(Date.now() / 1000 - ts);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function stepCount(record: WorkflowRecord): number {
  return Array.isArray(record.definition?.steps) ? record.definition.steps.length : 0;
}

export function WorkflowQuickSwitcher({
  open,
  onClose,
  onSelectWorkflow,
  onNewWorkflow,
}: WorkflowQuickSwitcherProps) {
  const [records, setRecords] = useState<WorkflowRecord[]>([]);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  // Load workflows when opened
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setSelectedIndex(0);
    listWorkflowRecords()
      .catch(() => [])
      .then((rows) => setRecords(Array.isArray(rows) ? rows : []));
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  // Filter and sort
  const filtered = query.trim()
    ? records.filter((r) => {
        const q = query.toLowerCase();
        const name = String(r.name || r.definition?.name || "").toLowerCase();
        const desc = String(r.description || "").toLowerCase();
        return name.includes(q) || desc.includes(q);
      })
    : records;

  const sorted = [...filtered].sort(
    (a, b) => (b.updated_at || b.created_at || 0) - (a.updated_at || a.created_at || 0),
  );

  // +1 for "New workflow" action at the end
  const totalItems = sorted.length + 1;

  // Clamp index
  useEffect(() => {
    setSelectedIndex((i) => Math.min(i, totalItems - 1));
  }, [totalItems]);

  // Scroll selected into view
  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector(`[data-index="${selectedIndex}"]`);
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  const handleSelect = useCallback(
    async (record: WorkflowRecord) => {
      try {
        const full = await getWorkflowRecord(record.id);
        onSelectWorkflow(full);
      } catch {
        onSelectWorkflow(record);
      }
      onClose();
    },
    [onSelectWorkflow, onClose],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((i) => (i + 1) % totalItems);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((i) => (i - 1 + totalItems) % totalItems);
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (selectedIndex < sorted.length) {
          void handleSelect(sorted[selectedIndex]);
        } else {
          onNewWorkflow();
          onClose();
        }
      } else if (e.key === "Escape") {
        onClose();
      }
    },
    [totalItems, sorted, selectedIndex, handleSelect, onNewWorkflow, onClose],
  );

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[500] flex items-start justify-center bg-black/30 pt-[15vh] backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="w-full max-w-[520px] overflow-hidden rounded-2xl border border-black/[0.08] bg-white/95 shadow-[0_24px_80px_-20px_rgba(0,0,0,0.3)] backdrop-blur-2xl"
        onKeyDown={handleKeyDown}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-black/[0.06] px-4 py-3">
          <Search size={16} className="shrink-0 text-[#86868b]" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            placeholder="Search workflows..."
            className="flex-1 bg-transparent text-[15px] text-[#1d1d1f] outline-none placeholder:text-[#aeaeb2]"
          />
          <kbd className="hidden items-center gap-0.5 rounded-md border border-black/[0.08] bg-black/[0.03] px-1.5 py-0.5 text-[11px] font-medium text-[#86868b] sm:inline-flex">
            esc
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-[340px] overflow-y-auto p-2">
          {sorted.length === 0 && query ? (
            <div className="px-3 py-6 text-center text-[13px] text-[#86868b]">
              No workflows match "{query}"
            </div>
          ) : (
            sorted.map((record, i) => {
              const name = String(record.name || record.definition?.name || "Untitled").trim();
              const steps = stepCount(record);
              const active = i === selectedIndex;

              return (
                <button
                  key={record.id}
                  type="button"
                  data-index={i}
                  onClick={() => void handleSelect(record)}
                  onMouseEnter={() => setSelectedIndex(i)}
                  className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                    active ? "bg-[#0071e3]/10" : "hover:bg-black/[0.03]"
                  }`}
                >
                  <div
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[13px] font-bold ${
                      active
                        ? "bg-[#0071e3] text-white"
                        : "bg-[#f0f4ff] text-[#3b5bdb]"
                    }`}
                  >
                    {name.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p
                      className={`truncate text-[13px] font-medium ${
                        active ? "text-[#0071e3]" : "text-[#1d1d1f]"
                      }`}
                    >
                      {name}
                    </p>
                    <div className="flex items-center gap-2 text-[11px] text-[#aeaeb2]">
                      {steps > 0 ? (
                        <span className="inline-flex items-center gap-0.5">
                          <Route size={9} />
                          {steps}
                        </span>
                      ) : null}
                      {record.updated_at || record.created_at ? (
                        <span className="inline-flex items-center gap-0.5">
                          <Clock size={9} />
                          {timeAgo(record.updated_at || record.created_at)}
                        </span>
                      ) : null}
                    </div>
                  </div>
                  {active ? (
                    <span className="text-[11px] text-[#aeaeb2]">Enter</span>
                  ) : null}
                </button>
              );
            })
          )}

          {/* New workflow action */}
          <button
            type="button"
            data-index={sorted.length}
            onClick={() => {
              onNewWorkflow();
              onClose();
            }}
            onMouseEnter={() => setSelectedIndex(sorted.length)}
            className={`mt-1 flex w-full items-center gap-3 rounded-xl border-t border-black/[0.04] px-3 py-2.5 text-left transition ${
              selectedIndex === sorted.length ? "bg-[#0071e3]/10" : "hover:bg-black/[0.03]"
            }`}
          >
            <div
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                selectedIndex === sorted.length
                  ? "bg-[#0071e3] text-white"
                  : "bg-black/[0.04] text-[#86868b]"
              }`}
            >
              <Plus size={14} strokeWidth={2.5} />
            </div>
            <span
              className={`text-[13px] font-medium ${
                selectedIndex === sorted.length ? "text-[#0071e3]" : "text-[#1d1d1f]"
              }`}
            >
              New Workflow
            </span>
          </button>
        </div>

        {/* Footer hint */}
        <div className="flex items-center gap-4 border-t border-black/[0.06] px-4 py-2 text-[11px] text-[#aeaeb2]">
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded border border-black/[0.08] bg-black/[0.03] px-1 text-[10px]">↑↓</kbd>
            Navigate
          </span>
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded border border-black/[0.08] bg-black/[0.03] px-1 text-[10px]">↵</kbd>
            Open
          </span>
          <span className="inline-flex items-center gap-1">
            <kbd className="rounded border border-black/[0.08] bg-black/[0.03] px-1 text-[10px]">esc</kbd>
            Close
          </span>
        </div>
      </div>
    </div>
  );
}
