import { AlertCircle, ArrowUp, ExternalLink, FileText, Loader2, X } from "lucide-react";
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
import { AccessModeDropdown } from "../AccessModeDropdown";
import { ComposerQuickActionsCard } from "../ComposerQuickActionsCard";
import type { ComposerAttachment } from "./types";

const MAX_TEXTAREA_HEIGHT_PX = 168;

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
  onAccessModeChange: (mode: "restricted" | "full_access") => void;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => Promise<void>;
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
  onAccessModeChange,
  onFileChange,
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

  const handleMessageChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    setMessage(event.target.value);
  };

  const handleComposerKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
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
      <div className="mx-auto w-full max-w-[1800px] px-6 py-4">
        <div className="assistantComposer rounded-[22px] border border-black/[0.08] bg-[#f3f3f5]">
          <div className="assistantComposerInputShell rounded-[14px] border border-black/[0.08] bg-white">
            <div className="flex min-w-0 flex-1">
              <textarea
                ref={textareaRef}
                rows={1}
                value={message}
                onChange={handleMessageChange}
                onInput={resizeComposerTextarea}
                placeholder="What would you like to do next?"
                aria-label="Message"
                className="assistantComposerInput min-w-0 flex-1 resize-none border-0 bg-transparent text-[15px] text-[#1d1d1f] placeholder:text-[#86868b] focus:outline-none"
                onKeyDown={handleComposerKeyDown}
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
                        <button
                          type="button"
                          onClick={() => handleOpenPreview(attachment)}
                          className="inline-flex min-w-0 items-center gap-1.5 px-2.5 py-1 transition-colors duration-150 hover:bg-[#f7f7f8] rounded-l-full"
                        >
                          {attachment.status === "uploading" ? (
                            <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-[#6e6e73]" />
                          ) : attachment.status === "error" ? (
                            <AlertCircle className="h-3.5 w-3.5 shrink-0 text-[#d44848]" />
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
                      title="Clear all attached files"
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
