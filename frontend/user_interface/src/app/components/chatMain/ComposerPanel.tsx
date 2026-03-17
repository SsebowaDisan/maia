import { ArrowUp } from "lucide-react";
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
import type { AgentCommandSelection } from "./composer/AgentCommandMenu";
import { useComposerCommandPalette } from "./composer/commandPalette";
import { FilePreviewModal } from "./shared/FilePreviewModal";
import type { ComposerAttachment } from "./types";

const MAX_TEXTAREA_HEIGHT_PX = 168;

type ComposerPanelProps = {
  accessMode: "restricted" | "full_access";
  agentControlsVisible: boolean;
  agentMode: "ask" | "company_agent" | "deep_search";
  composerMode: "ask" | "company_agent" | "deep_search" | "web_search";
  attachments: ComposerAttachment[];
  clearAttachments: () => void;
  removeAttachment: (attachmentId: string) => void;
  enableAskMode: () => void;
  enableAgentMode: () => void;
  enableWebSearch: () => void;
  enableDeepResearch: () => void;
  activeAgent?: { agent_id: string; name: string } | null;
  onAgentSelect?: (agent: AgentCommandSelection | null) => void;
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
  enableAgentMode,
  enableWebSearch,
  enableDeepResearch,
  activeAgent = null,
  onAgentSelect,
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
  const canSubmit = Boolean(message.trim()) && !isUploading && !isSending;
  const sendDisabled = !canSubmit;
  const [previewAttachment, setPreviewAttachment] = useState<ComposerAttachment | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

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
  const agentPickerVisible = trimmedMessage.startsWith("@");

  useEffect(() => {
    if (!previewAttachment) {
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

  const attachmentStatusLabel = (attachment: ComposerAttachment) => {
    if (attachment.status === "uploading") {
      return attachment.message || "Uploading";
    }
    if (attachment.status === "error") {
      const detail = String(attachment.message || "").trim();
      if (!detail) {
        return "Failed";
      }
      const compact = detail.length > 42 ? `${detail.slice(0, 39)}...` : detail;
      return `Failed: ${compact}`;
    }
    return "";
  };

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
        <div className="assistantComposer rounded-[24px] border border-black/[0.07] bg-gradient-to-b from-[#f7f7f9] to-[#efeff2] shadow-[0_10px_28px_-24px_rgba(0,0,0,0.4)]">
          <div className="assistantComposerInputShell relative rounded-[16px] border border-black/[0.07] bg-white/96">
            <div className="flex min-w-0 flex-1">
              <textarea
                ref={textareaRef}
                rows={1}
                value={message}
                onChange={handleMessageChange}
                onInput={resizeComposerTextarea}
                placeholder="What would you like to do next?"
                aria-label="Message"
                className="assistantComposerInput min-w-0 flex-1 resize-none border-0 bg-transparent focus:outline-none"
                onKeyDown={handleComposerKeyDown}
                onKeyUp={syncCommandQueryFromTextarea}
                onClick={syncCommandQueryFromTextarea}
              />
            </div>
            {agentPickerVisible ? (
              <ComposerAgentPicker
                query={trimmedMessage}
                onPick={(agent) => {
                  const suffix = trimmedMessage.replace(/^@\S*\s*/, "").trim();
                  setMessage(suffix ? `${suffix} ` : "");
                  onAgentSelect?.({
                    agent_id: agent.agent_id,
                    name: agent.name,
                    description: String(agent.description || ""),
                    trigger_family: String(agent.trigger_family || ""),
                  });
                }}
              />
            ) : null}
            {commandQuery && commandOptions.length > 0 && !agentPickerVisible ? (
              <ComposerCommandMenu
                query={commandQuery}
                options={commandOptions}
                activeIndex={commandActiveIndex}
                onSelect={selectCommandOption}
              />
            ) : null}
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
                onChange={(value) => {
                  if (value === "ask") {
                    enableAskMode();
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
                attachmentStatusLabel={attachmentStatusLabel}
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
