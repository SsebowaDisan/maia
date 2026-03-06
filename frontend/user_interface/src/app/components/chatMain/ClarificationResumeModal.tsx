import { AlertCircle, Loader2, Play, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ClarificationPrompt } from "../../types";

type ClarificationResumeModalProps = {
  prompt: ClarificationPrompt;
  onDismiss: () => void;
  onSubmit: (answers: string[]) => Promise<void>;
};

function ClarificationResumeModal({ prompt, onDismiss, onSubmit }: ClarificationResumeModalProps) {
  const fields = useMemo(() => {
    const fromQuestions = prompt.questions.filter((item) => item.trim().length > 0);
    if (fromQuestions.length > 0) {
      return fromQuestions;
    }
    return prompt.missingRequirements.filter((item) => item.trim().length > 0);
  }, [prompt.missingRequirements, prompt.questions]);
  const [answers, setAnswers] = useState<string[]>(() => fields.map(() => ""));
  const [submitting, setSubmitting] = useState(false);
  const [errorText, setErrorText] = useState("");

  useEffect(() => {
    setAnswers(fields.map(() => ""));
    setSubmitting(false);
    setErrorText("");
  }, [prompt.runId, fields]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting) {
        onDismiss();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onDismiss, submitting]);

  const canContinue = answers.every((item) => item.trim().length > 0);

  const submit = async () => {
    if (!canContinue || submitting) {
      return;
    }
    setSubmitting(true);
    setErrorText("");
    try {
      await onSubmit(answers.map((item) => item.trim()));
    } catch (error) {
      setErrorText(
        error instanceof Error ? error.message : String(error || "Unable to continue the process."),
      );
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[210] flex items-center justify-center p-4 sm:p-6" onClick={onDismiss}>
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_14%_10%,rgba(255,255,255,0.42)_0%,rgba(241,241,244,0.68)_34%,rgba(17,17,20,0.42)_100%)] backdrop-blur-[10px]" />
      <div
        className="relative z-[211] flex max-h-[min(92vh,920px)] w-full max-w-[880px] flex-col overflow-hidden rounded-[28px] border border-white/70 bg-[linear-gradient(164deg,#fcfcfd_0%,#f6f6f8_48%,#ececef_100%)] shadow-[0_42px_118px_-52px_rgba(0,0,0,0.6)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-black/[0.08] px-6 py-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.1em] text-[#6e6e73]">Input Required</p>
            <p className="mt-1 text-[20px] font-semibold tracking-[-0.015em] text-[#16161a]">
              Continue Paused Process
            </p>
            <p className="mt-1 text-[13px] text-[#5f5f65]">
              Maia paused execution because details were missing. Fill all fields to resume immediately.
            </p>
          </div>
          <button
            type="button"
            onClick={onDismiss}
            disabled={submitting}
            className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/[0.08] bg-white/80 text-[#6e6e73] transition-colors hover:text-[#1d1d1f] disabled:opacity-45"
            aria-label="Close clarification prompt"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <div className="rounded-2xl border border-black/[0.08] bg-white/88 px-4 py-3 text-[12px] text-[#4f4f55]">
            <p className="font-medium text-[#1d1d1f]">Original request</p>
            <p className="mt-1 leading-relaxed">{prompt.originalRequest}</p>
          </div>

          <div className="mt-4 space-y-3">
            {fields.map((label, index) => (
              <div key={`${prompt.runId}-${index}`} className="rounded-2xl border border-black/[0.08] bg-white/92 p-4">
                <label className="text-[12px] font-medium text-[#1d1d1f]">{label}</label>
                <textarea
                  value={answers[index] || ""}
                  onChange={(event) =>
                    setAnswers((prev) => {
                      const next = [...prev];
                      next[index] = event.target.value;
                      return next;
                    })
                  }
                  rows={3}
                  placeholder="Provide the missing detail..."
                  className="mt-2 w-full resize-y rounded-xl border border-black/[0.1] bg-white px-3 py-2 text-[13px] text-[#1d1d1f] placeholder:text-[#8a8a90] focus:outline-none focus:ring-2 focus:ring-black/10"
                />
              </div>
            ))}
          </div>

          {errorText ? (
            <div className="mt-4 inline-flex items-start gap-2 rounded-xl border border-[#f2c99f] bg-[#fff6eb] px-3 py-2 text-[12px] text-[#8a4a0f]">
              <AlertCircle className="mt-[1px] h-3.5 w-3.5 shrink-0" />
              <p>{errorText}</p>
            </div>
          ) : null}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-black/[0.08] px-6 py-4">
          <button
            type="button"
            onClick={onDismiss}
            disabled={submitting}
            className="h-10 rounded-xl border border-black/[0.1] bg-white/90 px-4 text-[13px] text-[#2e2e32] hover:bg-white disabled:opacity-45"
          >
            Later
          </button>
          <button
            type="button"
            onClick={() => {
              void submit();
            }}
            disabled={!canContinue || submitting}
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-[#1d1d1f] px-4 text-[13px] font-medium text-white hover:bg-[#2c2c30] disabled:opacity-45"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Continuing...
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5" />
                Continue Process
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export { ClarificationResumeModal };
