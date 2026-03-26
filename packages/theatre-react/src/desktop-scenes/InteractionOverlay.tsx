import { overlayForInteractionEvent } from "./sceneEvents";

type InteractionOverlayProps = {
  sceneSurface: string;
  activeEventType: string;
  activeDetail: string;
  scrollDirection: string;
  action: string;
  actionPhase: string;
  actionStatus: string;
  actionTargetLabel: string;
};

function InteractionOverlay({
  sceneSurface,
  activeEventType,
  activeDetail,
  scrollDirection,
  action,
  actionPhase,
  actionStatus,
  actionTargetLabel,
}: InteractionOverlayProps) {
  const overlay = overlayForInteractionEvent({
    eventType: activeEventType,
    sceneSurface,
    activeDetail,
    scrollDirection,
    action,
    actionPhase,
    actionStatus,
    actionTargetLabel,
  });
  if (!overlay) return null;

  if (overlay.variant === "human-alert") {
    return (
      <div className="pointer-events-none absolute left-1/2 top-5 z-30 w-[min(88%,560px)] -translate-x-1/2 rounded-xl border border-white/20 bg-[#121722] px-3.5 py-2.5 text-[11px] text-white/92 shadow-[0_12px_28px_-20px_rgba(0,0,0,0.9)]">
        <p className="font-semibold tracking-[0.01em]">{overlay.text}</p>
        <p className="mt-0.5 line-clamp-2 text-white/78">{overlay.detail || "Complete verification, then continue."}</p>
      </div>
    );
  }
  if (overlay.variant === "center-pill") {
    return (
      <div
        className={`pointer-events-none absolute left-1/2 top-1/2 z-30 -translate-x-1/2 -translate-y-1/2 rounded-full border px-3.5 py-1.5 text-[10px] font-medium tracking-[0.02em] shadow-[0_14px_30px_-20px_rgba(0,0,0,0.65)] backdrop-blur-sm ${
          overlay.pulse
            ? "animate-pulse border-white/35 bg-[#111827]/85 text-white"
            : "border-white/25 bg-[#111827]/80 text-white/95"
        }`}
      >
        {overlay.text}
      </div>
    );
  }
  return (
    <div className="pointer-events-none absolute left-1/2 top-1/2 z-30 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/25 bg-[#111827]/80 px-3.5 py-1.5 text-[10px] font-medium text-white/95 shadow-[0_14px_30px_-20px_rgba(0,0,0,0.65)] backdrop-blur-sm">
      {overlay.text}
    </div>
  );
}

export { InteractionOverlay };
