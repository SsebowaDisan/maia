import type { RefObject } from "react";
import { ApprovalGateCard } from "./ApprovalGateCard";
import { DesktopViewer } from "./DesktopViewer";
import { FullscreenViewerOverlay } from "./FullscreenViewerOverlay";
import { PhaseTimeline } from "./PhaseTimeline";
import { ReplayTimeline } from "./ReplayTimeline";
import type { AgentActivityEvent } from "../../types";

type ActivityPanelBodyProps = {
  sharedViewerProps: Omit<React.ComponentProps<typeof DesktopViewer>, "onToggleTheaterView" | "onToggleFocusMode" | "onOpenFullscreen">;
  phaseTimeline: Array<{
    key: string;
    label: string;
    state: "active" | "completed" | "pending" | string;
    latestEventTitle?: string;
  }>;
  streaming: boolean;
  visibleEvents: AgentActivityEvent[];
  orderedEvents: AgentActivityEvent[];
  safeCursor: number;
  progressPercent: number;
  activeEvent: AgentActivityEvent | null;
  sceneText: string;
  onSelectEvent: (event: AgentActivityEvent, index: number) => void;
  listRef: RefObject<HTMLDivElement | null>;
  setCursor: React.Dispatch<React.SetStateAction<number>>;
  setIsPlaying: React.Dispatch<React.SetStateAction<boolean>>;
  isFocusMode: boolean;
  setIsFocusMode: React.Dispatch<React.SetStateAction<boolean>>;
  isTheaterView: boolean;
  setIsTheaterView: React.Dispatch<React.SetStateAction<boolean>>;
  isFullscreenViewer: boolean;
  setIsFullscreenViewer: React.Dispatch<React.SetStateAction<boolean>>;
  approvalEvent: AgentActivityEvent | null;
  approvalDismissed: string;
  setApprovalDismissed: React.Dispatch<React.SetStateAction<string>>;
};

function ActivityPanelBody({
  sharedViewerProps,
  phaseTimeline,
  streaming,
  visibleEvents,
  orderedEvents,
  safeCursor,
  progressPercent,
  activeEvent,
  sceneText,
  onSelectEvent,
  listRef,
  setCursor,
  setIsPlaying,
  isFocusMode,
  setIsFocusMode,
  isTheaterView,
  setIsTheaterView,
  isFullscreenViewer,
  setIsFullscreenViewer,
  approvalEvent,
  approvalDismissed,
  setApprovalDismissed,
}: ActivityPanelBodyProps) {
  return (
    <>
      <DesktopViewer
        {...sharedViewerProps}
        onToggleTheaterView={() => setIsTheaterView((prev) => !prev)}
        onToggleFocusMode={() => setIsFocusMode((prev) => !prev)}
        onOpenFullscreen={() => {
          setIsFullscreenViewer(true);
          setIsFocusMode(true);
        }}
      />

      <PhaseTimeline phases={phaseTimeline} streaming={streaming} eventCount={visibleEvents.length} />

      <ReplayTimeline
        streaming={streaming}
        safeCursor={safeCursor}
        totalEvents={orderedEvents.length}
        progressPercent={progressPercent}
        setCursor={setCursor}
        setIsPlaying={setIsPlaying}
        activeEvent={activeEvent}
        visibleEvents={visibleEvents}
        onSelectEvent={onSelectEvent}
        listRef={listRef}
      />

      <FullscreenViewerOverlay
        isOpen={isFullscreenViewer}
        isFocusMode={isFocusMode}
        onToggleFocusMode={() => setIsFocusMode((prev) => !prev)}
        onClose={() => setIsFullscreenViewer(false)}
        desktopViewer={
          <DesktopViewer
            {...sharedViewerProps}
            fullscreen
            onToggleTheaterView={() => setIsTheaterView((prev) => !prev)}
            onToggleFocusMode={() => setIsFocusMode((prev) => !prev)}
            onOpenFullscreen={() => setIsFullscreenViewer(true)}
          />
        }
        visibleEvents={visibleEvents}
        activeEvent={activeEvent}
        sceneText={sceneText}
        onSelectEvent={onSelectEvent}
      />

      {(() => {
        if (!streaming || !approvalEvent) return null;
        const eventId = String(approvalEvent.event_id || "");
        if (approvalDismissed === eventId) return null;
        const payload = ((approvalEvent.data ?? approvalEvent.metadata) ?? {}) as Record<string, unknown>;
        const rawGate = String(payload.gate_color ?? payload.trust_gate_color ?? "amber").trim();
        const gateColor: "amber" | "red" = rawGate === "red" ? "red" : "amber";
        const trustScore = Number(payload.trust_score ?? 0.5);
        const reason = String(payload.reason ?? payload.message ?? "").trim();
        return (
          <ApprovalGateCard
            trustScore={trustScore}
            gateColor={gateColor}
            reason={reason}
            onApprove={() => setApprovalDismissed(eventId)}
            onCancel={() => setApprovalDismissed(eventId)}
          />
        );
      })()}
    </>
  );
}

export { ActivityPanelBody };
