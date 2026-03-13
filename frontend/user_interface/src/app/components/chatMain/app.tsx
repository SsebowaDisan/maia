import {
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type UIEvent as ReactUIEvent,
} from "react";
import { ArrowDown } from "lucide-react";
import { ClarificationResumeModal } from "./ClarificationResumeModal";
import { CanvasPanel } from "../canvas/CanvasPanel";
import { useCanvasStore } from "../../stores/canvasStore";
import type { ChatTurn } from "../../types";
import { ComposerPanel } from "./ComposerPanel";
import { EmptyState } from "./EmptyState";
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
const CONVERSATION_RAIL_SCROLL_VISIBILITY_MS = 820;

type ConversationRailMarker = {
  turnIndex: number;
  centerPx: number;
  topPercent: number;
  preview: string;
};

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
  const conversationRailHideTimeoutRef = useRef<number | null>(null);
  const [showComposerDuringActivity, setShowComposerDuringActivity] = useState(true);
  const [composerDockedByScroll, setComposerDockedByScroll] = useState(false);
  const [scrollSettling, setScrollSettling] = useState(false);
  const [distanceToBottom, setDistanceToBottom] = useState(0);
  const [isConversationScrolling, setIsConversationScrolling] = useState(false);
  const [conversationRailMarkers, setConversationRailMarkers] = useState<ConversationRailMarker[]>([]);
  const [activeConversationRailTurn, setActiveConversationRailTurn] = useState<number | null>(null);
  const maiaActive = isActivityStreaming || isSending;
  const canScrollToLatest = chatTurns.length > 0 && distanceToBottom > 16;
  const upsertDocuments = useCanvasStore((state) => state.upsertDocuments);

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
      if (conversationRailHideTimeoutRef.current !== null) {
        window.clearTimeout(conversationRailHideTimeoutRef.current);
      }
    },
    [],
  );

  const refreshConversationRail = (element: HTMLDivElement | null) => {
    if (!element) {
      setConversationRailMarkers([]);
      setActiveConversationRailTurn(null);
      return;
    }

    const turnNodes = Array.from(element.querySelectorAll<HTMLElement>("[data-turn-index]"));
    const totalHeight = Math.max(1, element.scrollHeight);
    const nextMarkers: ConversationRailMarker[] = [];

    turnNodes.forEach((node) => {
      const turnIndex = Number(node.dataset.turnIndex || NaN);
      if (!Number.isFinite(turnIndex) || turnIndex < 0 || turnIndex >= chatTurns.length) {
        return;
      }
      const prompt = String(chatTurns[turnIndex]?.user || "").trim();
      if (!prompt) {
        return;
      }
      const centerPx = node.offsetTop + node.offsetHeight / 2;
      const topPercent = Math.max(0, Math.min(100, (centerPx / totalHeight) * 100));
      nextMarkers.push({
        turnIndex,
        centerPx,
        topPercent,
        preview: prompt,
      });
    });

    setConversationRailMarkers(nextMarkers);
    if (nextMarkers.length === 0) {
      setActiveConversationRailTurn(null);
      return;
    }

    if (selectedTurnIndex !== null && nextMarkers.some((marker) => marker.turnIndex === selectedTurnIndex)) {
      setActiveConversationRailTurn(selectedTurnIndex);
      return;
    }

    const viewportCenter = element.scrollTop + element.clientHeight / 2;
    const nearest = nextMarkers.reduce((closest, marker) => {
      if (!closest) {
        return marker;
      }
      const currentDistance = Math.abs(marker.centerPx - viewportCenter);
      const closestDistance = Math.abs(closest.centerPx - viewportCenter);
      return currentDistance < closestDistance ? marker : closest;
    }, null as ConversationRailMarker | null);
    setActiveConversationRailTurn(nearest?.turnIndex ?? null);
  };

  const updateDistanceToBottom = (element: HTMLDivElement | null) => {
    if (!element) {
      setDistanceToBottom(0);
      return;
    }
    const nextDistance = Math.max(0, element.scrollHeight - element.scrollTop - element.clientHeight);
    setDistanceToBottom(nextDistance);
  };

  const scrollToLatestMessage = () => {
    const element = contentScrollRef.current;
    if (!element) {
      return;
    }
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false);
    element.scrollTo({
      top: element.scrollHeight,
      behavior: prefersReducedMotion ? "auto" : "smooth",
    });
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

    if (nextVisible && composerDockedByScroll && !maiaActive) {
      setComposerDockedByScroll(false);
    }
  };

  const handleMainMouseLeave = () => {
    if (!maiaActive && !composerDockedByScroll) {
      return;
    }
    setShowComposerDuringActivity(false);
  };

  const handleContentScroll = (event: ReactUIEvent<HTMLDivElement>) => {
    const element = event.currentTarget;
    updateDistanceToBottom(element);
    refreshConversationRail(element);
    setIsConversationScrolling(true);
    if (conversationRailHideTimeoutRef.current !== null) {
      window.clearTimeout(conversationRailHideTimeoutRef.current);
    }
    conversationRailHideTimeoutRef.current = window.setTimeout(() => {
      setIsConversationScrolling(false);
      conversationRailHideTimeoutRef.current = null;
    }, CONVERSATION_RAIL_SCROLL_VISIBILITY_MS);

    const distanceToBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    if (!maiaActive && distanceToBottom <= COMPOSER_REVEAL_DISTANCE_PX) {
      setComposerDockedByScroll(false);
      setScrollSettling(false);
      setShowComposerDuringActivity(true);
      if (scrollHideTimeoutRef.current !== null) {
        window.clearTimeout(scrollHideTimeoutRef.current);
        scrollHideTimeoutRef.current = null;
      }
      return;
    }

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
    updateDistanceToBottom(contentScrollRef.current);
    const rafId = window.requestAnimationFrame(() => {
      refreshConversationRail(contentScrollRef.current);
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [chatTurns.length, isSending, isActivityStreaming]);

  useEffect(() => {
    const onResize = () => {
      refreshConversationRail(contentScrollRef.current);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [chatTurns.length, selectedTurnIndex]);

  const handleConversationRailSelect = (turnIndex: number) => {
    const scrollElement = contentScrollRef.current;
    if (!scrollElement) {
      return;
    }
    const target = scrollElement.querySelector<HTMLElement>(`[data-turn-index="${String(turnIndex)}"]`);
    if (!target) {
      return;
    }
    onSelectTurn(turnIndex);
    setActiveConversationRailTurn(turnIndex);
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false);
    target.scrollIntoView({
      behavior: prefersReducedMotion ? "auto" : "smooth",
      block: "center",
      inline: "nearest",
    });
  };

  const composerVisible = maiaActive || composerDockedByScroll
    ? showComposerDuringActivity && !scrollSettling
    : true;
  const showJumpToLatestButton = canScrollToLatest && isConversationScrolling;
  const showConversationRail = conversationRailMarkers.length > 1 && isConversationScrolling;

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
        <button
          type="button"
          title="Jump to latest message"
          onClick={scrollToLatestMessage}
          className={`absolute right-5 z-20 inline-flex h-9 w-9 items-center justify-center rounded-full border shadow-sm transition-all duration-200 ${
            composerVisible ? "bottom-5" : "bottom-4"
          } ${
            showJumpToLatestButton
              ? "pointer-events-auto translate-y-0 opacity-100 border-black/[0.12] bg-white text-[#1d1d1f] hover:border-black/[0.2] hover:bg-[#f8f8fa]"
              : "pointer-events-none translate-y-2 opacity-0 border-black/[0.06] bg-[#f4f4f6] text-[#b0b2b8]"
          }`}
        >
          <ArrowDown className="h-4 w-4" />
        </button>

        <div
          className={`absolute right-[7px] top-6 z-20 w-4 transition-opacity duration-200 ${
            composerVisible ? "bottom-[108px]" : "bottom-6"
          } ${showConversationRail ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"}`}
          aria-hidden={!showConversationRail}
        >
          <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 rounded-full bg-black/[0.12]" />
          {conversationRailMarkers.map((marker) => {
            const isActive = activeConversationRailTurn === marker.turnIndex;
            return (
              <button
                key={`rail-marker-${marker.turnIndex}`}
                type="button"
                title={marker.preview}
                onClick={() => handleConversationRailSelect(marker.turnIndex)}
                className={`absolute left-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border transition-all duration-150 ${
                  isActive
                    ? "h-2.5 w-2.5 border-black/60 bg-[#1d1d1f] shadow-[0_0_0_3px_rgba(255,255,255,0.9)]"
                    : "h-2 w-2 border-black/[0.22] bg-white hover:h-2.5 hover:w-2.5 hover:border-black/[0.42]"
                }`}
                style={{ top: `${marker.topPercent}%` }}
                aria-label={`Go to prompt ${marker.turnIndex + 1}`}
              />
            );
          })}
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
