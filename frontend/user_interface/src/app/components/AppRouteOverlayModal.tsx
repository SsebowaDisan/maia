import { X } from "lucide-react";
import type { ReactNode } from "react";

type AppRouteOverlayModalProps = {
  title: string;
  subtitle: string;
  onClose: () => void;
  children: ReactNode;
};

export function AppRouteOverlayModal({
  title,
  subtitle,
  onClose,
  children,
}: AppRouteOverlayModalProps) {
  return (
    <div
      className="fixed inset-0 z-[172] flex items-center justify-center p-4 sm:p-6 md:p-10"
      role="dialog"
      aria-modal="true"
      aria-label={`${title} panel`}
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_6%,rgba(255,255,255,0.36)_0%,rgba(241,241,244,0.7)_36%,rgba(27,27,31,0.4)_100%)] backdrop-blur-[10px]" />
      <div
        className="relative z-[173] flex h-[min(92vh,1020px)] w-full max-w-[1380px] min-h-[620px] flex-col overflow-hidden rounded-[30px] border border-white/70 bg-[linear-gradient(155deg,#fcfcfd_0%,#f6f6f8_44%,#ececef_100%)] shadow-[0_46px_124px_-48px_rgba(0,0,0,0.62)]"
        style={{
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif",
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-black/[0.08] px-6 pb-4 pt-5">
          <div className="min-w-0">
            <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">
              Workspace
            </p>
            <h2 className="mt-1 truncate text-[31px] font-semibold tracking-[-0.02em] text-[#111827]">
              {title}
            </h2>
            <p className="mt-1 text-[14px] text-[#5f5f65]">{subtitle}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-black/[0.08] bg-white/70 text-[#6e6e73] transition-colors hover:bg-white hover:text-[#1d1d1f]"
            aria-label={`Close ${title}`}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden bg-white/70 p-2">{children}</div>
      </div>
    </div>
  );
}
