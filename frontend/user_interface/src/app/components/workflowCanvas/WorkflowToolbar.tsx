import {
  Bug,
  Calendar,
  Check,
  ChevronLeft,
  History,
  LayoutTemplate,
  Loader2,
  Play,
  Plus,
  Sparkles,
  Square,
} from "lucide-react";

type WorkflowToolbarProps = {
  isRunning: boolean;
  isDirty: boolean;
  onRun: () => void;
  onStop?: () => void;
  onAddStep: () => void;
  onSave: () => void;
  onSchedule: () => void;
  onOpenTemplates: () => void;
  onOpenNlBuilder: () => void;
  onOpenRunHistory: () => void;
  onOpenRunInspector: () => void;
  onAllWorkflows: () => void;
};

function WorkflowToolbar({
  isRunning,
  isDirty,
  onRun,
  onStop,
  onAddStep,
  onSave,
  onSchedule,
  onOpenTemplates,
  onOpenNlBuilder,
  onOpenRunHistory,
  onOpenRunInspector,
  onAllWorkflows,
}: WorkflowToolbarProps) {
  const isMac =
    typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.userAgent);

  return (
    <div className="flex items-center gap-1 rounded-[18px] border border-white/60 bg-white/80 p-1 shadow-[0_2px_20px_-4px_rgba(0,0,0,0.12),0_0_0_1px_rgba(0,0,0,0.04)] backdrop-blur-xl">
      {/* ── Left: Navigation ── */}
      <div className="flex items-center">
        {/* Back to gallery */}
        <button
          type="button"
          onClick={onAllWorkflows}
          title={`All Workflows (${isMac ? "⌘" : "Ctrl+"}K)`}
          className="group flex h-8 w-8 items-center justify-center rounded-xl text-[#86868b] transition-colors hover:bg-black/[0.05] hover:text-[#1d1d1f]"
        >
          <ChevronLeft size={16} strokeWidth={2} />
        </button>

        <span className="mx-0.5 h-4 w-px bg-black/[0.06]" />

        {/* Browse panels — icon-only with tooltips */}
        <button
          type="button"
          onClick={onOpenTemplates}
          title="Templates"
          className="flex h-8 w-8 items-center justify-center rounded-xl text-[#86868b] transition-colors hover:bg-black/[0.05] hover:text-[#1d1d1f]"
        >
          <LayoutTemplate size={15} strokeWidth={1.8} />
        </button>
        <button
          type="button"
          onClick={onOpenRunHistory}
          title="Run History"
          className="flex h-8 w-8 items-center justify-center rounded-xl text-[#86868b] transition-colors hover:bg-black/[0.05] hover:text-[#1d1d1f]"
        >
          <History size={15} strokeWidth={1.8} />
        </button>
        <button
          type="button"
          onClick={onOpenRunInspector}
          title="Debug Inspector"
          className="flex h-8 w-8 items-center justify-center rounded-xl text-[#86868b] transition-colors hover:bg-black/[0.05] hover:text-[#1d1d1f]"
        >
          <Bug size={15} strokeWidth={1.8} />
        </button>
      </div>

      <span className="mx-0.5 h-4 w-px bg-black/[0.06]" />

      {/* ── Center: Build actions ── */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onAddStep}
          className="inline-flex h-8 items-center gap-1.5 rounded-xl bg-black/[0.04] px-3 text-[12px] font-medium text-[#1d1d1f] transition hover:bg-black/[0.07]"
        >
          <Plus size={14} strokeWidth={2} />
          Add agent
        </button>
        <button
          type="button"
          onClick={onOpenNlBuilder}
          className="inline-flex h-8 items-center gap-1.5 rounded-xl bg-gradient-to-r from-[#f5f3ff] to-[#ede9fe] px-3 text-[12px] font-medium text-[#6d28d9] transition hover:from-[#ede9fe] hover:to-[#ddd6fe]"
        >
          <Sparkles size={13} strokeWidth={2} />
          AI Build
        </button>
      </div>

      <span className="mx-0.5 h-4 w-px bg-black/[0.06]" />

      {/* ── Right: Save state + Run ── */}
      <div className="flex items-center gap-1">
        {/* Save — contextual: shows state, clickable when dirty */}
        <button
          type="button"
          onClick={onSave}
          disabled={!isDirty}
          className={`inline-flex h-8 items-center gap-1 rounded-xl px-2.5 text-[12px] font-medium transition ${
            isDirty
              ? "bg-[#fef3c7] text-[#92400e] hover:bg-[#fde68a]"
              : "text-[#86868b]"
          }`}
        >
          {isDirty ? (
            <span className="h-[6px] w-[6px] rounded-full bg-[#f59e0b]" />
          ) : (
            <Check size={13} strokeWidth={2.5} className="text-[#34d399]" />
          )}
          {isDirty ? "Save" : "Saved"}
        </button>

        {/* Run / Stop — primary CTA */}
        {isRunning ? (
          <button
            type="button"
            onClick={() => onStop?.()}
            className="inline-flex h-8 items-center gap-1.5 rounded-xl bg-[#dc2626] px-4 text-[12px] font-semibold text-white shadow-[0_1px_3px_rgba(220,38,38,0.3)] transition hover:bg-[#b91c1c]"
          >
            <Square size={12} strokeWidth={2.5} fill="currentColor" />
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={onRun}
            className="inline-flex h-8 items-center gap-1.5 rounded-xl bg-[#1d1d1f] px-4 text-[12px] font-semibold text-white shadow-[0_1px_3px_rgba(0,0,0,0.2)] transition hover:bg-[#000]"
          >
            <Play size={12} strokeWidth={2.5} fill="currentColor" />
            Run
          </button>
        )}
      </div>
    </div>
  );
}

export { WorkflowToolbar };
export type { WorkflowToolbarProps };
