import { useEffect, useState } from "react";
import { Loader2, Sparkles, X } from "lucide-react";

type NLBuilderSheetProps = {
  open: boolean;
  isGenerating: boolean;
  streamLog: string;
  error: string;
  onClose: () => void;
  onGenerate: (description: string, maxSteps: number) => Promise<void>;
};

function NLBuilderSheet({
  open,
  isGenerating,
  streamLog,
  error,
  onClose,
  onGenerate,
}: NLBuilderSheetProps) {
  const [description, setDescription] = useState("");
  const [maxSteps, setMaxSteps] = useState(8);

  useEffect(() => {
    if (!open) {
      setDescription("");
      setMaxSteps(8);
    }
  }, [open]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="absolute inset-0 z-20 flex items-end bg-black/20 p-4 backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className="mx-auto w-full max-w-[920px] rounded-3xl border border-black/[0.08] bg-white shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-black/[0.06] px-5 py-4">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center justify-center rounded-full border border-black/[0.08] bg-[#f8fafc] p-2 text-[#344054]">
              <Sparkles size={14} />
            </span>
            <div>
              <p className="text-[12px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
                Build from description
              </p>
              <p className="text-[16px] font-semibold text-[#101828]">Generate workflow with AI</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-black/[0.08] p-2 text-[#475467] hover:bg-[#f8fafc]"
            aria-label="Close NL builder"
          >
            <X size={14} />
          </button>
        </div>

        <div className="grid grid-cols-1 gap-4 p-5 lg:grid-cols-[1fr_320px]">
          <div className="space-y-3">
            <label className="block">
              <span className="mb-1 block text-[12px] font-semibold text-[#344054]">
                Describe what you want the workflow to do
              </span>
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={6}
                placeholder="Research competitor launches weekly, summarize risks, and send email report to leadership."
                className="w-full resize-none rounded-2xl border border-black/[0.12] px-3 py-2.5 text-[14px] text-[#101828] outline-none focus:border-[#94a3b8]"
              />
            </label>
            <div className="flex items-center gap-3">
              <label className="inline-flex items-center gap-2 text-[12px] text-[#475467]">
                <span className="font-semibold">Max steps</span>
                <input
                  type="number"
                  min={2}
                  max={20}
                  value={maxSteps}
                  onChange={(event) => setMaxSteps(Math.max(2, Math.min(20, Number(event.target.value) || 8)))}
                  className="w-16 rounded-lg border border-black/[0.12] px-2 py-1 text-[12px] text-[#101828] outline-none focus:border-[#94a3b8]"
                />
              </label>
              <button
                type="button"
                onClick={() => onGenerate(description, maxSteps)}
                disabled={isGenerating || !description.trim()}
                className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-[#111827] px-4 py-2 text-[12px] font-semibold text-white hover:bg-[#0f172a] disabled:opacity-60"
              >
                {isGenerating ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                Generate workflow
              </button>
            </div>
            {error ? <p className="text-[12px] font-medium text-[#b42318]">{error}</p> : null}
          </div>

          <aside className="rounded-2xl border border-black/[0.08] bg-[#fcfcfd] p-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#667085]">
              Builder stream
            </p>
            <div className="mt-2 h-[180px] overflow-y-auto rounded-xl border border-black/[0.06] bg-white p-2 text-[12px] text-[#475467]">
              {streamLog.trim() ? streamLog : "No output yet."}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

export { NLBuilderSheet };
export type { NLBuilderSheetProps };
