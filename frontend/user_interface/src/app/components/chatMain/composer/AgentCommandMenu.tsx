import { Bot, ChevronRight, GitBranch, Search, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { listWorkflowRecords, type WorkflowRecord } from "../../../../api/client";

type AgentCommandSelection = {
  agent_id: string;
  name: string;
  description: string;
  trigger_family: string;
};

type WorkflowCommandSelection = {
  workflow_id: string;
  name: string;
  description: string;
  definition: WorkflowRecord["definition"];
};

type AgentCommandMenuProps = {
  open: boolean;
  onClose: () => void;
  onSelect: (agent: AgentCommandSelection) => void;
  onSelectWorkflow?: (workflow: WorkflowCommandSelection) => void;
  onOpenWorkflow?: (workflowId: string) => void;
  onSelectStandard?: () => void;
};

function matchesQuery(name: string, description: string, query: string): boolean {
  if (!query) {
    return true;
  }
  const haystack = `${name} ${description}`.toLowerCase();
  return haystack.includes(query);
}

function AgentMenuSkeleton() {
  return (
    <div className="space-y-2 p-3">
      {Array.from({ length: 3 }).map((_, index) => (
        <div
          key={`workflow-skeleton-${String(index)}`}
          className="h-12 animate-pulse rounded-xl border border-black/[0.06] bg-[#f6f6f7]"
        />
      ))}
    </div>
  );
}

function AgentCommandMenu({ open, onClose, onSelectWorkflow, onOpenWorkflow, onSelectStandard }: AgentCommandMenuProps) {
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [workflows, setWorkflows] = useState<WorkflowCommandSelection[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    if (!open) {
      return;
    }
    let disposed = false;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const workflowRows = await listWorkflowRecords().catch(() => []);
        if (disposed) {
          return;
        }
        const normalized: WorkflowCommandSelection[] = (workflowRows || [])
          .filter((row): row is WorkflowRecord => Boolean(row && row.id))
          .map((row) => ({
            workflow_id: row.id,
            name: String(row.name || "Untitled workflow").trim(),
            description: String(row.description || "").trim(),
            definition: row.definition,
          }));
        setWorkflows(normalized);
      } catch (nextError) {
        if (!disposed) {
          setError(String(nextError || "Failed to load workflows."));
          setWorkflows([]);
        }
      } finally {
        if (!disposed) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      disposed = true;
    };
  }, [open]);

  const normalizedQuery = search.trim().toLowerCase();
  const visibleWorkflows = useMemo(
    () => workflows.filter((row) => matchesQuery(row.name, row.description, normalizedQuery)),
    [normalizedQuery, workflows],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    setActiveIndex(0);
  }, [open, normalizedQuery]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (!visibleWorkflows.length) {
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((previous) => (previous + 1) % visibleWorkflows.length);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((previous) =>
          previous <= 0 ? visibleWorkflows.length - 1 : previous - 1,
        );
        return;
      }
      if (event.key === "Enter") {
        event.preventDefault();
        const selected = visibleWorkflows[activeIndex];
        if (selected) {
          onSelectWorkflow?.(selected);
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeIndex, visibleWorkflows, onClose, onSelectWorkflow, open]);

  if (!open) {
    return null;
  }

  return (
    <>
    {/* Invisible backdrop — click outside to close */}
    <div className="fixed inset-0 z-[139]" onClick={onClose} />
    <div className="absolute bottom-full left-0 z-[140] mb-2 w-[360px] overflow-hidden rounded-2xl border border-black/[0.1] bg-white shadow-[0_18px_42px_-26px_rgba(0,0,0,0.6)]">
      <div className="border-b border-black/[0.06] px-3 py-2.5">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
          Run workflow
        </p>
        <label className="mt-2 flex h-9 items-center gap-2 rounded-xl border border-black/[0.1] bg-white px-2.5">
          <Search className="h-3.5 w-3.5 text-[#8d8d93]" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search workflows"
            className="w-full bg-transparent text-[12px] text-[#1d1d1f] outline-none placeholder:text-[#8d8d93]"
          />
        </label>
      </div>

      {loading ? <AgentMenuSkeleton /> : null}

      {!loading && error ? (
        <div className="p-3">
          <div className="rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#b42318]">
            {error}
          </div>
        </div>
      ) : null}

      {!loading && !error ? (
        <div className="max-h-[380px] overflow-y-auto px-2 py-2">
          <div className="space-y-1">
            {/* Standard — direct to LLM */}
            <button
              type="button"
              onMouseDown={(event) => {
                event.preventDefault();
                onSelectStandard?.();
              }}
              className="w-full rounded-xl border border-transparent px-2.5 py-2 text-left transition-colors hover:border-black/[0.06] hover:bg-[#f8f8fa]"
            >
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-black/[0.08] bg-[#f8fafc]">
                  <Sparkles className="h-3.5 w-3.5 text-[#6e6e73]" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-semibold text-[#111827]">Standard</p>
                  <p className="mt-0.5 text-[12px] text-[#6b7280]">Send directly to LLM</p>
                </div>
              </div>
            </button>

            {/* Divider */}
            <div className="mx-2 border-t border-black/[0.06]" />
          </div>

          {!visibleWorkflows.length ? (
            <div className="flex flex-col items-center gap-2 py-4 text-center">
              <GitBranch className="h-5 w-5 text-[#c4b5fd]" />
              <p className="text-[12px] text-[#667085]">
                {workflows.length ? "No matching workflows." : "No workflows yet."}
              </p>
              <a
                href="/workflow-builder"
                className="inline-flex items-center gap-1 text-[12px] font-semibold text-[#7c3aed] hover:underline"
              >
                Create a workflow
                <ChevronRight className="h-3 w-3" />
              </a>
            </div>
          ) : (
            <div className="space-y-1">
              {visibleWorkflows.map((workflow, index) => {
                const isActive = index === activeIndex;
                const stepCount = Array.isArray(workflow.definition?.steps)
                  ? workflow.definition.steps.length
                  : 0;
                return (
                  <button
                    key={workflow.workflow_id}
                    type="button"
                    onMouseDown={(event) => {
                      event.preventDefault();
                      onSelectWorkflow?.(workflow);
                    }}
                    onDoubleClick={() => onOpenWorkflow?.(workflow.workflow_id)}
                    onMouseEnter={() => setActiveIndex(index)}
                    className={`w-full rounded-xl border px-2.5 py-2 text-left transition-colors ${
                      isActive
                        ? "border-[#c4b5fd] bg-[#f5f3ff]"
                        : "border-transparent hover:border-black/[0.06] hover:bg-[#f8f8fa]"
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[#c4b5fd]/40 bg-[#f5f3ff]">
                        <GitBranch className="h-3.5 w-3.5 text-[#7c3aed]" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-semibold text-[#111827]">
                          {workflow.name}
                        </p>
                        <p className="mt-0.5 truncate text-[12px] text-[#6b7280]">
                          {workflow.description ||
                            `${stepCount} step${stepCount !== 1 ? "s" : ""}`}
                        </p>
                      </div>
                      <span className="shrink-0 rounded-full border border-[#c4b5fd] bg-[#f5f3ff] px-2 py-0.5 text-[10px] font-semibold text-[#7c3aed]">
                        Workflow
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      ) : null}

      <div className="flex items-center justify-between border-t border-black/[0.06] bg-[#fcfcfd] px-3 py-2">
        <a
          href="/workflow-builder"
          className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#7c3aed] hover:text-[#6d28d9]"
        >
          <GitBranch className="h-3 w-3" />
          Create new workflow
        </a>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex items-center gap-1 rounded-full border border-black/[0.08] bg-white px-2.5 py-1 text-[11px] font-semibold text-[#4b5563] hover:bg-[#f7f7f8]"
        >
          <Bot className="h-3.5 w-3.5" />
          Close
        </button>
      </div>
    </div>
    </>
  );
}

export { AgentCommandMenu };
export type { AgentCommandMenuProps, AgentCommandSelection, WorkflowCommandSelection };
