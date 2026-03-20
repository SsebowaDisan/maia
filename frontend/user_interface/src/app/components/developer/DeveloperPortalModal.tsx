/** Full-screen modal wrapper for the Developer Portal page. */
import { useEffect, useRef, useState } from "react";
import { Code2, X } from "lucide-react";
import { DeveloperPortalPage } from "../../pages/DeveloperPortalPage";

type Props = {
  open: boolean;
  onClose: () => void;
};

export function DeveloperPortalModal({ open, onClose }: Props) {
  const [visible, setVisible] = useState(false);
  const closingRef = useRef(false);

  useEffect(() => {
    if (!open) { setVisible(false); return; }
    const frame = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(frame);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") handleClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  const handleClose = () => {
    if (closingRef.current) return;
    closingRef.current = true;
    setVisible(false);
    setTimeout(() => { closingRef.current = false; onClose(); }, 200);
  };

  if (!open) return null;

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center transition-opacity duration-200 ${visible ? "opacity-100" : "opacity-0"}`}>
      <div className="absolute inset-0 bg-black/30 backdrop-blur-md" onClick={handleClose} />
      <div className={`relative flex h-[88vh] w-[92vw] max-w-5xl flex-col overflow-hidden rounded-2xl border border-black/[0.08] bg-[#f6f6f7] shadow-[0_24px_80px_-16px_rgba(0,0,0,0.22)] transition-all duration-200 ${visible ? "scale-100" : "scale-[0.97]"}`}>
        <div className="flex items-center justify-between border-b border-black/[0.06] bg-white/80 px-5 py-3 backdrop-blur-xl">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#fff7ed]">
              <Code2 size={15} className="text-[#ea580c]" />
            </div>
            <h2 className="text-[14px] font-semibold text-[#1d1d1f]">Developer Portal</h2>
          </div>
          <button onClick={handleClose} className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[#86868b] transition-colors hover:bg-black/[0.05] hover:text-[#1d1d1f]" aria-label="Close">
            <X size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <DeveloperPortalPage />
        </div>
      </div>
    </div>
  );
}
