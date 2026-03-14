import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type UIEvent as ReactUIEvent,
} from "react";
import { approveAgentRunGate, rejectAgentRunGate } from "../../../api/client";
import { ClarificationResumeModal } from "./ClarificationResumeModal";
import { CanvasPanel } from "../canvas/CanvasPanel";
import { useCanvasStore } from "../../stores/canvasStore";
import type { ChatTurn } from "../../types";
import { ComposerPanel } from "./ComposerPanel";
import { EmptyState } from "./EmptyState";
import { GateApprovalCard } from "./GateApprovalCard";
import {
  CITATION_ANCHOR_SELECTOR,
  resolveCitationAnchorInteractionPolicy,
  resolveCitationFocusFromAnchor,
  shouldOpenCitationSourceUrlForPointerEvent,
} from "./citationFocus";
import type { ChatMainProps } from "./types";
import { TurnsPanel } from "./TurnsPanel";
import { useChatMainInteractions } from "./useChatMainInteractions";

const COMPOSER_REVEAL_DISTANCE_PX = 260;
const COMPOSER_HIDE_DISTANCE_PX = 320;
const COMPOSER_ACTIVITY_REVEAL_DISTANCE_PX = 360;
const COMPOSER_ACTIVITY_HIDE_DISTANCE_PX = 430;
const COMPOSER_SCROLL_SETTLE_MS = 420;

function ChatMain({
  chatTurns,
  selectedTurnIndex,
  onSelectTurn,
  onUpdateUserTurn,
  onSendMessage,
  onUploadFiles,
  onCreateFileIngestionJob,
  availableDocuments = [],
  availableGroups = [],
  availableProjects = [],
  isSending,
  citationMode,
  mindmapEnabled,
  mindmapMaxDepth,
  mindmapIncludeReasoning,
  mindmapMapType,
  onCitationClick,
  citationFocus = null,
  agentMode,
  onAgentModeChange,
  accessMode,
  onAccessModeChange,
  activityEvents,
  isActivityStreaming,
  clarificationPrompt,
  onDismissClarificationPrompt,
  onSubmitClarificationPrompt,
}: ChatMainProps) {
  const composerContainerRef = useRef<HTMLDivElement | null>(null);
  const contentScrollRef = useRef<HTMLDivElement | null>(null);
  const scrollHideTimeoutRef = useRef<number | null>(null);
  const [showComposerDuringActivity, setShowComposerDuringActivity] = useState(true);
  const [composerDockedByScroll, setComposerDockedByScroll] = useState(false);
  const [scrollSettling, setScrollSettling] = useState(false);
  const maiaActive = isActivityStreaming || isSending;
  const upsertDocuments = useCanvasStore((state) => state.upsertDocuments);
  const pendingGate = useMemo(() => {
    const orderedEvents = Array.isArray(activityEvents) ? [...activityEvents] : [];
    if (!orderedEvents.length) {
      return null;
    }
    let latestPending:
      | {
          runId: string;
          gateId: string;
          toolId: string;
          paramsPreview: string;
          costEstimateUsd: number | null;
        }
      | null = null;
    const resolvedGates = new Set<string>();
    for (let index = orderedEvents.length - 1; index >= 0; index -= 1) {
      const event = orderedEvents[index];
      const eventType = String(event?.event_type || event?.type || "").trim().toLowerCase();
      const data = (event?.data || {}) as Record<string, unknown>;
      const metadata = (event?.metadata || {}) as Record<string, unknown>;
      const gateId = String(data.gate_id || metadata.gate_id || "").trim();
      if (!gateId) {
        continue;
      }
      if (eventType === "gate_approved" || eventType === "gate_rejected" || eventType === "gate_resolved") {
        resolvedGates.add(gateId);
        continue;
      }
      if (eventType !== "gate_pending" || resolvedGates.has(gateId)) {
        continue;
      }
      const runId = String(event?.run_id || data.run_id || metadata.run_id || "").trim();
      const toolId = String(data.tool_id || metadata.tool_id || event.title || "tool").trim();
      const paramsPreview = String(
        data.params_preview || metadata.params_preview || event.detail || "Review tool call parameters before continuing.",
      ).trim();
      const numericCost = Number(data.cost_estimate ?? metadata.cost_estimate ?? Number.NaN);
      latestPending = {
        runId: runId || "active-run",
        gateId,
        toolId: toolId || "tool",
        paramsPreview: paramsPreview || "Review tool call parameters before continuing.",
        costEstimateUsd: Number.isFinite(numericCost) ? numericCost : null,
      };
      break;
    }
    return latestPending;
  }, [activityEvents]);

  const interactions = useChatMainInteractions({
    accessMode,
    activityEvents,
    agentMode,
    chatTurns,
    citationMode,
    mindmapEnabled,
    mindmapMaxDepth,
    mindmapIncludeReasoning,
    mindmapMapType,
    isSending,
    onAccessModeChange,
    onAgentModeChange,
    onSendMessage,
    onUpdateUserTurn,
    onUploadFiles,
    onCreateFileIngestionJob,
    availableDocuments,
    availableGroups,
    availableProjects,
  });

  const handleTurnClick = (
    event: ReactMouseEvent<HTMLDivElement>,
    turn: ChatTurn,
    index: number,
  ) => {
    const target = event.target as HTMLElement;
    const citationAnchor = target.closest(CITATION_ANCHOR_SELECTOR) as HTMLAnchorElement | null;
    if (citationAnchor) {
      const interactionPolicy = resolveCitationAnchorInteractionPolicy(citationAnchor);
      if (
        shouldOpenCitationSourceUrlForPointerEvent(event.nativeEvent, interactionPolicy) ||
        interactionPolicy.openDirectOnPrimaryClick
      ) {
        if (!interactionPolicy.directOpenUrl) {
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        window.open(interactionPolicy.directOpenUrl, "_blank", "noopener,noreferrer");
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      onSelectTurn(index);
      const resolved = resolveCitationFocusFromAnchor({ turn, citationAnchor });
      onCitationClick(resolved.focus);
      return;
    }
    onSelectTurn(index);
  };

  const handleTurnAuxClick = (
    event: ReactMouseEvent<HTMLDivElement>,
    _turn: ChatTurn,
    _index: number,
  ) => {
    const target = event.target as HTMLElement;
    const citationAnchor = target.closest(CITATION_ANCHOR_SELECTOR) as HTMLAnchorElement | null;
    if (!citationAnchor) {
      return;
    }
    const interactionPolicy = resolveCitationAnchorInteractionPolicy(citationAnchor);
    if (!interactionPolicy.directOpenUrl || event.button !== 1) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    window.open(interactionPolicy.directOpenUrl, "_blank", "noopener,noreferrer");
  };

  useEffect(() => {
    if (!maiaActive) {
      if (!composerDockedByScroll) {
        setShowComposerDuringActivity(true);
      }
      return;
    }
    setShowComposerDuringActivity(false);
    const activeElement = document.activeElement;
    if (activeElement instanceof HTMLElement && composerContainerRef.current?.contains(activeElement)) {
      activeElement.blur();
    }
  }, [composerDockedByScroll, maiaActive]);

  useEffect(() => {
    const documents = chatTurns.flatMap((turn) => turn.documents || []);
    if (documents.length > 0) {
      upsertDocuments(documents);
    }
  }, [chatTurns, upsertDocuments]);

  useEffect(
    () => () => {
      if (scrollHideTimeoutRef.current !== null) {
        window.clearTimeout(scrollHideTimeoutRef.current);
      }
    },
    [],
  );

  const scrollLatestTurnToTop = () => {
    const element = contentScrollRef.current;
    if (!element) {
      return;
    }
    const latestTurnIndex = chatTurns.length - 1;
    const latestTurnNode = element.querySelector<HTMLElement>(
      `[data-turn-index="${String(latestTurnIndex)}"]`,
    );
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false);
    const behavior: ScrollBehavior = prefersReducedMotion ? "auto" : "smooth";
    if (latestTurnNode) {
      latestTurnNode.scrollIntoView({
        behavior,
        block: "start",
        inline: "nearest",
      });
      return;
    }
    element.scrollTo({ top: element.scrollHeight, behavior });
  };

  const handleMainMouseMove = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (!maiaActive && !composerDockedByScroll) {
      return;
    }
    if (scrollSettling && !maiaActive) {
      return;
    }
    const bounds = event.currentTarget.getBoundingClientRect();
    const distanceToBottom = bounds.bottom - event.clientY;
    const revealDistance = maiaActive ? COMPOSER_ACTIVITY_REVEAL_DISTANCE_PX : COMPOSER_REVEAL_DISTANCE_PX;
    const hideDistance = maiaActive ? COMPOSER_ACTIVITY_HIDE_DISTANCE_PX : COMPOSER_HIDE_DISTANCE_PX;
    const nextVisible = showComposerDuringActivity
      ? distanceToBottom <= hideDistance
      : distanceToBottom <= revealDistance;
    setShowComposerDuringActivity(nextVisible);
  };

  const handleMainMouseLeave = () => {
    if (!maiaActive && !composerDockedByScroll) {
      return;
    }
    setShowComposerDuringActivity(false);
  };

  const handleContentScroll = (event: ReactUIEvent<HTMLDivElement>) => {
    void event.currentTarget;
    setComposerDockedByScroll(true);
    setScrollSettling(true);
    setShowComposerDuringActivity(false);
    if (scrollHideTimeoutRef.current !== null) {
      window.clearTimeout(scrollHideTimeoutRef.current);
    }
    scrollHideTimeoutRef.current = window.setTimeout(() => {
      setScrollSettling(false);
      scrollHideTimeoutRef.current = null;
    }, COMPOSER_SCROLL_SETTLE_MS);
  };

  useEffect(() => {
    if (!isSending) {
      return;
    }
    const rafId = window.requestAnimationFrame(() => {
      scrollLatestTurnToTop();
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [chatTurns.length, isSending, isActivityStreaming]);

  const composerVisible = maiaActive || composerDockedByScroll
    ? showComposerDuringActivity && !scrollSettling
    : true;

  return (
    <div
      className="flex-1 min-h-0 min-w-0 flex flex-col overflow-hidden rounded-[28px] border border-black/[0.06] bg-[#f6f6f7] shadow-[0_14px_40px_rgba(15,23,42,0.06)]"
      onMouseMove={handleMainMouseMove}
      onMouseLeave={handleMainMouseLeave}
    >
      <div className="border-b border-black/[0.06] px-5 py-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">Dialogue</p>
          <h3 className="mt-1 text-[20px] font-semibold tracking-[-0.02em] text-[#17171b]">Conversation</h3>
        </div>
      </div>
      <div className="relative min-h-0 flex-1">
        <div
          ref={contentScrollRef}
          className="h-full overflow-y-auto px-6 pb-10 pt-6"
          onScroll={handleContentScroll}
        >
          {pendingGate ? (
            <div className="mb-4">
              <GateApprovalCard
                runId={pendingGate.runId}
                gateId={pendingGate.gateId}
                toolId={pendingGate.toolId}
                paramsPreview={pendingGate.paramsPreview}
                costEstimateUsd={pendingGate.costEstimateUsd}
                onApprove={async (runId, gateId) => {
                  await approveAgentRunGate(runId, gateId);
                }}
                onReject={async (runId, gateId) => {
                  await rejectAgentRunGate(runId, gateId);
                }}
              />
            </div>
          ) : null}
          {chatTurns.length === 0 ? (
            <EmptyState />
          ) : (
            <TurnsPanel
              activityEvents={activityEvents}
              beginInlineEdit={interactions.beginInlineEdit}
              cancelInlineEdit={interactions.cancelInlineEdit}
              chatTurns={chatTurns}
              copyPlainText={interactions.copyPlainText}
              editingText={interactions.editingText}
              editingTurnIndex={interactions.editingTurnIndex}
              isActivityStreaming={isActivityStreaming}
              isSending={isSending}
              onTurnClick={handleTurnClick}
              onTurnAuxClick={handleTurnAuxClick}
              quoteAssistant={interactions.quoteAssistant}
              retryTurn={interactions.retryTurn}
              saveInlineEdit={interactions.saveInlineEdit}
              selectedTurnIndex={selectedTurnIndex}
              setEditingText={interactions.setEditingText}
              citationFocus={citationFocus}
            />
          )}
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-[#f6f6f7] via-[#f6f6f7]/92 to-transparent" />
      </div>

      <div
        ref={composerContainerRef}
        className={`overflow-hidden bg-[linear-gradient(180deg,rgba(246,246,247,0.08)_0%,rgba(246,246,247,0.86)_18%,#f6f6f7_100%)] px-3 pb-3 pt-2 transition-[max-height,opacity,transform] duration-220 ease-out ${
          composerVisible
            ? "max-h-[440px] translate-y-0 opacity-100"
            : "pointer-events-none max-h-0 translate-y-3 opacity-0"
        }`}
      >
        <ComposerPanel
          accessMode={accessMode}
          agentControlsVisible={interactions.agentControlsVisible}
          agentMode={agentMode}
          composerMode={interactions.composerMode}
          attachments={interactions.attachments}
          clearAttachments={interactions.clearAttachments}
          removeAttachment={interactions.removeAttachment}
          enableAskMode={interactions.enableAskMode}
          enableAgentMode={interactions.enableAgentMode}
          enableWebSearch={interactions.enableWebSearch}
          enableDeepResearch={interactions.enableDeepResearch}
          fileInputRef={interactions.fileInputRef}
          isSending={isSending}
          isUploading={interactions.isUploading}
          latestHighlightSnippets={interactions.latestHighlightSnippets}
          message={interactions.message}
          messageActionStatus={interactions.messageActionStatus}
          onAccessModeChange={onAccessModeChange}
          onFileChange={interactions.onFileChange}
          documentOptions={availableDocuments}
          groupOptions={availableGroups}
          projectOptions={availableProjects}
          onAttachDocument={interactions.attachDocumentById}
          onAttachGroup={interactions.attachGroupById}
          onAttachProject={interactions.attachProjectById}
          pasteHighlightsToComposer={interactions.pasteHighlightsToComposer}
          setMessage={interactions.setMessage}
          submit={interactions.submit}
        />
      </div>

      {clarificationPrompt ? (
        <ClarificationResumeModal
          prompt={clarificationPrompt}
          onDismiss={onDismissClarificationPrompt}
          onSubmit={onSubmitClarificationPrompt}
        />
      ) : null}

      <CanvasPanel />
    </div>
  );
}

export { ChatMain };
