import { type MouseEvent as ReactMouseEvent } from "react";
import { ClarificationResumeModal } from "./ClarificationResumeModal";
import type { ChatTurn } from "../../types";
import { ComposerPanel } from "./ComposerPanel";
import { EmptyState } from "./EmptyState";
import { CITATION_ANCHOR_SELECTOR, resolveCitationFocusFromAnchor } from "./citationFocus";
import type { ChatMainProps } from "./types";
import { TurnsPanel } from "./TurnsPanel";
import { useChatMainInteractions } from "./useChatMainInteractions";

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
      event.preventDefault();
      event.stopPropagation();
      onSelectTurn(index);
      const resolved = resolveCitationFocusFromAnchor({ turn, citationAnchor });
      onCitationClick(resolved.focus);
      return;
    }
    onSelectTurn(index);
  };

  return (
    <div className="flex-1 min-h-0 min-w-0 flex flex-col bg-white overflow-hidden">
      <div className="flex-1 px-6 py-6 overflow-y-auto">
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
            quoteAssistant={interactions.quoteAssistant}
            retryTurn={interactions.retryTurn}
            saveInlineEdit={interactions.saveInlineEdit}
            selectedTurnIndex={selectedTurnIndex}
            setEditingText={interactions.setEditingText}
            citationFocus={citationFocus}
          />
        )}
      </div>

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
