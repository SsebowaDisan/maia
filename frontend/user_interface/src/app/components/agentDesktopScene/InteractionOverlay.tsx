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
  if (!overlay) {
    return null;
  }
  if (overlay.variant === "human-alert") {
    return (
      <div className="pointer-events-none absolute inset-x-6 top-14 z-30 rounded-xl border border-white/30 bg-black/76 px-3 py-2 text-[11px] text-white/92 shadow-[0_10px_24px_-18px_rgba(0,0,0,0.75)]">
        <p className="font-semibold tracking-[0.01em]">{overlay.text}</p>
        <p className="mt-0.5 line-clamp-2 text-white/78">{overlay.detail || "Complete verification, then continue."}</p>
      </div>
    );
  }
  if (overlay.variant === "center-pill") {
    return (
      <div
        className={`pointer-events-none absolute left-1/2 top-14 z-30 -translate-x-1/2 rounded-full border px-3 py-1 text-[10px] font-medium tracking-[0.02em] ${
          overlay.pulse
            ? "animate-pulse border-white/35 bg-black/75 text-white"
            : "border-white/30 bg-black/70 text-white/95"
        }`}
      >
        {overlay.text}
      </div>
    );
  }
  return (
    <div className="pointer-events-none absolute left-4 top-14 z-30 rounded-lg border border-white/30 bg-black/70 px-3 py-1.5 text-[11px] text-white/95">
      {overlay.text}
    </div>
  );
}

export { InteractionOverlay };
