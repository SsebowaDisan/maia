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
  X,
} from "lucide-react";
import { toast } from "sonner";

import { getWorkflowTemplatePreview, type WorkflowTemplatePreview } from "../../../api/client";
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
  // Normalize: if ts looks like seconds (before year 2100), convert to ms
  const ms = ts < 1e12 ? ts * 1000 : ts;
  const diff = Math.max(0, Date.now() - ms);
  const seconds = Math.floor(diff / 1000);
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

// Color palette — cycles through for cards
const CARD_COLORS = [
  { accent: "#7c3aed", bg: "from-[#f5f3ff] to-[#ede9fe]", text: "text-[#7c3aed]", mono: "from-[#ede9fe] to-[#ddd6fe]", hover: "hover:border-[#7c3aed]/25" },
  { accent: "#059669", bg: "from-[#ecfdf5] to-[#d1fae5]", text: "text-[#059669]", mono: "from-[#d1fae5] to-[#a7f3d0]", hover: "hover:border-[#059669]/25" },
  { accent: "#ea580c", bg: "from-[#fff7ed] to-[#ffedd5]", text: "text-[#ea580c]", mono: "from-[#ffedd5] to-[#fed7aa]", hover: "hover:border-[#ea580c]/25" },
  { accent: "#2563eb", bg: "from-[#eff6ff] to-[#dbeafe]", text: "text-[#2563eb]", mono: "from-[#dbeafe] to-[#bfdbfe]", hover: "hover:border-[#2563eb]/25" },
  { accent: "#db2777", bg: "from-[#fdf2f8] to-[#fce7f3]", text: "text-[#db2777]", mono: "from-[#fce7f3] to-[#fbcfe8]", hover: "hover:border-[#db2777]/25" },
  { accent: "#0d9488", bg: "from-[#f0fdfa] to-[#ccfbf1]", text: "text-[#0d9488]", mono: "from-[#ccfbf1] to-[#99f6e4]", hover: "hover:border-[#0d9488]/25" },
];

function cardColor(index: number) {
  return CARD_COLORS[index % CARD_COLORS.length];
}

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
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [previewTemplate, setPreviewTemplate] = useState<WorkflowTemplatePreview | null>(null);
  const [previewTemplateName, setPreviewTemplateName] = useState("");

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

  const handlePreviewTemplate = async (template: WorkflowTemplate) => {
    setPreviewTemplate(null);
    setPreviewTemplateName(template.name);
    setPreviewError("");
    setPreviewLoading(true);
    try {
      const preview = await getWorkflowTemplatePreview(template.template_id);
      setPreviewTemplate(preview);
    } catch (error) {
      setPreviewError(String(error || "Failed to load template preview."));
    } finally {
      setPreviewLoading(false);
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
                  const color = cardColor(i);
                  const steps = template.step_count || (Array.isArray(template.definition?.steps) ? template.definition.steps.length : 0);
                  const tags = Array.isArray(template.tags) ? template.tags.slice(0, 2) : [];

                  return (
                    <article
                      key={template.template_id}
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
                              className={`rounded-full bg-gradient-to-r ${color.bg} px-1.5 py-px text-[9px] font-medium ${color.text}`}
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

                      <div className="mt-3 flex items-center justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            void handlePreviewTemplate(template);
                          }}
                          className="rounded-full border border-black/[0.12] bg-white px-3 py-1 text-[11px] font-semibold text-[#475467] hover:bg-[#f8fafc]"
                        >
                          Preview output
                        </button>
                        <button
                          type="button"
                          onClick={() => onSelectTemplate(template)}
                          className="rounded-full bg-[#1d1d1f] px-3 py-1 text-[11px] font-semibold text-white hover:bg-black"
                        >
                          Use template
                        </button>
                      </div>
                    </article>
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
              className="group flex min-h-[180px] flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-black/[0.08] bg-white/40 transition hover:border-[#7c3aed]/30 hover:bg-[#f5f3ff]/50"
            >
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[#7c3aed]/10 text-[#7c3aed] transition group-hover:bg-[#7c3aed]/15">
                <Plus size={22} strokeWidth={2.5} />
              </div>
              <div className="text-center">
                <p className="text-[13px] font-semibold text-[#86868b] transition group-hover:text-[#1d1d1f]">
                  New Workflow
                </p>
                <p className="mt-0.5 text-[11px] text-[#aeaeb2]">Start from scratch</p>
              </div>
            </button>

            {/* Workflow cards */}
            {sorted.map((record, idx) => {
              const name = String(record.name || record.definition?.name || "Untitled").trim();
              const desc = String(record.description || record.definition?.description || "").trim();
              const steps = stepCount(record);
              const monogram = name.charAt(0).toUpperCase() || "W";
              const isDeleting = deletingId === record.id;
              const color = cardColor(idx);
              const stepNames = Array.isArray(record.definition?.steps)
                ? record.definition.steps
                    .slice(0, 4)
                    .map((s: { description?: string; step_id?: string }) => String(s.description || s.step_id || "").trim())
                    .filter(Boolean)
                : [];

              return (
                <article
                  key={record.id}
                  role="button"
                  tabIndex={isDeleting ? -1 : 0}
                  aria-disabled={isDeleting}
                  onClick={() => {
                    if (!isDeleting) {
                      void handleSelect(record);
                    }
                  }}
                  onKeyDown={(event) => {
                    if (isDeleting) {
                      return;
                    }
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      void handleSelect(record);
                    }
                  }}
                  className={`group relative flex flex-col overflow-hidden rounded-2xl border border-black/[0.06] bg-white text-left shadow-sm transition hover:shadow-md ${isDeleting ? "opacity-50" : ""} ${color.hover}`}
                >
                  {/* Color accent header */}
                  <div className={`flex items-center gap-3 bg-gradient-to-r ${color.bg} px-4 pb-3 pt-4`}>
                    <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br ${color.mono} text-[17px] font-bold ${color.text} shadow-sm`}>
                      {monogram}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[14px] font-semibold text-[#1d1d1f]">{name}</p>
                      {steps > 0 ? (
                        <p className={`mt-0.5 text-[11px] font-medium ${color.text}`}>
                          {steps} step{steps !== 1 ? "s" : ""}
                        </p>
                      ) : null}
                    </div>
                  </div>

                  {/* Body */}
                  <div className="flex flex-1 flex-col justify-between px-4 pb-3.5 pt-3">
                    {desc ? (
                      <p className="line-clamp-2 text-[12px] leading-[1.5] text-[#667085]">{desc}</p>
                    ) : stepNames.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {stepNames.map((s, i) => (
                          <span key={i} className="rounded-full border border-black/[0.06] bg-[#f8fafc] px-2 py-0.5 text-[10px] text-[#667085]">
                            {s.length > 24 ? `${s.slice(0, 24)}…` : s}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="text-[12px] text-[#aeaeb2]">No description</p>
                    )}

                    {/* Footer */}
                    <div className="mt-3 flex items-center justify-between">
                      {record.updated_at || record.created_at ? (
                        <span className="inline-flex items-center gap-1 text-[11px] text-[#aeaeb2]">
                          <Clock size={10} />
                          {timeAgo(record.updated_at || record.created_at)}
                        </span>
                      ) : <span />}
                      <ArrowRight size={13} className="text-[#aeaeb2] opacity-0 transition group-hover:opacity-100" />
                    </div>
                  </div>

                  {/* Delete button */}
                  <button
                    type="button"
                    onClick={(e) => void handleDelete(e, record.id)}
                    className="absolute right-2.5 top-2.5 flex h-7 w-7 items-center justify-center rounded-lg bg-white/80 text-[#aeaeb2] opacity-0 shadow-sm backdrop-blur transition hover:bg-[#ff3b30]/10 hover:text-[#ff3b30] group-hover:opacity-100"
                  >
                    {isDeleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                  </button>
                </article>
              );
            })}
          </div>
        )}
      </div>

      {(previewLoading || previewTemplate || previewError) ? (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-black/30 px-4">
          <div className="w-full max-w-[760px] rounded-2xl border border-black/[0.08] bg-white p-4 shadow-2xl">
            <div className="mb-2 flex items-start justify-between gap-2">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
                  Template preview
                </p>
                <p className="mt-0.5 text-[15px] font-semibold text-[#111827]">
                  {previewTemplate?.name || previewTemplateName || "Template output"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setPreviewTemplate(null);
                  setPreviewTemplateName("");
                  setPreviewError("");
                  setPreviewLoading(false);
                }}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-black/[0.1] text-[#475467] hover:bg-[#f8fafc]"
                aria-label="Close template preview"
              >
                <X size={14} />
              </button>
            </div>

            {previewLoading ? (
              <div className="flex items-center gap-2 rounded-xl border border-black/[0.08] bg-[#f8fafc] px-3 py-2 text-[12px] text-[#475467]">
                <Loader2 size={13} className="animate-spin" />
                Generating sample output...
              </div>
            ) : null}

            {previewError ? (
              <p className="rounded-xl border border-[#fecaca] bg-[#fff1f2] px-3 py-2 text-[12px] text-[#b42318]">
                {previewError}
              </p>
            ) : null}

            {previewTemplate?.sample_output ? (
              <pre className="mt-2 max-h-[420px] overflow-auto whitespace-pre-wrap rounded-xl border border-black/[0.08] bg-[#f8fafc] p-3 text-[12px] leading-[1.55] text-[#111827]">
                {previewTemplate.sample_output}
              </pre>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
