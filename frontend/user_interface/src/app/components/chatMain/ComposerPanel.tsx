import { ArrowUp, GitBranch } from "lucide-react";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type RefObject,
} from "react";
import type { FileGroupRecord, FileRecord } from "../../../api/client";
import type { SidebarProject } from "../../appShell/types";
import { AccessModeDropdown } from "../AccessModeDropdown";
import { ComposerModeSelector } from "../ComposerModeSelector";
import { ComposerQuickActionsCard } from "../ComposerQuickActionsCard";
import { ComposerAttachmentChips } from "./composer/ComposerAttachmentChips";
import { ComposerAgentPicker } from "./composer/ComposerAgentPicker";
import { ComposerCommandMenu } from "./composer/ComposerCommandMenu";
import type { AgentCommandSelection, WorkflowCommandSelection } from "./composer/AgentCommandMenu";
import { useComposerCommandPalette } from "./composer/commandPalette";
import { FilePreviewModal } from "./shared/FilePreviewModal";
import type { ComposerAttachment } from "./types";
import { openConnectorOverlay } from "../../utils/connectorOverlay";

const MAX_TEXTAREA_HEIGHT_PX = 168;

type ComposerPanelProps = {
  accessMode: "restricted" | "full_access";
  agentControlsVisible: boolean;
  agentMode: "ask" | "rag" | "company_agent" | "deep_search";
  composerMode: "ask" | "rag" | "company_agent" | "deep_search" | "web_search" | "brain";
  attachments: ComposerAttachment[];
  clearAttachments: () => void;
  removeAttachment: (attachmentId: string) => void;
  enableAskMode: () => void;
  enableRagMode: () => void;
  enableAgentMode: () => void;
  enableBrainMode: () => void;
  enableWebSearch: () => void;
  enableDeepResearch: () => void;
  activeAgent?: { agent_id: string; name: string } | null;
  onAgentSelect?: (agent: AgentCommandSelection | null) => void;
  onSelectWorkflow?: (workflow: WorkflowCommandSelection) => void;
  activeWorkflow?: {
    workflow_id: string;
    name: string;
    missing_connectors?: string[];
  } | null;
  onClearWorkflow?: () => void;
  fileInputRef: RefObject<HTMLInputElement | null>;
  isSending: boolean;
  isUploading: boolean;
  latestHighlightSnippets: string[];
  message: string;
  messageActionStatus: string;
  documentOptions: FileRecord[];
  groupOptions: FileGroupRecord[];
  projectOptions: SidebarProject[];
  onAccessModeChange: (mode: "restricted" | "full_access") => void;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => Promise<void>;
  onAttachDocument: (documentId: string) => void;
  onAttachGroup: (groupId: string) => void;
  onAttachProject: (projectId: string) => void;
  pasteHighlightsToComposer: () => void;
  setMessage: (value: string) => void;
  submit: () => Promise<void>;
  onFocusWithinChange?: (focused: boolean) => void;
};

function ComposerPanel({
  accessMode,
  agentControlsVisible,
  agentMode,
  composerMode,
  attachments,
  clearAttachments,
  removeAttachment,
  enableAskMode,
  enableRagMode,
  enableAgentMode,
  enableBrainMode,
  enableWebSearch,
  enableDeepResearch,
  activeAgent = null,
  onAgentSelect,
  onSelectWorkflow,
  activeWorkflow = null,
  onClearWorkflow,
  fileInputRef,
  isSending,
  isUploading,
  latestHighlightSnippets,
  message,
  messageActionStatus,
  documentOptions,
  groupOptions,
  projectOptions,
  onAccessModeChange,
  onFileChange,
  onAttachDocument,
  onAttachGroup,
  onAttachProject,
  pasteHighlightsToComposer,
  setMessage,
  submit,
  onFocusWithinChange,
}: ComposerPanelProps) {
  const hasPendingAttachments = attachments.some(
    (attachment) => attachment.status === "uploading" || attachment.status === "indexing",
  );
  const canSubmit = Boolean(message.trim()) && !isSending && !hasPendingAttachments;
  const sendDisabled = !canSubmit;
  const [previewAttachment, setPreviewAttachment] = useState<ComposerAttachment | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const missingConnectors = Array.isArray(activeWorkflow?.missing_connectors)
    ? activeWorkflow.missing_connectors
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];

  const resizeComposerTextarea = useCallback(() => {
    const element = textareaRef.current;
    if (!element) {
      return;
    }
    element.style.height = "0px";
    const nextHeight = Math.min(element.scrollHeight, MAX_TEXTAREA_HEIGHT_PX);
    element.style.height = `${nextHeight}px`;
    element.style.overflowY = element.scrollHeight > MAX_TEXTAREA_HEIGHT_PX ? "auto" : "hidden";
  }, []);

  const submitIfPossible = useCallback(() => {
    if (!canSubmit) {
      return;
    }
    void submit();
  }, [canSubmit, submit]);

  const {
    commandActiveIndex,
    commandOptions,
    commandQuery,
    handleComposerKeyDown,
    handleMessageChange,
    selectCommandOption,
    syncCommandQueryFromTextarea,
  } = useComposerCommandPalette({
    message,
    setMessage,
    textareaRef,
    documentOptions,
    groupOptions,
    projectOptions,
    onAttachDocument,
    onAttachGroup,
    onAttachProject,
    onSubmit: submitIfPossible,
  });

  const trimmedMessage = message.trimStart();
  // "@" now triggers the document/file command palette, not the agent picker.
  // Agent picker is accessed via the mode selector button instead.
  const agentPickerVisible = false;

  useEffect(() => {
    if (!previewAttachment) {
      return;
    }
    // Don't auto-close previews for files opened from the document menu (kind === "file")
    if (previewAttachment.kind === "file") {
      return;
    }
    if (!attachments.some((item) => item.id === previewAttachment.id)) {
      setPreviewAttachment(null);
    }
  }, [attachments, previewAttachment]);

  useEffect(() => {
    if (!previewAttachment) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPreviewAttachment(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [previewAttachment]);

  useEffect(() => {
    resizeComposerTextarea();
  }, [message, resizeComposerTextarea]);

  return (
    <div
      className="bg-transparent"
      onFocusCapture={() => onFocusWithinChange?.(true)}
      onBlurCapture={(event) => {
        const nextTarget = event.relatedTarget as Node | null;
        if (!event.currentTarget.contains(nextTarget)) {
          onFocusWithinChange?.(false);
        }
      }}
    >
      <div className="mx-auto w-full max-w-[1460px] px-3 pt-2 pb-0">
        {activeWorkflow && missingConnectors.length ? (
          <div className="mb-2 rounded-xl border border-[#fde68a] bg-[#fffbeb] px-3 py-2">
            <p className="text-[12px] font-semibold text-[#92400e]">
              This workflow needs {missingConnectors.join(", ")}. Connect now to run successfully.
            </p>
            <button
              type="button"
              onClick={() =>
                openConnectorOverlay(missingConnectors[0], {
                  fromPath: window.location.pathname || "/",
                })
              }
              className="mt-1 text-[12px] font-semibold text-[#7c2d12] underline-offset-2 hover:underline"
            >
              Connect now
            </button>
          </div>
        ) : null}
        {activeWorkflow ? (
          <div className="mb-1.5 flex items-center gap-1.5">
            <span className="inline-flex max-w-[280px] items-center gap-1.5 rounded-full border border-[#c4b5fd] bg-[#f5f3ff] px-2.5 py-1 text-[11px] font-semibold text-[#7c3aed]">
              <GitBranch className="h-3 w-3 shrink-0" />
              <span className="truncate">{activeWorkflow.name}</span>
              <button
                type="button"
                onClick={onClearWorkflow}
                className="ml-0.5 inline-flex h-3.5 w-3.5 items-center justify-center rounded-full hover:bg-[#7c3aed]/10"
                aria-label="Remove workflow"
              >
                &times;
              </button>
            </span>
          </div>
        ) : null}
        {/* Document/file mention popup — renders above the composer */}
        {commandQuery && commandOptions.length > 0 ? (
          <div className="relative mb-2">
            <ComposerCommandMenu
              query={commandQuery}
              options={commandOptions}
              activeIndex={commandActiveIndex}
              onSelect={selectCommandOption}
              onPreview={(option) => {
                setPreviewAttachment({
                  id: option.id,
                  name: option.label,
                  status: "uploaded",
                  fileId: option.id,
                  kind: "file",
                });
              }}
            />
          </div>
        ) : null}
        <div className="assistantComposer rounded-[24px] border border-black/[0.07] bg-gradient-to-b from-[#f7f7f9] to-[#efeff2] shadow-[0_10px_28px_-24px_rgba(0,0,0,0.4)]">
          <div className="assistantComposerInputShell relative rounded-[16px] border border-black/[0.07] bg-white/96">
            <div className="flex min-w-0 flex-1">
              <textarea
                ref={textareaRef}
                rows={1}
                value={message}
                onChange={handleMessageChange}
                onInput={resizeComposerTextarea}
                placeholder={
                  composerMode === "brain"
                    ? "Describe what you want — the Brain will assemble a team and run it..."
                    : composerMode === "rag"
                      ? "Ask Maia to answer from your files and indexed URLs..."
                    : composerMode === "deep_search"
                      ? "What would you like to research in depth?"
                      : composerMode === "web_search"
                        ? "Search the web for..."
                        : composerMode === "company_agent"
                          ? "What would you like the workflow to do?"
                          : "What would you like to do next?"
                }
                aria-label="Message"
                className="assistantComposerInput min-w-0 flex-1 resize-none border-0 bg-transparent focus:outline-none"
                onKeyDown={handleComposerKeyDown}
                onKeyUp={syncCommandQueryFromTextarea}
                onClick={syncCommandQueryFromTextarea}
              />
            </div>
          </div>

          <div className="assistantComposerToolbar">
            <div className="assistantComposerTools">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(event) => {
                  void onFileChange(event);
                }}
              />
              <ComposerQuickActionsCard
                onUploadFile={() => fileInputRef.current?.click()}
                onPasteHighlights={pasteHighlightsToComposer}
                canPasteHighlights={latestHighlightSnippets.length > 0}
                disableUpload={isUploading || isSending}
                triggerClassName="composerAttachButton inline-flex items-center justify-center rounded-full border border-black/[0.08] bg-white text-[#6e6e73] shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-colors duration-150 hover:bg-[#f7f7f8] hover:text-[#1d1d1f] disabled:opacity-40"
              />
              <ComposerModeSelector
                value={composerMode}
                activeAgent={activeAgent}
                onAgentSelect={onAgentSelect}
                onSelectWorkflow={onSelectWorkflow}
                onChange={(value) => {
                  if (value === "ask") {
                    enableAskMode();
                    return;
                  }
                  if (value === "rag") {
                    enableRagMode();
                    return;
                  }
                  if (value === "brain") {
                    enableBrainMode();
                    return;
                  }
                  if (value === "company_agent") {
                    enableAgentMode();
                    return;
                  }
                  if (value === "web_search") {
                    enableWebSearch();
                    return;
                  }
                  enableDeepResearch();
                }}
              />

              <ComposerAttachmentChips
                attachments={attachments}
                isSending={isSending}
                onClearAttachments={clearAttachments}
                onOpenPreview={setPreviewAttachment}
                onRemoveAttachment={removeAttachment}
              />

              <div className="assistantComposerAccessSlot">
                <div
                  className="accessReveal"
                  data-visible={agentControlsVisible && agentMode === "company_agent" ? "true" : "false"}
                >
                  {agentControlsVisible && agentMode === "company_agent" ? (
                    <AccessModeDropdown
                      value={accessMode}
                      onChange={(value) => onAccessModeChange(value)}
                    />
                  ) : (
                    <span className="accessPopupPlaceholder" aria-hidden="true" />
                  )}
                </div>
              </div>
            </div>

            <div className="assistantComposerActions">
              <button
                type="button"
                className={`inline-flex h-10 w-10 items-center justify-center rounded-full border border-black/[0.1] shadow-[0_6px_14px_-12px_rgba(0,0,0,0.35)] transition-colors duration-150 ${
                  isSending ? "bg-white text-black" : "bg-white text-black hover:bg-[#f5f5f7]"
                } ${sendDisabled && !isSending ? "cursor-not-allowed opacity-45" : ""}`}
                disabled={sendDisabled}
                onClick={submitIfPossible}
                aria-label={isSending ? "Maia is working" : "Send message"}
                title={isSending ? "Maia is working" : "Send"}
              >
                {isSending ? (
                  <span className="h-3 w-3 rounded-[2px] bg-black" aria-hidden="true" />
                ) : (
                  <ArrowUp className="h-4.5 w-4.5 stroke-[2.3]" />
                )}
              </button>
            </div>
          </div>
        </div>
        {messageActionStatus ? (
          <div className="pointer-events-none fixed bottom-5 right-6 z-[120]">
            <div className="rounded-xl border border-black/[0.08] bg-white/95 px-3 py-2 text-[12px] text-[#4c4c50] shadow-[0_16px_34px_-24px_rgba(0,0,0,0.55)] backdrop-blur">
              {messageActionStatus}
            </div>
          </div>
        ) : null}
      </div>

      <FilePreviewModal
        attachment={previewAttachment}
        onClose={() => setPreviewAttachment(null)}
        emptyPreviewMessage="Preview will be available once upload is ready."
      />
    </div>
  );
}

export { ComposerPanel };
export type { WorkflowCommandSelection };
