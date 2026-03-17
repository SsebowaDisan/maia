import { Check } from "lucide-react";

type DoneStageOverlayProps = {
  open: boolean;
  title: string;
  detail: string;
};

function DoneStageOverlay({ open, title, detail }: DoneStageOverlayProps) {
  if (!open) {
    return null;
  }

  const headline = String(title || "").trim() || "Task completed";
  const summary =
    String(detail || "").trim() || "All requested work is complete and ready for handoff.";

  return (
    <div className="pointer-events-none absolute inset-0 z-40 flex items-center justify-center bg-[radial-gradient(circle_at_30%_0%,rgba(163,196,255,0.34),rgba(243,247,255,0.9)_55%,rgba(229,240,255,0.92)_100%)] p-6">
      <div className="w-full max-w-[640px] rounded-[28px] border border-black/[0.08] bg-white/95 px-8 py-7 text-[#111827] shadow-[0_40px_80px_-56px_rgba(15,23,42,0.55)] backdrop-blur-sm">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full border border-[#c7d7f7] bg-[radial-gradient(circle_at_30%_30%,#f8fbff,#dbe8ff)] shadow-[0_14px_28px_-20px_rgba(109,40,217,0.8)]">
          <span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#7c3aed] text-white shadow-[0_10px_18px_-12px_rgba(124,58,237,0.9)]">
            <Check className="h-5 w-5" strokeWidth={2.6} />
          </span>
        </div>
        <p className="text-center text-[11px] font-semibold uppercase tracking-[0.14em] text-[#64748b]">
          Completed
        </p>
        <p className="mt-2 text-center text-[clamp(22px,3.1vw,34px)] font-semibold leading-[1.1] tracking-[-0.02em] text-[#1f2937]">
          {headline}
        </p>
        <p className="mx-auto mt-3 max-w-[520px] text-center text-[14px] leading-[1.5] text-[#475569]">
          {summary}
        </p>
        <div className="mt-6 h-[5px] overflow-hidden rounded-full bg-[#dbe7ff]">
          <div className="h-full w-full rounded-full bg-[linear-gradient(90deg,#c4b5fd_0%,#8b5cf6_45%,#7c3aed_100%)]" />
        </div>
      </div>
    </div>
  );
}

export { DoneStageOverlay };
