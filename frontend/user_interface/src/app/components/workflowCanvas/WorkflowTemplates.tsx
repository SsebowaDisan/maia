import { Loader2, RefreshCw, X } from "lucide-react";

import type { WorkflowTemplate } from "../../../api/client/types";

type WorkflowTemplatesProps = {
  open: boolean;
  loading: boolean;
  templates: WorkflowTemplate[];
  onClose: () => void;
  onRefresh: () => void;
  onSelectTemplate: (template: WorkflowTemplate) => void;
};

function WorkflowTemplates({
  open,
  loading,
  templates,
  onClose,
  onRefresh,
  onSelectTemplate,
}: WorkflowTemplatesProps) {
  if (!open) {
    return null;
  }

  return (
    <aside className="absolute left-4 top-16 z-20 w-[360px] max-w-[92vw] overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-xl">
      <div className="flex items-center justify-between border-b border-black/[0.06] px-4 py-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">Templates</p>
          <p className="text-[14px] font-semibold text-[#101828]">Starter workflows</p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onRefresh}
            className="rounded-full border border-black/[0.08] p-1.5 text-[#475467] hover:bg-[#f8fafc]"
            aria-label="Refresh templates"
          >
            <RefreshCw size={13} />
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-black/[0.08] p-1.5 text-[#475467] hover:bg-[#f8fafc]"
            aria-label="Close templates"
          >
            <X size={13} />
          </button>
        </div>
      </div>

      <div className="max-h-[440px] space-y-2 overflow-y-auto p-3">
        {loading ? (
          <div className="flex items-center gap-2 rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 text-[12px] text-[#475467]">
            <Loader2 size={13} className="animate-spin" />
            Loading templates...
          </div>
        ) : null}
        {!loading && templates.length === 0 ? (
          <p className="rounded-xl border border-black/[0.06] bg-[#fcfcfd] p-3 text-[12px] text-[#667085]">
            No templates available.
          </p>
        ) : null}
        {templates.map((template) => (
          <button
            key={template.template_id}
            type="button"
            onClick={() => onSelectTemplate(template)}
            className="block w-full rounded-xl border border-black/[0.08] bg-white p-3 text-left transition hover:border-[#d0d5dd] hover:bg-[#fcfcfd]"
          >
            <p className="text-[13px] font-semibold text-[#101828]">{template.name}</p>
            <p className="mt-1 text-[12px] text-[#475467]">{template.description}</p>
            <p className="mt-2 text-[11px] font-semibold uppercase tracking-[0.09em] text-[#667085]">
              {template.step_count} steps
            </p>
          </button>
        ))}
      </div>
    </aside>
  );
}

export { WorkflowTemplates };
export type { WorkflowTemplatesProps };
