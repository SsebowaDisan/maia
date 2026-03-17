import { useEffect, useState } from "react";
import {
  ArrowRight,
  Clock,
  LayoutTemplate,
  Loader2,
  Plus,
  Route,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import {
  getWorkflowRecord,
  listWorkflowRecords,
  removeWorkflowRecord,
} from "../../../api/client/workflows";
import type { WorkflowRecord, WorkflowTemplate } from "../../../api/client/types";

type WorkflowGalleryProps = {
  onSelectWorkflow: (record: WorkflowRecord) => void;
  onNewWorkflow: () => void;
  templates: WorkflowTemplate[];
  templatesLoading: boolean;
  onSelectTemplate: (template: WorkflowTemplate) => void;
};

function timeAgo(ts?: number): string {
  if (!ts) return "";
  const seconds = Math.floor((Date.now() / 1000) - ts);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function stepCount(record: WorkflowRecord): number {
  return Array.isArray(record.definition?.steps) ? record.definition.steps.length : 0;
}

// Color palette for template cards — cycles through
const TEMPLATE_COLORS = [
  { bg: "from-[#f5f3ff] to-[#ede9fe]", icon: "text-[#7c3aed]", hover: "hover:border-[#7c3aed]/25" },
  { bg: "from-[#ecfdf5] to-[#d1fae5]", icon: "text-[#059669]", hover: "hover:border-[#059669]/25" },
  { bg: "from-[#fff7ed] to-[#ffedd5]", icon: "text-[#ea580c]", hover: "hover:border-[#ea580c]/25" },
  { bg: "from-[#eff6ff] to-[#dbeafe]", icon: "text-[#2563eb]", hover: "hover:border-[#2563eb]/25" },
  { bg: "from-[#fdf2f8] to-[#fce7f3]", icon: "text-[#db2777]", hover: "hover:border-[#db2777]/25" },
  { bg: "from-[#f0fdfa] to-[#ccfbf1]", icon: "text-[#0d9488]", hover: "hover:border-[#0d9488]/25" },
];

export function WorkflowGallery({
  onSelectWorkflow,
  onNewWorkflow,
  templates,
  templatesLoading,
  onSelectTemplate,
}: WorkflowGalleryProps) {
  const [records, setRecords] = useState<WorkflowRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const rows = await listWorkflowRecords().catch(() => []);
      setRecords(Array.isArray(rows) ? rows : []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const handleDelete = async (e: React.MouseEvent, recordId: string) => {
    e.stopPropagation();
    if (deletingId) return;
    setDeletingId(recordId);
    try {
      await removeWorkflowRecord(recordId);
      setRecords((prev) => prev.filter((r) => r.id !== recordId));
      toast.success("Workflow deleted.");
    } catch (err) {
      toast.error(`Failed to delete: ${String(err)}`);
    } finally {
      setDeletingId(null);
    }
  };

  const handleSelect = async (record: WorkflowRecord) => {
    try {
      const full = await getWorkflowRecord(record.id);
      onSelectWorkflow(full);
    } catch {
      onSelectWorkflow(record);
    }
  };

  const filtered = search.trim()
    ? records.filter((r) => {
        const q = search.toLowerCase();
        const name = String(r.name || r.definition?.name || "").toLowerCase();
        const desc = String(r.description || r.definition?.description || "").toLowerCase();
        return name.includes(q) || desc.includes(q);
      })
    : records;

  const sorted = [...filtered].sort((a, b) => (b.updated_at || b.created_at || 0) - (a.updated_at || a.created_at || 0));

  const showTemplates = !search.trim() && templates.length > 0;

  return (
    <div className="flex h-full flex-col items-center overflow-y-auto bg-[#f5f5f7] px-6 py-10">
      <div className="w-full max-w-[840px]">
        {/* Header */}
        <div className="mb-8 flex items-end justify-between gap-4">
          <div>
            <h1 className="text-[28px] font-bold tracking-tight text-[#1d1d1f]">
              Workflows
            </h1>
            <p className="mt-1 text-[15px] text-[#86868b]">
              Compose multi-agent automations.
            </p>
          </div>
          <button
            type="button"
            onClick={onNewWorkflow}
            className="inline-flex items-center gap-2 rounded-full bg-[#1d1d1f] px-5 py-2.5 text-[13px] font-semibold text-white shadow-sm transition hover:bg-[#000]"
          >
            <Plus size={14} strokeWidth={2.5} />
            New Workflow
          </button>
        </div>

        {/* Search */}
        <div className="relative mb-6">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[#86868b]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search workflows..."
            className="w-full rounded-xl border border-black/[0.06] bg-white/80 py-2.5 pl-10 pr-4 text-[14px] text-[#1d1d1f] shadow-sm outline-none backdrop-blur-xl transition placeholder:text-[#aeaeb2] focus:border-black/[0.12] focus:bg-white focus:shadow-md"
          />
        </div>

        {/* ── Templates section ── */}
        {showTemplates ? (
          <div className="mb-8">
            <div className="mb-3 flex items-center gap-2">
              <LayoutTemplate size={14} className="text-[#86868b]" />
              <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-[#86868b]">
                Start from a template
              </h2>
            </div>
            {templatesLoading ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-[100px] animate-pulse rounded-2xl bg-white/60" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {templates.slice(0, 6).map((template, i) => {
                  const color = TEMPLATE_COLORS[i % TEMPLATE_COLORS.length];
                  const steps = template.step_count || (Array.isArray(template.definition?.steps) ? template.definition.steps.length : 0);
                  const tags = Array.isArray(template.tags) ? template.tags.slice(0, 2) : [];

                  return (
                    <button
                      key={template.template_id}
                      type="button"
                      onClick={() => onSelectTemplate(template)}
                      className={`group relative flex flex-col justify-between overflow-hidden rounded-2xl border border-black/[0.06] bg-white p-4 text-left shadow-sm transition hover:shadow-md ${color.hover}`}
                    >
                      {/* Gradient accent bar */}
                      <div className={`absolute inset-x-0 top-0 h-1 bg-gradient-to-r ${color.bg}`} />

                      <div className="mt-1">
                        <p className="text-[13px] font-semibold text-[#1d1d1f] group-hover:text-[#1d1d1f]">
                          {template.name}
                        </p>
                        {template.description ? (
                          <p className="mt-1 line-clamp-2 text-[11px] leading-[1.45] text-[#86868b]">
                            {template.description}
                          </p>
                        ) : null}
                      </div>

                      <div className="mt-3 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          {steps > 0 ? (
                            <span className="inline-flex items-center gap-1 text-[10px] text-[#aeaeb2]">
                              <Route size={9} />
                              {steps} step{steps !== 1 ? "s" : ""}
                            </span>
                          ) : null}
                          {tags.map((tag) => (
                            <span
                              key={tag}
                              className={`rounded-full bg-gradient-to-r ${color.bg} px-1.5 py-px text-[9px] font-medium ${color.icon}`}
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                        <ArrowRight
                          size={12}
                          className="text-[#aeaeb2] opacity-0 transition group-hover:opacity-100"
                        />
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        ) : null}

        {/* ── Your workflows section ── */}
        {showTemplates && sorted.length > 0 ? (
          <div className="mb-3 flex items-center gap-2">
            <Route size={14} className="text-[#86868b]" />
            <h2 className="text-[13px] font-semibold uppercase tracking-[0.08em] text-[#86868b]">
              Your workflows
            </h2>
          </div>
        ) : null}

        {/* Grid */}
        {loading ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-[160px] animate-pulse rounded-2xl bg-white/60"
              />
            ))}
          </div>
        ) : sorted.length === 0 && !showTemplates ? (
          <div className="flex flex-col items-center gap-4 py-20 text-center">
            <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white shadow-sm">
              {search ? (
                <Search size={24} className="text-[#aeaeb2]" />
              ) : (
                <Sparkles size={24} className="text-[#aeaeb2]" />
              )}
            </div>
            <div>
              <p className="text-[15px] font-semibold text-[#1d1d1f]">
                {search ? "No workflows match your search" : "No workflows yet"}
              </p>
              <p className="mt-1 text-[13px] text-[#86868b]">
                {search
                  ? "Try a different keyword."
                  : "Create your first workflow to get started."}
              </p>
            </div>
            {!search ? (
              <button
                type="button"
                onClick={onNewWorkflow}
                className="mt-2 inline-flex items-center gap-2 rounded-full bg-[#0071e3] px-5 py-2.5 text-[13px] font-semibold text-white transition hover:bg-[#0077ed]"
              >
                <Plus size={14} strokeWidth={2.5} />
                Create Workflow
              </button>
            ) : null}
          </div>
        ) : sorted.length === 0 && showTemplates ? null : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            {/* New workflow card */}
            <button
              type="button"
              onClick={onNewWorkflow}
              className="group flex h-[160px] flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-black/[0.08] bg-white/40 transition hover:border-[#0071e3]/30 hover:bg-white/70"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#0071e3]/10 text-[#0071e3] transition group-hover:bg-[#0071e3]/15">
                <Plus size={20} strokeWidth={2.5} />
              </div>
              <span className="text-[13px] font-medium text-[#86868b] transition group-hover:text-[#1d1d1f]">
                New Workflow
              </span>
            </button>

            {/* Workflow cards */}
            {sorted.map((record) => {
              const name = String(record.name || record.definition?.name || "Untitled").trim();
              const desc = String(record.description || record.definition?.description || "").trim();
              const steps = stepCount(record);
              const monogram = name.charAt(0).toUpperCase() || "W";
              const isDeleting = deletingId === record.id;

              return (
                <button
                  key={record.id}
                  type="button"
                  onClick={() => void handleSelect(record)}
                  disabled={isDeleting}
                  className="group relative flex h-[160px] flex-col justify-between overflow-hidden rounded-2xl border border-black/[0.06] bg-white p-4 text-left shadow-sm transition hover:border-black/[0.1] hover:shadow-md disabled:opacity-50"
                >
                  {/* Delete button */}
                  <button
                    type="button"
                    onClick={(e) => void handleDelete(e, record.id)}
                    className="absolute right-2.5 top-2.5 flex h-7 w-7 items-center justify-center rounded-lg bg-black/[0.04] text-[#aeaeb2] opacity-0 transition hover:bg-[#ff3b30]/10 hover:text-[#ff3b30] group-hover:opacity-100"
                  >
                    {isDeleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                  </button>

                  {/* Top: monogram + name */}
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#f0f4ff] to-[#e0e7ff] text-[16px] font-bold text-[#3b5bdb]">
                      {monogram}
                    </div>
                    <div className="min-w-0 pt-0.5">
                      <p className="truncate text-[14px] font-semibold text-[#1d1d1f]">
                        {name}
                      </p>
                      {desc ? (
                        <p className="mt-0.5 line-clamp-2 text-[11px] leading-[1.4] text-[#86868b]">
                          {desc}
                        </p>
                      ) : null}
                    </div>
                  </div>

                  {/* Bottom: metadata */}
                  <div className="flex items-center gap-3 text-[11px] text-[#aeaeb2]">
                    {steps > 0 ? (
                      <span className="inline-flex items-center gap-1">
                        <Route size={10} />
                        {steps} step{steps !== 1 ? "s" : ""}
                      </span>
                    ) : null}
                    {record.updated_at || record.created_at ? (
                      <span className="inline-flex items-center gap-1">
                        <Clock size={10} />
                        {timeAgo(record.updated_at || record.created_at)}
                      </span>
                    ) : null}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
