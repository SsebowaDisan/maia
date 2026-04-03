import {
  useCallback,
  useEffect,
  useMemo,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { ArrowDown } from "lucide-react";
import { approveAgentRunGate, rejectAgentRunGate } from "../../../api/client";
import { ClarificationResumeModal } from "./ClarificationResumeModal";
import { useCanvasStore } from "../../stores/canvasStore";
import { useAgentRunStore } from "../../stores/agentRunStore";
import {
  EVT_INTERACTION_SUGGESTION_SEND,
  type InteractionSuggestionSendDetail,
} from "../../constants/uiEvents";
import type { ChatTurn } from "../../types";
import { ComposerPanel, type WorkflowCommandSelection } from "./ComposerPanel";
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
import { useCitationPrefetch } from "./chatMainSections/useCitationPrefetch";
import { usePendingGate } from "./chatMainSections/usePendingGate";
import { useScrollControls } from "./chatMainSections/useScrollControls";

function ChatMain({
  chatTurns,
  selectedTurnIndex,
  onSelectTurn,
  onUpdateUserTurn,
  onSendMessage,
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
  const upsertDocuments = useCanvasStore((state) => state.upsertDocuments);
  const hydrateRunSnapshot = useAgentRunStore((state) => state.hydrateFromActivityEvent);
  const clearRunSnapshot = useAgentRunStore((state) => state.clear);

  const activeRunId = useMemo(() => {
    for (let index = activityEvents.length - 1; index >= 0; index -= 1) {
      const runId = String(activityEvents[index]?.run_id || "").trim();
      if (runId) {
        return runId;
      }
    }
    return "";
  }, [activityEvents]);

  const pendingGate = usePendingGate({
    activeRunId,
    activityEvents: activityEvents as Array<Record<string, unknown>>,
  });

  const scroll = useScrollControls({
    chatTurnCount: chatTurns.length,
    selectedTurnIndex,
    isSending,
    isActivityStreaming,
  });

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
    onCreateFileIngestionJob,
    availableDocuments,
    availableGroups,
    availableProjects,
  });

  useEffect(() => {
    const handleSuggestionSend = (event: Event) => {
      const customEvent = event as CustomEvent<InteractionSuggestionSendDetail>;
      const prompt = String(customEvent.detail?.prompt || "").trim();
      if (!prompt) {
        return;
      }
      void interactions.sendSuggestionPrompt(prompt);
    };
    window.addEventListener(
      EVT_INTERACTION_SUGGESTION_SEND,
      handleSuggestionSend as EventListener,
    );
    return () => {
      window.removeEventListener(
        EVT_INTERACTION_SUGGESTION_SEND,
        handleSuggestionSend as EventListener,
      );
    };
  }, [interactions.sendSuggestionPrompt]);

  const handleTurnClick = (
    event: ReactMouseEvent<HTMLDivElement>,
    turn: ChatTurn,
    index: number,
  ) => {
    const target = event.target as HTMLElement;
    const citationAnchor = target.closest(CITATION_ANCHOR_SELECTOR) as HTMLAnchorElement | null;
    if (citationAnchor) {
      const interactionPolicy = resolveCitationAnchorInteractionPolicy(citationAnchor);
      if (shouldOpenCitationSourceUrlForPointerEvent(event.nativeEvent, interactionPolicy)) {
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
    const documents = chatTurns.flatMap((turn) => turn.documents || []);
    if (documents.length > 0) {
      upsertDocuments(documents);
    }
  }, [chatTurns, upsertDocuments]);

  useEffect(() => {
    if (!Array.isArray(activityEvents) || activityEvents.length === 0) {
      clearRunSnapshot();
      return;
    }
    const latestEvent = activityEvents[activityEvents.length - 1];
    hydrateRunSnapshot((latestEvent || {}) as Record<string, unknown>);
  }, [activityEvents, clearRunSnapshot, hydrateRunSnapshot]);

  useCitationPrefetch({
    contentScrollRef: scroll.contentScrollRef,
    chatTurns,
  });

  const hasActiveRun = isSending || isActivityStreaming;
  const isBrainActive = interactions.composerMode === "brain" && hasActiveRun;
  const composerVisible = hasActiveRun
    ? scroll.composerHovering
    : !scroll.composerCollapsed || scroll.composerHovering || scroll.composerFocused;

  const handleSelectWorkflow = useCallback(
    (workflow: WorkflowCommandSelection) => {
      const steps = Array.isArray(workflow.definition?.steps) ? workflow.definition.steps : [];
      if (steps.length === 0) {
        return;
      }
      interactions.setActiveWorkflow({
        workflow_id: workflow.workflow_id,
        name: String(workflow.name || "Untitled workflow").trim(),
        description: String(workflow.description || "").trim(),
        steps: steps.map((s) => ({
          step_id: String(s.step_id || ""),
          agent_id: String(s.agent_id || ""),
          description: String(s.description || ""),
        })),
      });
      interactions.showActionStatus(`Workflow "${workflow.name}" selected. Type your input.`);
    },
    [interactions],
  );

  return (
    <div className="relative h-full flex-1 min-h-0 min-w-0 flex flex-col overflow-hidden rounded-[28px] border border-black/[0.06] bg-[#f6f6f7] shadow-[0_14px_40px_rgba(15,23,42,0.06)]">
      <div className="shrink-0 border-b border-black/[0.06] px-5 py-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">Dialogue</p>
          <h3 className="mt-1 text-[20px] font-semibold tracking-[-0.02em] text-[#17171b]">Conversation</h3>
        </div>
      </div>
      <div className="relative min-h-0 flex-1 grow">
        <div
          ref={scroll.contentScrollRef}
          className="absolute inset-0 overflow-y-auto overscroll-none px-6 pb-3 pt-6"
          onScroll={scroll.handleContentScroll}
        >
          {pendingGate ? (
            <div className="mb-4">
              <GateApprovalCard
                runId={pendingGate.runId}
                gateId={pendingGate.gateId}
                toolId={pendingGate.toolId}
                paramsPreview={pendingGate.paramsPreview}
                actionLabel={pendingGate.actionLabel}
                preview={pendingGate.preview}
                costEstimateUsd={pendingGate.costEstimateUsd}
                onApprove={async (runId, gateId, editedParams) => {
                  await approveAgentRunGate(runId, gateId, editedParams);
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
              autoFollowLatest={!scroll.showScrollToLatest}
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
              onCitationClick={onCitationClick}
            />
          )}
        </div>
        {scroll.showScrollToLatest && (scroll.scrollIconSettling || scroll.scrollIconHovering) ? (
          <button
            type="button"
            tabIndex={-1}
            onMouseDown={(e) => e.preventDefault()}
            onClick={scroll.scrollToLatestMessage}
            onMouseEnter={() => scroll.setScrollIconHovering(true)}
            onMouseLeave={() => scroll.setScrollIconHovering(false)}
            className="absolute inset-y-0 right-4 z-20 my-auto inline-flex h-10 w-10 items-center justify-center rounded-full border border-black/[0.08] bg-white/96 text-[#1d1d1f] shadow-[0_10px_24px_-18px_rgba(0,0,0,0.55)] transition hover:bg-white"
            aria-label="Scroll to latest message"
            title="Scroll to latest message"
          >
            <ArrowDown className="h-4 w-4 stroke-[2.4]" />
          </button>
        ) : null}
      </div>
      {/* ── Composer footer ── */}
      <div
        className={`relative z-20 shrink-0 ${hasActiveRun ? "" : "mt-auto"}`}
        onMouseEnter={() => {
          scroll.setComposerHovering(true);
        }}
        onMouseLeave={() => {
          scroll.setComposerHovering(false);
        }}
      >
        {!composerVisible && isBrainActive ? (
          <div className="flex justify-center py-1.5">
            <div className="h-1 w-10 rounded-full bg-black/[0.08]" />
          </div>
        ) : null}
        {composerVisible && !hasActiveRun ? (
          <div className={`border-t border-black/[0.06] bg-[#f6f6f7] px-3 pb-3 pt-2 ${isBrainActive ? "transition-opacity duration-200" : ""}`}>
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
              enableBrainMode={interactions.enableBrainMode}
              enableRagMode={interactions.enableRagMode}
              enableWebSearch={interactions.enableWebSearch}
              enableDeepResearch={interactions.enableDeepResearch}
              activeAgent={interactions.activeAgent}
              onAgentSelect={interactions.onAgentSelect}
              onSelectWorkflow={handleSelectWorkflow}
              activeWorkflow={interactions.activeWorkflow}
              onClearWorkflow={() => interactions.setActiveWorkflow(null)}
              fileInputRef={interactions.fileInputRef}
              isSending={isSending}
              isUploading={interactions.isUploading}
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
              setMessage={interactions.setMessage}
              submit={interactions.submit}
              onFocusWithinChange={(focused) => {
                scroll.setComposerFocused(focused);
                if (focused) {
                  scroll.setComposerCollapsed(false);
                }
              }}
            />
          </div>
        ) : hasActiveRun ? (
          <div className="border-t border-black/[0.06] bg-[#f6f6f7] px-3 py-2">
            <div className="mx-auto h-1.5 w-16 rounded-full bg-black/[0.12]" />
          </div>
        ) : (
          <div className="border-t border-black/[0.06] bg-[#f6f6f7] px-3 pb-[42px] pt-3">
            <div className="mx-auto h-1.5 w-16 rounded-full bg-black/[0.12]" />
          </div>
        )}
        {/* Overlay composer on hover during active run — inside the hover
            wrapper so mouseLeave from the bar doesn't flicker the overlay */}
        {composerVisible && hasActiveRun ? (
          <div className="absolute inset-x-0 bottom-0 z-30 rounded-b-[28px] border-t border-black/[0.06] bg-[#f6f6f7]/95 px-3 pb-3 pt-2 shadow-[0_-8px_24px_rgba(0,0,0,0.06)] backdrop-blur-sm">
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
              enableBrainMode={interactions.enableBrainMode}
              enableRagMode={interactions.enableRagMode}
              enableWebSearch={interactions.enableWebSearch}
              enableDeepResearch={interactions.enableDeepResearch}
              activeAgent={interactions.activeAgent}
              onAgentSelect={interactions.onAgentSelect}
              onSelectWorkflow={handleSelectWorkflow}
              activeWorkflow={interactions.activeWorkflow}
              onClearWorkflow={() => interactions.setActiveWorkflow(null)}
              fileInputRef={interactions.fileInputRef}
              isSending={isSending}
              isUploading={interactions.isUploading}
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
              setMessage={interactions.setMessage}
              submit={interactions.submit}
              onFocusWithinChange={(focused) => {
                scroll.setComposerFocused(focused);
              }}
            />
          </div>
        ) : null}
      </div>

      {clarificationPrompt ? (
        <ClarificationResumeModal
          prompt={clarificationPrompt}
          onDismiss={onDismissClarificationPrompt}
          onSubmit={onSubmitClarificationPrompt}
        />
      ) : null}
    </div>
  );
}

export { ChatMain };
