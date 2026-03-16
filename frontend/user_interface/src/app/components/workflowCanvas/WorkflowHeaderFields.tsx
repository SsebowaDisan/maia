import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, ChevronDown, Loader2, Plus } from "lucide-react";
import { toast } from "sonner";

import { getWorkflowRecord, listWorkflowRecords } from "../../../api/client/workflows";
import { useWorkflowStore } from "../../stores/workflowStore";

function normalizeWorkflowRecordName(record: { name?: string; definition?: { name?: string } }) {
  const direct = String(record.name || "").trim();
  if (direct) {
    return direct;
  }
  const nested = String(record.definition?.name || "").trim();
  return nested || "Untitled workflow";
}

export function WorkflowHeaderFields() {
  const workflowId = useWorkflowStore((state) => state.workflowId);
  const workflowName = useWorkflowStore((state) => state.workflowName);
  const workflowDescription = useWorkflowStore((state) => state.workflowDescription);
  const isDirty = useWorkflowStore((state) => state.isDirty);
  const setMetadata = useWorkflowStore((state) => state.setMetadata);
  const loadDefinition = useWorkflowStore((state) => state.loadDefinition);
  const markSaved = useWorkflowStore((state) => state.markSaved);
  const clearRun = useWorkflowStore((state) => state.clearRun);

  const [records, setRecords] = useState<Array<{ id: string; name: string }>>([]);
  const [selectedRecordId, setSelectedRecordId] = useState("");
  const [loadingRecords, setLoadingRecords] = useState(false);
  const [loadingSelection, setLoadingSelection] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [open, setOpen] = useState(false);
  const [savedListOpen, setSavedListOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const sortedRecords = useMemo(
    () =>
      [...records].sort((a, b) =>
        String(a.name || "").localeCompare(String(b.name || ""), undefined, { sensitivity: "base" }),
      ),
    [records],
  );

  const refreshRecords = async () => {
    setLoadingRecords(true);
    setLoadError("");
    try {
      const rows = await listWorkflowRecords().catch(() => []);
      setRecords(
        (rows || []).map((row) => ({
          id: String(row.id || "").trim(),
          name: normalizeWorkflowRecordName(row),
        })),
      );
    } catch (error) {
      setLoadError(`Failed to load workflows: ${String(error)}`);
    } finally {
      setLoadingRecords(false);
    }
  };

  useEffect(() => {
    void refreshRecords();
  }, []);

  useEffect(() => {
    setSelectedRecordId(String(workflowId || "").trim());
  }, [workflowId]);

  useEffect(() => {
    if (workflowId && !isDirty) {
      void refreshRecords();
    }
  }, [workflowId, isDirty]);

  useEffect(() => {
    if (!open) {
      setSavedListOpen(false);
      return;
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current) {
        return;
      }
      const target = event.target as Node | null;
      if (target && !rootRef.current.contains(target)) {
        setOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("mousedown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  const handleSelectRecord = async (recordId: string) => {
    const normalizedId = String(recordId || "").trim();
    setSelectedRecordId(normalizedId);
    if (!normalizedId) {
      clearRun();
      setMetadata({
        workflowId: null,
        workflowName: "Untitled workflow",
        workflowDescription: "",
        activeTemplateId: null,
      });
      markSaved();
      return;
    }
    setLoadingSelection(true);
    try {
      const record = await getWorkflowRecord(normalizedId);
      const definition = record.definition;
      loadDefinition(definition, {
        workflowId: normalizedId,
        activeTemplateId: null,
      });
      setMetadata({
        workflowId: normalizedId,
        workflowName: normalizeWorkflowRecordName(record),
        workflowDescription: String(record.description || definition.description || ""),
      });
      markSaved();
      clearRun();
    } catch (error) {
      toast.error(`Failed to load workflow: ${String(error)}`);
    } finally {
      setLoadingSelection(false);
    }
  };

  const selectedRecordName = useMemo(() => {
    if (!selectedRecordId) {
      return "New workflow";
    }
    return (
      sortedRecords.find((workflow) => workflow.id === selectedRecordId)?.name ||
      "New workflow"
    );
  }, [selectedRecordId, sortedRecords]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex h-10 items-center gap-2 rounded-2xl border border-black/[0.08] bg-[linear-gradient(180deg,#ffffff_0%,#f7f8fa_100%)] px-3.5 text-[12px] font-medium text-[#1f2937] shadow-[0_8px_20px_rgba(15,23,42,0.08)] transition hover:border-black/[0.12] hover:shadow-[0_10px_24px_rgba(15,23,42,0.12)]"
      >
        <span className="max-w-[190px] truncate">
          {String(workflowName || "").trim() || "Untitled workflow"}
        </span>
        {isDirty ? <span className="h-1.5 w-1.5 rounded-full bg-[#111827]" /> : null}
        <ChevronDown size={14} className={open ? "rotate-180 transition-transform" : "transition-transform"} />
      </button>

      {open ? (
        <div className="absolute right-0 top-[calc(100%+12px)] z-[190] w-[360px] rounded-3xl border border-white/80 bg-[linear-gradient(180deg,#ffffff_0%,#f7f8fa_100%)] p-4 shadow-[0_28px_68px_-30px_rgba(15,23,42,0.45)] backdrop-blur-xl">
          <div className="mb-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
              Workflow details
            </p>
            <p className="mt-1 text-[13px] text-[#6b7280]">Edit metadata without leaving canvas.</p>
          </div>

          <div className="space-y-2">
            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-[#6b7280]">Saved workflows</span>
              <div className="relative">
                <button
                  type="button"
                  aria-label="Saved workflows"
                  aria-expanded={savedListOpen}
                  onClick={() => setSavedListOpen((value) => !value)}
                  className="inline-flex w-full items-center justify-between rounded-xl border border-black/[0.08] bg-[#f9fafb] px-3 py-2 text-[13px] font-medium text-[#111827] outline-none transition hover:bg-white focus:border-[#9ca3af] focus:bg-white"
                >
                  <span className="truncate">{selectedRecordName}</span>
                  <ChevronDown
                    size={14}
                    className={savedListOpen ? "shrink-0 rotate-180 transition-transform" : "shrink-0 transition-transform"}
                  />
                </button>
                {savedListOpen ? (
                  <div className="absolute left-0 right-0 top-[calc(100%+6px)] z-[220] overflow-hidden rounded-xl border border-black/[0.1] bg-white shadow-[0_18px_34px_-24px_rgba(15,23,42,0.45)]">
                    <button
                      type="button"
                      onClick={() => {
                        setSavedListOpen(false);
                        void handleSelectRecord("");
                      }}
                      className={`block w-full px-3 py-2 text-left text-[13px] transition ${
                        !selectedRecordId ? "bg-[#f3f4f6] font-semibold text-[#111827]" : "text-[#374151] hover:bg-[#f9fafb]"
                      }`}
                    >
                      New workflow
                    </button>
                    {sortedRecords.map((workflow) => {
                      const active = workflow.id === selectedRecordId;
                      return (
                        <button
                          key={workflow.id}
                          type="button"
                          onClick={() => {
                            setSavedListOpen(false);
                            void handleSelectRecord(workflow.id);
                          }}
                          className={`block w-full truncate px-3 py-2 text-left text-[13px] transition ${
                            active ? "bg-[#f3f4f6] font-semibold text-[#111827]" : "text-[#374151] hover:bg-[#f9fafb]"
                          }`}
                        >
                          {workflow.name}
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            </label>

            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-[#6b7280]">Workflow name</span>
              <input
                aria-label="Workflow name"
                value={workflowName}
                onChange={(event) => setMetadata({ workflowName: event.target.value })}
                placeholder="Workflow name"
                className="w-full rounded-xl border border-black/[0.08] bg-[#f9fafb] px-3 py-2 text-[13px] font-semibold text-[#111827] outline-none focus:border-[#9ca3af] focus:bg-white"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-[11px] font-medium text-[#6b7280]">Description</span>
              <input
                aria-label="Workflow description"
                value={workflowDescription}
                onChange={(event) => setMetadata({ workflowDescription: event.target.value })}
                placeholder="Description (optional)"
                className="w-full rounded-xl border border-black/[0.08] bg-[#f9fafb] px-3 py-2 text-[13px] text-[#111827] outline-none focus:border-[#9ca3af] focus:bg-white"
              />
            </label>
          </div>

          <div className="mt-3 flex items-center justify-between gap-2 border-t border-black/[0.06] pt-3">
            <div className="inline-flex min-h-[20px] items-center gap-1.5">
              {loadingRecords || loadingSelection ? (
                <span className="inline-flex items-center gap-1 rounded-full border border-black/[0.08] bg-white px-2 py-1 text-[10px] font-semibold text-[#667085]">
                  <Loader2 size={10} className="animate-spin" />
                  Loading
                </span>
              ) : null}
              {loadError ? (
                <span
                  title={loadError}
                  className="inline-flex items-center gap-1 rounded-full border border-[#fecaca] bg-[#fff1f2] px-2 py-1 text-[10px] font-semibold text-[#b42318]"
                >
                  <AlertCircle size={10} />
                  Error
                </span>
              ) : null}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="inline-flex items-center rounded-full border border-black/[0.1] bg-white px-3 py-1.5 text-[11px] font-medium text-[#475467]"
              >
                Done
              </button>
              <button
                type="button"
                onClick={() => {
                  setSelectedRecordId("");
                  clearRun();
                  setMetadata({
                    workflowId: null,
                    workflowName: "Untitled workflow",
                    workflowDescription: "",
                    activeTemplateId: null,
                  });
                  markSaved();
                }}
                className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.12] bg-white px-3 py-1.5 text-[11px] font-semibold text-[#344054]"
              >
                <Plus size={12} />
                New
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
