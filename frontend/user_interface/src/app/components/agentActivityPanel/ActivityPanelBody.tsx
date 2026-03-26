import { useState, type RefObject } from "react";
import { toast } from "sonner";
import {
  AssemblyProgressPanel,
  BrainReviewPanel,
  FullscreenViewerOverlay,
  PhaseTimeline,
  ResearchTodoList,
  type FullscreenTimelineItem,
} from "@maia/theatre";

import { approveAgentRunGate, rejectAgentRunGate } from "../../../api/client";
import { readEventPayload } from "../../utils/eventPayload";
import { resolvePreferredRunId } from "../../utils/runIdSelection";
import { ApprovalGateCard } from "./ApprovalGateCard";
import { AgentHandoffRelay } from "./AgentHandoffRelay";
import { DesktopViewer } from "./DesktopViewer";
import { ReplayControls } from "./ReplayControls";
import { visibleTimelineEvents } from "./replayModePolicy";
import { ReplayTimeline } from "./ReplayTimeline";
import { TeamConversationTab } from "./TeamConversationTab";
import type { TheatreStage } from "./deriveTheatreStage";
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
  plannedRoadmapSteps: Array<{ toolId: string; title: string; whyThisStep: string }>;
  roadmapActiveIndex: number;
  theatreStage: TheatreStage;
  needsHumanReview: boolean;
  humanReviewNotes?: string | null;
  activityRunId: string;
  onReplayStep: (event: Record<string, unknown>, index: number, total: number) => void;
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
  plannedRoadmapSteps,
  roadmapActiveIndex,
  theatreStage,
  needsHumanReview,
  humanReviewNotes,
  activityRunId,
  onReplayStep,
}: ActivityPanelBodyProps) {
  const [panelTab, setPanelTab] = useState<"timeline" | "conversation">("timeline");
  const conversationRunId = resolvePreferredRunId(activityRunId, orderedEvents);
  const timelineItems: FullscreenTimelineItem[] = visibleTimelineEvents(visibleEvents).map((event) => {
    const index = visibleEvents.findIndex((candidate) => candidate.event_id === event.event_id);
    return {
      id: String(event.event_id || index),
      title: String(event.title || "Untitled event"),
      detail: String(event.detail || ""),
      onSelect: () => onSelectEvent(event, index),
    };
  });
  const activeEventType = String(activeEvent?.event_type || "").trim().toLowerCase();
  const executionStarted = orderedEvents.some(
    (event) => String(event.event_type || "").trim().toLowerCase() === "execution_starting",
  );
  const isPreExecutionPlan =
    !executionStarted &&
    (
      plannedRoadmapSteps.length > 0 ||
      activeEventType.startsWith("assembly_") ||
      activeEventType === "planning_started" ||
      activeEventType === "workflow_saved" ||
      activeEventType === "assembly_connector_needed" ||
      activeEventType === "connector_needed"
    );
  const showPlanningSecondaryPanels = !isPreExecutionPlan;
  const showReplayRail = !isPreExecutionPlan;

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

      {showPlanningSecondaryPanels ? (
        <PhaseTimeline phases={phaseTimeline} streaming={streaming} eventCount={visibleEvents.length} />
      ) : null}

      {showPlanningSecondaryPanels ? (
        <ResearchTodoList
          visibleEvents={visibleEvents}
          plannedRoadmapSteps={plannedRoadmapSteps}
          roadmapActiveIndex={roadmapActiveIndex}
          streaming={streaming}
        />
      ) : null}

      {showPlanningSecondaryPanels ? <AssemblyProgressPanel events={orderedEvents} activeEvent={activeEvent} /> : null}

      {showPlanningSecondaryPanels ? <BrainReviewPanel events={orderedEvents} /> : null}

      {(theatreStage === "review" || theatreStage === "confirm") ? (
        <div className="mt-3 rounded-2xl border border-[#e3e5e8] bg-white px-4 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#7a7a83]">
            {theatreStage === "confirm" ? "Confirmation Required" : "Review Required"}
          </p>
          <p className="mt-1 text-[13px] text-[#1f2937]">
            {theatreStage === "confirm"
              ? "An irreversible action is pending. Confirm before execution continues."
              : "Review generated output before final delivery."}
          </p>
          {needsHumanReview || humanReviewNotes ? (
            <p className="mt-1 text-[12px] text-[#6b7280]">
              {String(humanReviewNotes || "Human review requested for this run.")}
            </p>
          ) : null}
        </div>
      ) : null}

      <AgentHandoffRelay event={activeEvent} />

      {showReplayRail ? (
        <div className="mt-3 inline-flex rounded-full border border-[#e4e7ec] bg-white p-1">
          <button
            type="button"
            onClick={() => setPanelTab("timeline")}
            className={`rounded-full px-3 py-1 text-[11px] font-semibold transition ${
              panelTab === "timeline"
                ? "bg-[#111827] text-white"
                : "text-[#475467] hover:bg-[#f8fafc]"
            }`}
          >
            Timeline
          </button>
          <button
            type="button"
            onClick={() => setPanelTab("conversation")}
            className={`rounded-full px-3 py-1 text-[11px] font-semibold transition ${
              panelTab === "conversation"
                ? "bg-[#111827] text-white"
                : "text-[#475467] hover:bg-[#f8fafc]"
            }`}
          >
            Team conversation
          </button>
        </div>
      ) : null}

      {showReplayRail && panelTab === "timeline" ? (
        <>
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

          {!streaming && activityRunId ? (
            <ReplayControls
              runId={activityRunId}
              onStep={(event, index, total) =>
                onReplayStep(event as Record<string, unknown>, index, total)}
            />
          ) : null}
        </>
      ) : null}

      {panelTab === "conversation" ? (
        <TeamConversationTab runId={conversationRunId} events={orderedEvents} />
      ) : null}

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
        activeTitle={String(activeEvent?.title || "")}
        activeDetail={String(sceneText || activeEvent?.detail || "")}
        timelineItems={timelineItems}
      />

      {(() => {
        if (!streaming || !approvalEvent) return null;
        const eventId = String(approvalEvent.event_id || "");
        if (approvalDismissed === eventId) return null;
        const payload = readEventPayload(approvalEvent);
        const rawGate = String(payload.gate_color ?? payload.trust_gate_color ?? "amber").trim();
        const gateColor: "amber" | "red" = rawGate === "red" ? "red" : "amber";
        const trustScore = Number(payload.trust_score ?? 0.5);
        const reason = String(payload.reason ?? payload.message ?? "").trim();
        const runId = String(
          approvalEvent.run_id || payload.run_id || payload.active_run_id || payload.session_run_id || "",
        ).trim();
        const gateId = String(payload.gate_id || payload.pending_gate_id || payload.id || eventId).trim();
        const actionLabel = String(
          payload.action_label || payload.tool_label || payload.tool_id || approvalEvent.title || "Pending action",
        ).trim();
        const paramsPreview = String(
          payload.params_preview || payload.preview_text || payload.detail || approvalEvent.detail || "",
        ).trim();
        const preview = payload.preview && typeof payload.preview === "object"
          ? (payload.preview as Record<string, unknown>)
          : null;

        return (
          <ApprovalGateCard
            trustScore={trustScore}
            gateColor={gateColor}
            reason={reason}
            actionLabel={actionLabel}
            paramsPreview={paramsPreview}
            preview={preview}
            onApprove={async (editedPreviewText) => {
              if (runId && gateId) {
                await approveAgentRunGate(
                  runId,
                  gateId,
                  editedPreviewText
                    ? { edited_preview: String(editedPreviewText || "").trim() }
                    : undefined,
                );
                toast.success("Approval submitted.");
              }
              setApprovalDismissed(eventId);
            }}
            onReject={async () => {
              if (runId && gateId) {
                await rejectAgentRunGate(runId, gateId);
                toast.success("Action rejected.");
              }
              setApprovalDismissed(eventId);
            }}
            onCancel={() => setApprovalDismissed(eventId)}
          />
        );
      })()}
    </>
  );
}

export { ActivityPanelBody };
