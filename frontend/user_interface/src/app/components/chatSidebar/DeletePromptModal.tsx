import { Loader2 } from "lucide-react";

type DeletePromptModalProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  inputValue: string;
  busy: boolean;
  errorMessage: string;
  onClose: () => void;
  onInputChange: (value: string) => void;
  onConfirm: () => void;
};

export function DeletePromptModal({
  open,
  title,
  description,
  confirmLabel,
  inputValue,
  busy,
  errorMessage,
  onClose,
  onInputChange,
  onConfirm,
}: DeletePromptModalProps) {
  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-[130] flex items-center justify-center p-5"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="absolute inset-0 bg-black/35 backdrop-blur-[10px]" />
      <div
        className="relative z-[131] w-full max-w-[440px] rounded-2xl border border-black/[0.1] bg-white shadow-[0_24px_70px_rgba(0,0,0,0.3)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-black/[0.08] px-5 py-4">
          <p className="text-[17px] font-semibold tracking-tight text-[#1d1d1f]">{title}</p>
          <p className="mt-1 text-[13px] leading-relaxed text-[#6e6e73]">{description}</p>
        </div>
        <div className="px-5 py-4">
          <label className="block text-[12px] font-medium text-[#6e6e73]">
            Type <span className="rounded bg-[#f5f5f7] px-1 py-0.5 font-semibold text-[#1d1d1f]">delete</span> to
            confirm
          </label>
          <input
            value={inputValue}
            onChange={(event) => onInputChange(event.target.value)}
            disabled={busy}
            placeholder="delete"
            className="mt-2 h-10 w-full rounded-xl border border-black/[0.1] bg-white px-3 text-[14px] text-[#1d1d1f] placeholder:text-[#a1a1aa] focus:outline-none focus:ring-2 focus:ring-black/10 disabled:opacity-60"
          />
          {errorMessage ? <p className="mt-2 text-[12px] text-[#d44848]">{errorMessage}</p> : null}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-black/[0.08] px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="h-9 rounded-xl border border-black/[0.08] bg-white px-3 text-[13px] font-semibold text-[#1d1d1f] transition-colors hover:bg-[#f5f5f7] disabled:cursor-not-allowed disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy || inputValue.trim().toLowerCase() !== "delete"}
            className="inline-flex h-9 items-center gap-2 rounded-xl bg-[#1d1d1f] px-3 text-[13px] font-semibold text-white transition-colors hover:bg-[#343438] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            <span>{busy ? "Deleting..." : confirmLabel}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
