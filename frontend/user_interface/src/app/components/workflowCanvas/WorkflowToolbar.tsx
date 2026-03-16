import {
  LayoutTemplate,
  Play,
  Save,
  Sparkles,
  Square,
  History,
  Plus,
} from "lucide-react";

type WorkflowToolbarProps = {
  isRunning: boolean;
  isDirty: boolean;
  onRun: () => void;
  onStop?: () => void;
  onAddStep: () => void;
  onSave: () => void;
  onOpenTemplates: () => void;
  onOpenNlBuilder: () => void;
  onOpenRunHistory: () => void;
};

function WorkflowToolbar({
  isRunning,
  isDirty,
  onRun,
  onStop,
  onAddStep,
  onSave,
  onOpenTemplates,
  onOpenNlBuilder,
  onOpenRunHistory,
}: WorkflowToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-black/[0.08] bg-white/95 p-1.5 shadow-sm backdrop-blur">
      <button
        type="button"
        onClick={onOpenTemplates}
        className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.1] bg-white px-2.5 py-1.5 text-[12px] font-semibold text-[#344054] transition hover:bg-[#f8fafc]"
      >
        <LayoutTemplate size={13} />
        Templates
      </button>
      <button
        type="button"
        onClick={onOpenNlBuilder}
        className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.1] bg-white px-2.5 py-1.5 text-[12px] font-semibold text-[#344054] transition hover:bg-[#f8fafc]"
      >
        <Sparkles size={13} />
        NL Build
      </button>
      <button
        type="button"
        onClick={onOpenRunHistory}
        className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.1] bg-white px-2.5 py-1.5 text-[12px] font-semibold text-[#344054] transition hover:bg-[#f8fafc]"
      >
        <History size={13} />
        Runs
      </button>
      <span className="mx-1 hidden h-5 w-px bg-black/[0.08] md:block" />
      <button
        type="button"
        onClick={onAddStep}
        className="inline-flex items-center gap-1.5 rounded-full border border-black/[0.1] bg-white px-2.5 py-1.5 text-[12px] font-semibold text-[#344054] transition hover:bg-[#f8fafc]"
      >
        <Plus size={13} />
        Add step
      </button>
      <button
        type="button"
        onClick={onSave}
        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-semibold transition ${
          isDirty
            ? "bg-[#111827] text-white hover:bg-[#0f172a]"
            : "border border-black/[0.1] bg-white text-[#344054] hover:bg-[#f8fafc]"
        }`}
      >
        <Save size={13} />
        {isDirty ? "Save" : "Saved"}
      </button>
      {isRunning ? (
        <button
          type="button"
          onClick={() => onStop?.()}
          className="inline-flex items-center gap-1.5 rounded-full bg-[#111827] px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-[#0f172a]"
        >
          <Square size={13} />
          Stop
        </button>
      ) : (
        <button
          type="button"
          onClick={onRun}
          className="inline-flex items-center gap-1.5 rounded-full bg-[#111827] px-3 py-1.5 text-[12px] font-semibold text-white hover:bg-[#0f172a]"
        >
          <Play size={13} />
          Run
        </button>
      )}
    </div>
  );
}

export { WorkflowToolbar };
export type { WorkflowToolbarProps };
