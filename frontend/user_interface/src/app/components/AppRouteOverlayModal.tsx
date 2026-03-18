import { X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

type AppRouteOverlayModalProps = {
  title: string;
  subtitle: string;
  onClose: () => void;
  children: ReactNode;
  headerActions?: ReactNode;
  headerToolbar?: ReactNode;
  contentClassName?: string;
};

export function AppRouteOverlayModal({
  title,
  subtitle,
  onClose,
  children,
  headerActions = null,
  headerToolbar = null,
  contentClassName = "",
}: AppRouteOverlayModalProps) {
  const [visible, setVisible] = useState(false);
  const closingRef = useRef(false);

  // Animate in on mount
  useEffect(() => {
    const frame = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  const handleClose = () => {
    if (closingRef.current) return;
    closingRef.current = true;
    setVisible(false);
    // Wait for the exit animation to finish before unmounting
    setTimeout(onClose, 220);
  };

  return (
    <div
      className={`fixed inset-0 z-[172] flex items-center justify-center p-4 transition-opacity duration-200 sm:p-6 md:p-10 ${
        visible ? "opacity-100" : "opacity-0"
      }`}
      role="dialog"
      aria-modal="true"
      aria-label={`${title} panel`}
      onClick={handleClose}
    >
      <div
        className={`absolute inset-0 bg-[radial-gradient(circle_at_18%_6%,rgba(255,255,255,0.36)_0%,rgba(241,241,244,0.7)_36%,rgba(27,27,31,0.4)_100%)] transition-all duration-200 ${
          visible ? "backdrop-blur-[10px]" : "backdrop-blur-none"
        }`}
      />
      <div
        className={`relative z-[173] flex h-[min(92vh,1020px)] w-full max-w-[1380px] min-h-[620px] flex-col overflow-hidden rounded-[30px] border border-white/70 bg-[linear-gradient(155deg,#fcfcfd_0%,#f6f6f8_44%,#ececef_100%)] shadow-[0_46px_124px_-48px_rgba(0,0,0,0.62)] transition-all duration-200 ${
          visible ? "scale-100 opacity-100" : "scale-[0.97] opacity-0"
        }`}
        style={{
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', sans-serif",
        }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-black/[0.08] px-6 pb-4 pt-5">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="text-[12px] font-semibold uppercase tracking-[0.16em] text-[#667085]">
                Workspace
              </p>
              <h2 className="mt-1 truncate text-[31px] font-semibold tracking-[-0.02em] text-[#111827]">
                {title}
              </h2>
              <p className="mt-1 text-[14px] text-[#5f5f65]">{subtitle}</p>
            </div>
            <div className="flex shrink-0 items-start gap-2">
              {headerActions}
              <button
                type="button"
                onClick={handleClose}
                className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-black/[0.08] bg-white/70 text-[#6e6e73] transition-colors hover:bg-white hover:text-[#1d1d1f]"
                aria-label={`Close ${title}`}
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>
          {headerToolbar ? <div className="mt-3">{headerToolbar}</div> : null}
        </div>

        <div
          className={`min-h-0 flex-1 overflow-hidden bg-white/70 p-2 ${contentClassName}`.trim()}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
