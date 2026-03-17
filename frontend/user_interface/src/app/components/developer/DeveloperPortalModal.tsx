/** Full-screen modal wrapper for the Developer Portal page. */
import { useEffect } from "react";
import { X } from "lucide-react";
import { DeveloperPortalPage } from "../../pages/DeveloperPortalPage";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function DeveloperPortalModal({ open, onClose }: Props) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/30 backdrop-blur-md"
        onClick={onClose}
      />

      {/* Modal panel */}
      <div
        className="relative w-[92vw] max-w-5xl h-[88vh] rounded-[20px] border border-white/20 bg-[#f6f6f7]/95 backdrop-blur-2xl flex flex-col overflow-hidden"
        style={{
          boxShadow:
            "0 24px 80px -16px rgba(0,0,0,0.22), 0 8px 24px -8px rgba(0,0,0,0.10), inset 0 1px 0 rgba(255,255,255,0.6)",
        }}
      >
        {/* Header — frosted glass */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-black/[0.06] bg-white/60 backdrop-blur-xl">
          <div className="flex items-center gap-2.5">
            <div className="flex gap-1.5">
              <button
                onClick={onClose}
                className="group flex h-3 w-3 items-center justify-center rounded-full bg-[#ff5f57] transition-all hover:brightness-90"
                title="Close"
              >
                <X className="h-2 w-2 text-[#4a0002] opacity-0 group-hover:opacity-100 transition-opacity" />
              </button>
              <div className="h-3 w-3 rounded-full bg-[#febc2e]" />
              <div className="h-3 w-3 rounded-full bg-[#28c840]" />
            </div>
            <div className="h-4 w-px bg-black/[0.08]" />
            <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Developer Portal</h2>
          </div>
          <button
            onClick={onClose}
            className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-[#86868b] transition-colors hover:bg-black/[0.05] hover:text-[#1d1d1f]"
            title="Close"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content — scrollable */}
        <div className="flex-1 overflow-y-auto">
          <DeveloperPortalPage />
        </div>
      </div>
    </div>
  );
}
