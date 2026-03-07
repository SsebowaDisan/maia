import { ArrowUpRight, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type NodeFollowUpModalProps = {
  open: boolean;
  nodeTitle: string;
  nodeText?: string;
  sourceName?: string;
  defaultPrompt: string;
  submitting?: boolean;
  onCancel: () => void;
  onSubmit: (prompt: string) => Promise<void>;
};

export function NodeFollowUpModal({
  open,
  nodeTitle,
  nodeText = "",
  sourceName = "",
  defaultPrompt,
  submitting = false,
  onCancel,
  onSubmit,
}: NodeFollowUpModalProps) {
  const [prompt, setPrompt] = useState(defaultPrompt);
  const [errorText, setErrorText] = useState("");
  const cleanedTitle = useMemo(() => String(nodeTitle || "").trim(), [nodeTitle]);
  const cleanedText = useMemo(() => String(nodeText || "").trim(), [nodeText]);
  const cleanedSourceName = useMemo(() => String(sourceName || "").trim(), [sourceName]);

  useEffect(() => {
    if (!open) {
      return;
    }
    setPrompt(defaultPrompt);
    setErrorText("");
  }, [defaultPrompt, open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting) {
        event.preventDefault();
        onCancel();
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        void submit();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onCancel, open, submitting, prompt]);

  if (!open) {
    return null;
  }

  const trimmedPrompt = prompt.trim();
  const canSubmit = trimmedPrompt.length > 0 && !submitting;

  const submit = async () => {
    if (!canSubmit) {
      return;
    }
    setErrorText("");
    try {
      await onSubmit(trimmedPrompt);
    } catch (error) {
      setErrorText(
        error instanceof Error ? error.message : String(error || "Could not send follow-up question."),
      );
    }
  };

  return (
    <div
      className="fixed inset-0 z-[220] flex items-center justify-center p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Ask a focused follow-up question"
      onClick={() => {
        if (!submitting) {
          onCancel();
        }
      }}
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_8%,rgba(255,255,255,0.45)_0%,rgba(241,241,244,0.7)_36%,rgba(27,27,31,0.42)_100%)] backdrop-blur-[10px]" />
      <div
        className="relative z-[221] w-full max-w-[680px] overflow-hidden rounded-[28px] border border-white/70 bg-[linear-gradient(160deg,#fcfcfd_0%,#f6f6f8_46%,#ececef_100%)] shadow-[0_42px_116px_-48px_rgba(0,0,0,0.62)]"
        style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif" }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-black/[0.08] px-5 py-4">
          <div className="flex items-center gap-4">
            <div className="inline-flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#28c940]" />
            </div>
            <div className="inline-flex items-center gap-2 rounded-full border border-black/[0.08] bg-white/85 px-3 py-1">
              <Sparkles className="h-3.5 w-3.5 text-[#5f5f65]" />
              <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-[#4f4f55]">Follow-Up</span>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/[0.08] text-[#6e6e73] transition-colors hover:bg-white hover:text-[#1d1d1f] disabled:opacity-45"
            aria-label="Close follow-up dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-4 px-5 pb-5 pt-4">
          <div>
            <p className="text-[22px] font-semibold tracking-[-0.02em] text-[#17171b]">Ask about this node</p>
            <p className="mt-1 text-[13px] text-[#5f5f65]">
              Refine the selected node with a focused question and Maia will continue from that context.
            </p>
          </div>

          <div className="rounded-2xl border border-black/[0.08] bg-white/88 px-4 py-3">
            <p className="text-[11px] uppercase tracking-[0.1em] text-[#7c7c83]">Selected node</p>
            <p className="mt-1 text-[15px] font-medium text-[#1d1d1f]">
              {cleanedTitle || "Untitled node"}
            </p>
            {cleanedSourceName ? <p className="mt-1 text-[12px] text-[#6b6b72]">Source: {cleanedSourceName}</p> : null}
            {cleanedText ? (
              <p className="mt-2 line-clamp-2 text-[12px] leading-relaxed text-[#5f5f65]">{cleanedText}</p>
            ) : null}
          </div>

          <div className="rounded-2xl border border-black/[0.08] bg-white/92 p-4">
            <label className="text-[12px] font-medium text-[#1d1d1f]" htmlFor="mindmap-node-follow-up">
              Follow-up question
            </label>
            <textarea
              id="mindmap-node-follow-up"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              placeholder="Ask a focused follow-up question..."
              rows={3}
              autoFocus
              className="mt-2 w-full resize-y rounded-xl border border-black/[0.12] bg-white px-3 py-2 text-[14px] text-[#1d1d1f] placeholder:text-[#8a8a90] focus:outline-none focus:ring-2 focus:ring-black/10"
            />
            <div className="mt-2 flex items-center justify-between text-[11px] text-[#6e6e73]">
              <span>Tip: Use Cmd/Ctrl + Enter to send quickly.</span>
              <span>{trimmedPrompt.length} chars</span>
            </div>
          </div>

          {errorText ? (
            <div className="rounded-xl border border-[#f2c99f] bg-[#fff6eb] px-3 py-2 text-[12px] text-[#8a4a0f]">
              {errorText}
            </div>
          ) : null}

          <div className="flex items-center justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onCancel}
              disabled={submitting}
              className="h-10 rounded-xl border border-black/[0.1] bg-white/90 px-4 text-[13px] text-[#2e2e32] hover:bg-white disabled:opacity-45"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => {
                void submit();
              }}
              disabled={!canSubmit}
              className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#1d1d1f] px-4 text-[13px] font-medium text-white transition-colors hover:bg-[#2a2a2d] disabled:opacity-45"
            >
              {submitting ? "Sending..." : "Ask Follow-Up"}
              <ArrowUpRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
