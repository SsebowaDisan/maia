import { AlertCircle, ArrowUp, ExternalLink, FileText, Folder, Loader2, X } from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type RefObject,
} from "react";
import { buildRawFileUrl } from "../../../api/client";
import type { FileGroupRecord, FileRecord } from "../../../api/client";
import type { SidebarProject } from "../../appShell/types";
import { AccessModeDropdown } from "../AccessModeDropdown";
import { ComposerQuickActionsCard } from "../ComposerQuickActionsCard";
import type { ComposerAttachment } from "./types";

const MAX_TEXTAREA_HEIGHT_PX = 168;
const MAX_COMMAND_OPTIONS = 8;

type CommandTrigger = "document" | "group" | "project";
type CommandOption = {
  id: string;
  label: string;
  subtitle?: string;
};
type CommandQueryState = {
  trigger: CommandTrigger;
  query: string;
  tokenStart: number;
  caret: number;
};

const TRIGGER_MAP: Record<string, CommandTrigger> = {
  "@": "document",
  "#": "group",
  "/": "project",
};

function resolveCommandQuery(text: string, caret: number): CommandQueryState | null {
  const safeCaret = Math.max(0, Math.min(caret, text.length));
  const beforeCaret = text.slice(0, safeCaret);
  const match = /(^|\s)([@#/])([^\s@#/]*)$/.exec(beforeCaret);
  if (!match) {
    return null;
  }
  const triggerChar = String(match[2] || "");
  const trigger = TRIGGER_MAP[triggerChar];
  if (!trigger) {
    return null;
  }
  const query = String(match[3] || "");
  const tokenStart = safeCaret - query.length - 1;
  if (tokenStart < 0) {
    return null;
  }
  return {
    trigger,
    query,
    tokenStart,
    caret: safeCaret,
  };
}

type ComposerPanelProps = {
  accessMode: "restricted" | "full_access";
  agentControlsVisible: boolean;
  agentMode: "ask" | "company_agent";
  attachments: ComposerAttachment[];
  clearAttachments: () => void;
  removeAttachment: (attachmentId: string) => void;
  enableAgentMode: () => void;
  enableDeepResearch: () => void;
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
};

function ComposerPanel({
  accessMode,
  agentControlsVisible,
  agentMode,
  attachments,
  clearAttachments,
  removeAttachment,
  enableAgentMode,
  enableDeepResearch,
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
}: ComposerPanelProps) {
  const visibleAttachments = attachments.slice(0, 3);
  const hiddenAttachmentCount = Math.max(0, attachments.length - visibleAttachments.length);
  const canSubmit = Boolean(message.trim()) && !isUploading && !isSending;
  const sendDisabled = !canSubmit;

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

  const [previewAttachment, setPreviewAttachment] = useState<ComposerAttachment | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [commandQuery, setCommandQuery] = useState<CommandQueryState | null>(null);
  const [commandActiveIndex, setCommandActiveIndex] = useState(0);

  const resizeComposerTextarea = useCallback(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "0px";
    const nextHeight = Math.min(element.scrollHeight, MAX_TEXTAREA_HEIGHT_PX);
    element.style.height = `${nextHeight}px`;
    element.style.overflowY = element.scrollHeight > MAX_TEXTAREA_HEIGHT_PX ? "auto" : "hidden";
  }, []);

  const submitIfPossible = () => {
    if (!canSubmit) return;
    void submit();
  };

  const commandOptions = useMemo<CommandOption[]>(() => {
    if (!commandQuery) {
      return [];
    }
    const normalizedQuery = commandQuery.query.trim().toLowerCase();
    const includeOption = (value: string) =>
      !normalizedQuery || value.toLowerCase().includes(normalizedQuery);

    if (commandQuery.trigger === "document") {
      return documentOptions
        .filter((item) => includeOption(item.name))
        .slice(0, MAX_COMMAND_OPTIONS)
        .map((item) => ({
          id: item.id,
          label: item.name,
          subtitle: "Document",
        }));
    }
    if (commandQuery.trigger === "group") {
      return groupOptions
        .filter((item) => includeOption(item.name))
        .slice(0, MAX_COMMAND_OPTIONS)
        .map((item) => ({
          id: item.id,
          label: item.name,
          subtitle: `${(item.file_ids || []).length} docs`,
        }));
    }
    return projectOptions
      .filter((item) => includeOption(item.name))
      .slice(0, MAX_COMMAND_OPTIONS)
      .map((item) => ({
        id: item.id,
        label: item.name,
        subtitle: "Project",
      }));
  }, [commandQuery, documentOptions, groupOptions, projectOptions]);

  const updateCommandQuery = useCallback(
    (nextText: string, caret: number) => {
      const next = resolveCommandQuery(nextText, caret);
      setCommandQuery(next);
      setCommandActiveIndex(0);
    },
    [setCommandQuery],
  );

  const removeCommandToken = useCallback(
    (query: CommandQueryState) => {
      const before = message.slice(0, query.tokenStart).replace(/\s+$/, " ");
      const after = message.slice(query.caret).replace(/^\s+/, "");
      const nextMessage = `${before}${after}`.replace(/\s{3,}/g, " ").trimStart();
      setMessage(nextMessage);
      window.requestAnimationFrame(() => {
        const element = textareaRef.current;
        if (!element) return;
        const caretPosition = Math.max(0, Math.min(before.length, nextMessage.length));
        element.focus();
        element.setSelectionRange(caretPosition, caretPosition);
      });
      setCommandQuery(null);
      setCommandActiveIndex(0);
    },
    [message, setMessage],
  );

  const attachFromCommand = useCallback(
    (option: CommandOption) => {
      if (!commandQuery) {
        return;
      }
      if (commandQuery.trigger === "document") {
        onAttachDocument(option.id);
      } else if (commandQuery.trigger === "group") {
        onAttachGroup(option.id);
      } else {
        onAttachProject(option.id);
      }
      removeCommandToken(commandQuery);
    },
    [commandQuery, onAttachDocument, onAttachGroup, onAttachProject, removeCommandToken],
  );

  const handleMessageChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    const nextMessage = event.target.value;
    setMessage(nextMessage);
    updateCommandQuery(nextMessage, event.target.selectionStart ?? nextMessage.length);
  };

  const syncCommandQueryFromTextarea = () => {
    const element = textareaRef.current;
    if (!element) {
      return;
    }
    const nextValue = element.value;
    updateCommandQuery(nextValue, element.selectionStart ?? nextValue.length);
  };

  const handleComposerKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (commandQuery && commandOptions.length > 0) {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setCommandActiveIndex((previous) =>
          commandOptions.length <= 0 ? 0 : (previous + 1) % commandOptions.length,
        );
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        setCommandActiveIndex((previous) =>
          commandOptions.length <= 0
            ? 0
            : (previous - 1 + commandOptions.length) % commandOptions.length,
        );
        return;
      }
      if (event.key === "Tab" || event.key === "Enter") {
        event.preventDefault();
        const option = commandOptions[Math.max(0, Math.min(commandActiveIndex, commandOptions.length - 1))];
        if (option) {
          attachFromCommand(option);
        }
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setCommandQuery(null);
        setCommandActiveIndex(0);
        return;
      }
    }

    if (event.key !== "Enter" || event.nativeEvent.isComposing) return;
    if (event.shiftKey) return;
    event.preventDefault();
    submitIfPossible();
  };

  useEffect(() => {
    if (!previewAttachment) return;
    if (!attachments.some((item) => item.id === previewAttachment.id)) {
      setPreviewAttachment(null);
    }
  }, [attachments, previewAttachment]);

  useEffect(() => {
    if (!commandOptions.length) {
      setCommandActiveIndex(0);
      return;
    }
    setCommandActiveIndex((previous) =>
      Math.max(0, Math.min(previous, commandOptions.length - 1)),
    );
  }, [commandOptions.length]);

  useEffect(() => {
    if (!previewAttachment) return;
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

  useEffect(() => {
    if (message.length === 0 && commandQuery) {
      setCommandQuery(null);
      setCommandActiveIndex(0);
    }
  }, [commandQuery, message]);

  const previewUrl = useMemo(() => {
    if (!previewAttachment) return "";
    if (previewAttachment.localUrl) return previewAttachment.localUrl;
    if (previewAttachment.fileId) return buildRawFileUrl(previewAttachment.fileId);
    return "";
  }, [previewAttachment]);

  const previewName = previewAttachment?.name || "";
  const previewNameLower = previewName.toLowerCase();
  const previewMime = String(previewAttachment?.mimeType || "").toLowerCase();
  const previewIsImage =
    previewMime.startsWith("image/") ||
    /\.(png|jpe?g|gif|bmp|webp|svg|tiff?)$/i.test(previewNameLower);
  const previewIsPdf = previewMime === "application/pdf" || previewNameLower.endsWith(".pdf");

  const handleOpenPreview = (attachment: ComposerAttachment) => {
    setPreviewAttachment(attachment);
  };

  return (
    <div className="border-t border-black/[0.06] bg-white">
      <div className="mx-auto w-full max-w-[1460px] px-6 py-4">
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
                className="assistantComposerInput min-w-0 flex-1 resize-none border-0 bg-transparent text-[15px] text-[#1d1d1f] placeholder:text-[#8b8b92] focus:outline-none"
                onKeyDown={handleComposerKeyDown}
                onKeyUp={syncCommandQueryFromTextarea}
                onClick={syncCommandQueryFromTextarea}
              />
            </div>
            {commandQuery && commandOptions.length > 0 ? (
              <div className="absolute bottom-full left-3 right-3 z-20 mb-2 overflow-hidden rounded-2xl border border-black/[0.1] bg-white shadow-[0_18px_38px_-24px_rgba(0,0,0,0.5)]">
                <div className="border-b border-black/[0.06] px-3 py-2 text-[11px] text-[#6e6e73]">
                  {commandQuery.trigger === "document"
                    ? "Attach document"
                    : commandQuery.trigger === "group"
                      ? "Attach group"
                      : "Attach project"}
                </div>
                <ul className="max-h-56 overflow-y-auto py-1.5">
                  {commandOptions.map((option, index) => (
                    <li key={`${commandQuery.trigger}-${option.id}`}>
                      <button
                        type="button"
                        onMouseDown={(event) => {
                          event.preventDefault();
                          attachFromCommand(option);
                        }}
                        className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[13px] transition-colors ${
                          index === commandActiveIndex
                            ? "bg-[#f3f3f6] text-[#1d1d1f]"
                            : "text-[#2a2a2d] hover:bg-[#f8f8fa]"
                        }`}
                      >
                        <span className="truncate">{option.label}</span>
                        {option.subtitle ? (
                          <span className="shrink-0 text-[11px] text-[#8d8d93]">{option.subtitle}</span>
                        ) : null}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
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
                onSelectAgent={enableAgentMode}
                onSelectDeepResearch={enableDeepResearch}
                onPasteHighlights={pasteHighlightsToComposer}
                canPasteHighlights={latestHighlightSnippets.length > 0}
                disableUpload={isUploading || isSending}
                triggerClassName="composerAttachButton inline-flex items-center justify-center rounded-full border border-black/[0.08] bg-white text-[#6e6e73] shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-colors duration-150 hover:bg-[#f7f7f8] hover:text-[#1d1d1f] disabled:opacity-40"
              />

              {attachments.length > 0 ? (
                <div className="flex min-w-0 max-w-[50vw] items-center gap-2">
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5 overflow-hidden pr-1">
                    {visibleAttachments.map((attachment) => (
                      <div
                        key={attachment.id}
                        className="inline-flex h-7 max-w-[260px] items-center rounded-full border border-black/[0.08] bg-white text-[11px] text-[#1d1d1f] shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
                        title={
                          attachment.message
                            ? `${attachment.name} - ${attachment.message}`
                            : attachment.name
                        }
                      >
                        {attachment.localUrl || attachment.fileId ? (
                          <button
                            type="button"
                            onClick={() => handleOpenPreview(attachment)}
                            className="inline-flex min-w-0 items-center gap-1.5 rounded-l-full px-2.5 py-1 transition-colors duration-150 hover:bg-[#f7f7f8]"
                          >
                            {attachment.status === "uploading" ? (
                              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-[#6e6e73]" />
                            ) : attachment.status === "error" ? (
                              <AlertCircle className="h-3.5 w-3.5 shrink-0 text-[#d44848]" />
                            ) : attachment.kind === "project" ? (
                              <Folder className="h-3.5 w-3.5 shrink-0 text-[#6e6e73]" />
                            ) : (
                              <FileText className="h-3.5 w-3.5 shrink-0 text-[#6e6e73]" />
                            )}
                            <span className="truncate">{attachment.name}</span>
                            {attachmentStatusLabel(attachment) ? (
                              <span className="shrink-0 text-[10px] text-[#8d8d93]">
                                {attachmentStatusLabel(attachment)}
                              </span>
                            ) : null}
                          </button>
                        ) : (
                          <div className="inline-flex min-w-0 items-center gap-1.5 rounded-l-full px-2.5 py-1">
                            {attachment.status === "uploading" ? (
                              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-[#6e6e73]" />
                            ) : attachment.status === "error" ? (
                              <AlertCircle className="h-3.5 w-3.5 shrink-0 text-[#d44848]" />
                            ) : attachment.kind === "project" ? (
                              <Folder className="h-3.5 w-3.5 shrink-0 text-[#6e6e73]" />
                            ) : (
                              <FileText className="h-3.5 w-3.5 shrink-0 text-[#6e6e73]" />
                            )}
                            <span className="truncate">{attachment.name}</span>
                            {attachmentStatusLabel(attachment) ? (
                              <span className="shrink-0 text-[10px] text-[#8d8d93]">
                                {attachmentStatusLabel(attachment)}
                              </span>
                            ) : null}
                          </div>
                        )}
                        <button
                          type="button"
                          onClick={() => removeAttachment(attachment.id)}
                          disabled={isSending}
                          className="inline-flex items-center px-2 py-1 text-[#8d8d93] transition-colors duration-150 hover:text-[#1d1d1f] disabled:opacity-50"
                          aria-label={`Remove ${attachment.name}`}
                          title={`Remove ${attachment.name}`}
                        >
                          <X className="h-3 w-3 shrink-0" />
                        </button>
                      </div>
                    ))}
                    {hiddenAttachmentCount > 0 ? (
                      <span className="inline-flex h-7 items-center rounded-full border border-black/[0.08] bg-white px-2.5 text-[11px] text-[#6e6e73]">
                        +{hiddenAttachmentCount} more
                      </span>
                    ) : null}
                  </div>

                  {attachments.length > 1 ? (
                    <button
                      type="button"
                      onClick={clearAttachments}
                      className="inline-flex h-7 shrink-0 items-center gap-1 rounded-full border border-black/[0.08] bg-white px-2.5 text-[11px] text-[#6e6e73] transition-colors duration-150 hover:bg-[#f7f7f8] hover:text-[#1d1d1f]"
                      title="Clear all attachments"
                    >
                      <X className="h-3 w-3" />
                      <span>Clear</span>
                    </button>
                  ) : null}
                </div>
              ) : null}

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
                  isSending
                    ? "bg-white text-black"
                    : "bg-white text-black hover:bg-[#f5f5f7]"
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

      {previewAttachment ? (
        <div className="fixed inset-0 z-[140] bg-black/45 backdrop-blur-[2px] px-4 py-6" onClick={() => setPreviewAttachment(null)}>
          <div
            className="mx-auto flex h-full w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-[0_24px_70px_-28px_rgba(0,0,0,0.65)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-black/[0.06] px-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-[14px] font-medium text-[#1d1d1f]" title={previewAttachment.name}>
                  {previewAttachment.name}
                </p>
                {previewAttachment.message ? (
                  <p className="text-[12px] text-[#8d8d93]">{previewAttachment.message}</p>
                ) : null}
              </div>
              <div className="ml-3 flex items-center gap-2">
                {previewUrl ? (
                  <a
                    href={previewUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded-full border border-black/[0.1] px-3 py-1.5 text-[11px] text-[#1d1d1f] hover:bg-[#f5f5f7]"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Open
                  </a>
                ) : null}
                <button
                  type="button"
                  onClick={() => setPreviewAttachment(null)}
                  className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/[0.1] text-[#6e6e73] hover:bg-[#f5f5f7] hover:text-[#1d1d1f]"
                  aria-label="Close preview"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto bg-[#f5f5f7] p-4">
              {!previewUrl ? (
                <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-black/[0.12] bg-white text-[13px] text-[#6e6e73]">
                  Preview will be available once upload is ready.
                </div>
              ) : previewIsImage ? (
                <div className="flex min-h-full items-start justify-center">
                  <img src={previewUrl} alt={previewAttachment.name} className="h-auto max-w-full rounded-xl border border-black/[0.08] bg-white" />
                </div>
              ) : previewIsPdf ? (
                <iframe
                  src={previewUrl}
                  title={`Preview ${previewAttachment.name}`}
                  className="h-full min-h-[420px] w-full rounded-xl border border-black/[0.08] bg-white"
                />
              ) : (
                <iframe
                  src={previewUrl}
                  title={`Preview ${previewAttachment.name}`}
                  className="h-full min-h-[420px] w-full rounded-xl border border-black/[0.08] bg-white"
                />
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export { ComposerPanel };
