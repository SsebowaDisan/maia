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
      <div className="pointer-events-none absolute inset-x-6 top-14 z-30 rounded-xl border border-[#ff9b6a]/70 bg-[#29160f]/85 px-3 py-2 text-[11px] text-[#ffd8c2] shadow-[0_10px_24px_-18px_rgba(0,0,0,0.75)]">
        <p className="font-semibold uppercase tracking-[0.07em]">{overlay.text}</p>
        <p className="mt-0.5 line-clamp-2 text-[#ffe6d7]">{overlay.detail || "Complete verification, then continue."}</p>
      </div>
    );
  }
  if (overlay.variant === "center-pill") {
    return (
      <div
        className={`pointer-events-none absolute left-1/2 top-14 z-30 -translate-x-1/2 rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] ${
          overlay.pulse
            ? "animate-pulse border-[#9ad9ff]/65 bg-[#0f2b3f]/84 text-[#d9f1ff]"
            : "border-[#8fc4ff]/65 bg-[#13263e]/82 text-[#d8edff]"
        }`}
      >
        {overlay.text}
      </div>
    );
  }
  return (
    <div className="pointer-events-none absolute left-4 top-14 z-30 rounded-lg border border-[#a6d4ff]/45 bg-[#142a3e]/84 px-3 py-1.5 text-[11px] text-[#dff0ff]">
      {overlay.text}
    </div>
  );
}

export { InteractionOverlay };
