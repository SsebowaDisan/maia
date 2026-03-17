import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type UIEvent as ReactUIEvent,
} from "react";
import { ArrowDown } from "lucide-react";
import { toast } from "sonner";
import { approveAgentRunGate, listPendingGates, rejectAgentRunGate } from "../../../api/client";
import { ClarificationResumeModal } from "./ClarificationResumeModal";
import { CanvasPanel } from "../canvas/CanvasPanel";
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

const SCROLL_ICON_SETTLE_MS = 1600;
const SCROLL_TO_LATEST_THRESHOLD_PX = 140;

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
  const contentScrollRef = useRef<HTMLDivElement | null>(null);
  const scrollIconHideTimeoutRef = useRef<number | null>(null);
  const programmaticScrollRef = useRef(false);
  const programmaticScrollTimerRef = useRef<number | null>(null);
  const pendingGateToastRef = useRef<string>("");
  const [scrollIconSettling, setScrollIconSettling] = useState(false);
  const [scrollIconHovering, setScrollIconHovering] = useState(false);
  const [showScrollToLatest, setShowScrollToLatest] = useState(false);
  const [composerCollapsed, setComposerCollapsed] = useState(false);
  const [composerHovering, setComposerHovering] = useState(false);
  const [composerFocused, setComposerFocused] = useState(false);
  const [pendingGateFromApi, setPendingGateFromApi] = useState<{
    runId: string;
    gateId: string;
    toolId: string;
    paramsPreview: string;
    costEstimateUsd: number | null;
  } | null>(null);
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
  const pendingGateFromEvents = useMemo(() => {
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
        runId: runId || activeRunId || "",
        gateId,
        toolId: toolId || "tool",
        paramsPreview: paramsPreview || "Review tool call parameters before continuing.",
        costEstimateUsd: Number.isFinite(numericCost) ? numericCost : null,
      };
      break;
    }
    return latestPending;
  }, [activeRunId, activityEvents]);
  const pendingGate = pendingGateFromEvents || pendingGateFromApi;
  useEffect(() => {
    const gateId = String(pendingGate?.gateId || "").trim();
    if (!gateId) {
      return;
    }
    if (pendingGateToastRef.current === gateId) {
      return;
    }
    pendingGateToastRef.current = gateId;
    toast.info(`Approval required for ${pendingGate?.toolId || "tool action"}.`);
  }, [pendingGate?.gateId, pendingGate?.toolId]);
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

  useEffect(
    () => () => {
      if (scrollIconHideTimeoutRef.current !== null) {
        window.clearTimeout(scrollIconHideTimeoutRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    if (!activeRunId || pendingGateFromEvents) {
      setPendingGateFromApi(null);
      return;
    }
    let disposed = false;
    const poll = async () => {
      try {
        const rows = await listPendingGates(activeRunId);
        if (disposed || !Array.isArray(rows) || !rows.length) {
          if (!disposed) {
            setPendingGateFromApi(null);
          }
          return;
        }
        const gate = rows[0];
        const numericCost = Number(gate.cost_estimate ?? Number.NaN);
        setPendingGateFromApi({
          runId: String(gate.run_id || activeRunId),
          gateId: String(gate.gate_id || ""),
          toolId: String(gate.tool_id || "tool"),
          paramsPreview: String(gate.params_preview || "Review tool call parameters before continuing."),
          costEstimateUsd: Number.isFinite(numericCost) ? numericCost : null,
        });
      } catch {
        if (!disposed) {
          setPendingGateFromApi(null);
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => {
      void poll();
    }, 3000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [activeRunId, pendingGateFromEvents]);

  const scrollLatestTurnToTop = useCallback(() => {
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
  }, [chatTurns.length]);

  const refreshScrollToLatestVisibility = useCallback(
    (element?: HTMLDivElement | null) => {
      if (programmaticScrollRef.current) return;
      const container = element || contentScrollRef.current;
      if (!container || chatTurns.length === 0) {
        setShowScrollToLatest(false);
        return;
      }
      const distanceToBottom =
        container.scrollHeight - (container.scrollTop + container.clientHeight);
      setShowScrollToLatest(distanceToBottom > SCROLL_TO_LATEST_THRESHOLD_PX);
    },
    [chatTurns.length],
  );

  const scrollToLatestMessage = useCallback(() => {
    const element = contentScrollRef.current;
    if (!element) {
      return;
    }
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false);

    // Lock out scroll-driven composer/button state updates for the duration of
    // the animation. Without this, the composer expanding mid-scroll changes
    // clientHeight, which changes distanceToBottom, which collapses/expands the
    // composer in a feedback loop that fights the animation.
    programmaticScrollRef.current = true;
    if (programmaticScrollTimerRef.current !== null) {
      window.clearTimeout(programmaticScrollTimerRef.current);
    }
    programmaticScrollTimerRef.current = window.setTimeout(() => {
      programmaticScrollRef.current = false;
      programmaticScrollTimerRef.current = null;
      setComposerCollapsed(false);
      setShowScrollToLatest(false);
    }, prefersReducedMotion ? 50 : 600);

    element.scrollTo({
      top: element.scrollHeight,
      behavior: prefersReducedMotion ? "auto" : "smooth",
    });
  }, []);

  const handleContentScroll = (event: ReactUIEvent<HTMLDivElement>) => {
    const container = event.currentTarget;
    setScrollIconSettling(true);
    refreshScrollToLatestVisibility(container);
    if (!composerFocused && !programmaticScrollRef.current) {
      const distanceToBottom =
        container.scrollHeight - (container.scrollTop + container.clientHeight);
      setComposerCollapsed(distanceToBottom > SCROLL_TO_LATEST_THRESHOLD_PX);
    }
    if (scrollIconHideTimeoutRef.current !== null) {
      window.clearTimeout(scrollIconHideTimeoutRef.current);
    }
    scrollIconHideTimeoutRef.current = window.setTimeout(() => {
      setScrollIconSettling(false);
      scrollIconHideTimeoutRef.current = null;
    }, SCROLL_ICON_SETTLE_MS);
  };

  useEffect(() => {
    if (!isSending || showScrollToLatest) {
      return;
    }
    const rafId = window.requestAnimationFrame(() => {
      scrollLatestTurnToTop();
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [isSending, isActivityStreaming, scrollLatestTurnToTop, showScrollToLatest]);

  useEffect(() => {
    const rafId = window.requestAnimationFrame(() => {
      refreshScrollToLatestVisibility();
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [
    chatTurns.length,
    isSending,
    isActivityStreaming,
    selectedTurnIndex,
    refreshScrollToLatestVisibility,
  ]);

  useEffect(() => {
    const container = contentScrollRef.current;
    if (!container || composerFocused || programmaticScrollRef.current) {
      return;
    }
    const distanceToBottom =
      container.scrollHeight - (container.scrollTop + container.clientHeight);
    setComposerCollapsed(distanceToBottom > SCROLL_TO_LATEST_THRESHOLD_PX);
  }, [chatTurns.length, composerFocused, selectedTurnIndex]);

  const composerVisible = !composerCollapsed || composerHovering || composerFocused;

  const handleSelectWorkflow = useCallback(
    (workflow: WorkflowCommandSelection) => {
      const steps = Array.isArray(workflow.definition?.steps) ? workflow.definition.steps : [];
      if (steps.length === 0) {
        toast.warning("This workflow has no steps.");
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
    <div
      className="relative h-full flex-1 min-h-0 min-w-0 flex flex-col overflow-hidden rounded-[28px] border border-black/[0.06] bg-[#f6f6f7] shadow-[0_14px_40px_rgba(15,23,42,0.06)]"
    >
      <div className="shrink-0 border-b border-black/[0.06] px-5 py-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">Dialogue</p>
          <h3 className="mt-1 text-[20px] font-semibold tracking-[-0.02em] text-[#17171b]">Conversation</h3>
        </div>
      </div>
      <div className="relative min-h-0 flex-1">
        <div
          ref={contentScrollRef}
          className="h-full overflow-y-auto overscroll-none px-6 pb-3 pt-6"
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
              autoFollowLatest={!showScrollToLatest}
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
        {showScrollToLatest && (scrollIconSettling || scrollIconHovering) ? (
          <button
            type="button"
            tabIndex={-1}
            onMouseDown={(e) => e.preventDefault()}
            onClick={scrollToLatestMessage}
            onMouseEnter={() => setScrollIconHovering(true)}
            onMouseLeave={() => setScrollIconHovering(false)}
            className="absolute inset-y-0 right-4 z-20 my-auto inline-flex h-10 w-10 items-center justify-center rounded-full border border-black/[0.08] bg-white/96 text-[#1d1d1f] shadow-[0_10px_24px_-18px_rgba(0,0,0,0.55)] transition hover:bg-white"
            aria-label="Scroll to latest message"
            title="Scroll to latest message"
          >
            <ArrowDown className="h-4 w-4 stroke-[2.4]" />
          </button>
        ) : null}
      </div>
      <div
        className="z-20 shrink-0"
        onMouseEnter={() => setComposerHovering(true)}
        onMouseLeave={() => setComposerHovering(false)}
      >
        {composerVisible ? (
          <div className="border-t border-black/[0.06] bg-[#f6f6f7] px-3 pb-3 pt-2">
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
              activeAgent={interactions.activeAgent}
              onAgentSelect={interactions.onAgentSelect}
              onSelectWorkflow={handleSelectWorkflow}
              activeWorkflow={interactions.activeWorkflow}
              onClearWorkflow={() => interactions.setActiveWorkflow(null)}
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
              onFocusWithinChange={(focused) => {
                setComposerFocused(focused);
                if (focused) {
                  setComposerCollapsed(false);
                }
              }}
            />
          </div>
        ) : (
          <div className="border-t border-black/[0.06] bg-[#f6f6f7] px-3 pt-3 pb-[42px]">
            <div className="mx-auto h-1.5 w-16 rounded-full bg-black/[0.12]" />
          </div>
        )}
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
