import {
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type UIEvent as ReactUIEvent,
} from "react";
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
  const scrollHideTimeoutRef = useRef<number | null>(null);
  const [showComposerDuringActivity, setShowComposerDuringActivity] = useState(true);
  const [composerDockedByScroll, setComposerDockedByScroll] = useState(false);
  const [scrollSettling, setScrollSettling] = useState(false);
  const maiaActive = isActivityStreaming || isSending;
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
    },
    [],
  );

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
        <div className="h-full overflow-y-auto px-6 pb-10 pt-6" onScroll={handleContentScroll}>
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
