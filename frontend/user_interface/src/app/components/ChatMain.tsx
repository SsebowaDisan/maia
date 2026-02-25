import {
  type ChangeEvent,
  type MouseEvent as ReactMouseEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  Copy,
  FileText,
  Loader2,
  Maximize2,
  Minimize2,
  PenLine,
  Paperclip,
  RotateCcw,
  Send,
  X,
} from "lucide-react";
import type { AgentActivityEvent, ChatAttachment, ChatTurn, CitationFocus } from "../types";
import type { UploadResponse } from "../../api/client";
import { renderRichText } from "../utils/richText";
import { parseEvidence } from "../utils/infoInsights";
import { AgentActivityPanel } from "./AgentActivityPanel";

interface ChatMainProps {
  onToggleInfoPanel: () => void;
  isInfoPanelOpen: boolean;
  chatTurns: ChatTurn[];
  selectedTurnIndex: number | null;
  onSelectTurn: (turnIndex: number) => void;
  onUpdateUserTurn: (turnIndex: number, message: string) => void;
  onSendMessage: (
    message: string,
    attachments?: ChatAttachment[],
    options?: {
      citationMode?: string;
      useMindmap?: boolean;
      agentMode?: "ask" | "company_agent";
      accessMode?: "restricted" | "full_access";
    },
  ) => Promise<void>;
  onUploadFiles: (files: FileList) => Promise<UploadResponse>;
  isSending: boolean;
  citationMode: string;
  onCitationModeChange: (mode: string) => void;
  mindmapEnabled: boolean;
  onMindmapEnabledChange: (enabled: boolean) => void;
  onCitationClick: (citation: CitationFocus) => void;
  agentMode: "ask" | "company_agent";
  onAgentModeChange: (mode: "ask" | "company_agent") => void;
  accessMode: "restricted" | "full_access";
  onAccessModeChange: (mode: "restricted" | "full_access") => void;
  activityEvents: AgentActivityEvent[];
  isActivityStreaming: boolean;
}

type AttachmentStatus = "uploading" | "indexed" | "error";

type ComposerAttachment = {
  id: string;
  name: string;
  status: AttachmentStatus;
  message?: string;
  fileId?: string;
};

type ComposerContext =
  | {
      kind: "retry";
      text: string;
    }
  | {
      kind: "quote";
      text: string;
    };

export function ChatMain({
  onToggleInfoPanel,
  isInfoPanelOpen,
  chatTurns,
  selectedTurnIndex,
  onSelectTurn,
  onUpdateUserTurn,
  onSendMessage,
  onUploadFiles,
  isSending,
  citationMode,
  onCitationModeChange,
  mindmapEnabled,
  onMindmapEnabledChange,
  onCitationClick,
  agentMode,
  onAgentModeChange,
  accessMode,
  onAccessModeChange,
  activityEvents,
  isActivityStreaming,
}: ChatMainProps) {
  const [message, setMessage] = useState("");
  const [isCitationDropdownOpen, setIsCitationDropdownOpen] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [composerContext, setComposerContext] = useState<ComposerContext | null>(null);
  const [messageActionStatus, setMessageActionStatus] = useState("");
  const [editingTurnIndex, setEditingTurnIndex] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const statusTimerRef = useRef<number | null>(null);

  const showActionStatus = (text: string) => {
    setMessageActionStatus(text);
    if (statusTimerRef.current) {
      window.clearTimeout(statusTimerRef.current);
    }
    statusTimerRef.current = window.setTimeout(() => {
      setMessageActionStatus("");
      statusTimerRef.current = null;
    }, 2500);
  };

  useEffect(
    () => () => {
      if (statusTimerRef.current) {
        window.clearTimeout(statusTimerRef.current);
      }
    },
    [],
  );

  const submit = async () => {
    const payload = message.trim() || composerContext?.text.trim() || "";
    if (!payload || isSending) {
      return;
    }
    const turnAttachments: ChatAttachment[] = attachments
      .filter((item) => item.status !== "error")
      .map((item) => ({ name: item.name, fileId: item.fileId }));
    setMessage("");
    await onSendMessage(payload, turnAttachments, {
      citationMode,
      useMindmap: mindmapEnabled,
      agentMode,
      accessMode,
    });
    setAttachments([]);
    setComposerContext(null);
  };

  const mapTurnAttachments = (turnAttachments?: ChatAttachment[]) => {
    return (turnAttachments || []).map((attachment, idx) => ({
      id: `compose-${Date.now()}-${idx}-${attachment.name}`,
      name: attachment.name,
      status: "indexed" as const,
      fileId: attachment.fileId,
    }));
  };

  const copyPlainText = async (text: string, label: string) => {
    const value = text.trim();
    if (!value) {
      showActionStatus(`Nothing to copy from ${label}.`);
      return;
    }
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const fallback = document.createElement("textarea");
        fallback.value = value;
        fallback.style.position = "fixed";
        fallback.style.opacity = "0";
        document.body.appendChild(fallback);
        fallback.focus();
        fallback.select();
        document.execCommand("copy");
        document.body.removeChild(fallback);
      }
      showActionStatus(`${label} copied.`);
    } catch {
      showActionStatus(`Unable to copy ${label.toLowerCase()}.`);
    }
  };

  const beginInlineEdit = (turn: ChatTurn, turnIndex: number) => {
    setEditingTurnIndex(turnIndex);
    setEditingText(turn.user);
    showActionStatus("Editing message inline.");
  };

  const cancelInlineEdit = () => {
    setEditingTurnIndex(null);
    setEditingText("");
  };

  const saveInlineEdit = async () => {
    if (editingTurnIndex === null) {
      return;
    }
    if (isSending) {
      return;
    }
    const value = editingText.trim();
    if (!value) {
      showActionStatus("Message cannot be empty.");
      return;
    }
    const editedTurn = chatTurns[editingTurnIndex];
    onUpdateUserTurn(editingTurnIndex, value);
    setEditingTurnIndex(null);
    setEditingText("");
    showActionStatus("Message updated. Generating response...");
    await onSendMessage(value, editedTurn?.attachments, {
      citationMode,
      useMindmap: mindmapEnabled,
      agentMode,
      accessMode,
    });
  };

  const retryTurn = (turn: ChatTurn) => {
    setComposerContext({
      kind: "retry",
      text: turn.user,
    });
    setMessage("");
    setAttachments(mapTurnAttachments(turn.attachments));
    showActionStatus("Retry prompt added above the chat bar.");
  };

  const quoteAssistant = (turn: ChatTurn) => {
    const quoteSource = turn.assistant.replace(/\s+/g, " ").trim();
    if (!quoteSource) {
      return;
    }
    setComposerContext({
      kind: "quote",
      text: quoteSource.slice(0, 350),
    });
    showActionStatus("Quoted answer in composer.");
  };

  const stopBubbleAction = (event: ReactMouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
  };

  const onFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = event.target.files;
    if (!selectedFiles || !selectedFiles.length) {
      return;
    }

    const pending = Array.from(selectedFiles).map((file, idx) => ({
      id: `${Date.now()}-${idx}-${file.name}`,
      name: file.name,
      status: "uploading" as const,
    }));
    setAttachments((prev) => [...prev, ...pending]);

    setIsUploading(true);
    try {
      const response = await onUploadFiles(selectedFiles);
      let successCursor = 0;
      setAttachments((prev) =>
        prev.map((attachment) => {
          const pendingIdx = pending.findIndex((item) => item.id === attachment.id);
          if (pendingIdx === -1) {
            return attachment;
          }
          const item = response.items[pendingIdx];
          if (item?.status === "success") {
            const mappedFileId = item.file_id || response.file_ids[successCursor] || undefined;
            successCursor += 1;
            return {
              ...attachment,
              status: "indexed",
              message: undefined,
              fileId: mappedFileId,
            };
          }
          return {
            ...attachment,
            status: "error",
            message: item?.message || response.errors[0] || "Upload failed.",
          };
        }),
      );
    } catch (error) {
      setAttachments((prev) =>
        prev.map((attachment) =>
          pending.some((item) => item.id === attachment.id)
            ? {
                ...attachment,
                status: "error",
                message: String(error),
              }
            : attachment,
        ),
      );
    } finally {
      setIsUploading(false);
      event.target.value = "";
    }
  };

  const handleTurnClick = (
    event: ReactMouseEvent<HTMLDivElement>,
    turn: ChatTurn,
    index: number,
  ) => {
    const target = event.target as HTMLElement;
    const citationAnchor = target.closest("a.citation") as HTMLAnchorElement | null;
    if (citationAnchor) {
      event.preventDefault();
      event.stopPropagation();
      onSelectTurn(index);

      const href = citationAnchor.getAttribute("href") || "";
      const evidenceId = href.startsWith("#") ? href.slice(1) : "";
      const evidenceCards = parseEvidence(turn.info || "");
      const matchedEvidence = evidenceCards.find((card) => card.id === evidenceId) || null;
      const fileIdAttr = citationAnchor.getAttribute("data-file-id") || "";
      const pageAttr = citationAnchor.getAttribute("data-page") || "";
      const sourceName = (matchedEvidence?.source || "Indexed source").replace(
        /^\[\d+\]\s*/,
        "",
      );

      onCitationClick({
        fileId: fileIdAttr || matchedEvidence?.fileId,
        sourceName,
        page: pageAttr || matchedEvidence?.page,
        extract: matchedEvidence?.extract || "No extract available for this citation.",
        evidenceId: evidenceId || undefined,
      });
      return;
    }
    onSelectTurn(index);
  };

  return (
    <div className="flex-1 min-h-0 min-w-0 flex flex-col bg-white overflow-hidden">
      <div className="flex-1 px-6 py-6 overflow-y-auto">
        {chatTurns.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center">
            <div className="max-w-2xl w-full text-center space-y-3">
              <div className="w-16 h-16 bg-gradient-to-br from-[#1d1d1f] to-[#3a3a3c] rounded-2xl mx-auto mb-4 flex items-center justify-center shadow-lg">
                <svg
                  className="w-8 h-8 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                  />
                </svg>
              </div>
              <h1 className="text-[28px] tracking-tight text-[#1d1d1f]">
                This is the beginning of a new conversation.
              </h1>
              <p className="text-[15px] text-[#86868b] leading-relaxed">
                Start by uploading files or URLs from the sidebar.
              </p>
            </div>
          </div>
        ) : (
          <div className="max-w-3xl mx-auto w-full space-y-4">
            {chatTurns.map((turn, index) => {
              const isLatestTurn = index === chatTurns.length - 1;
              const turnActivityEvents =
                turn.mode === "company_agent"
                  ? isLatestTurn && activityEvents.length > 0
                    ? activityEvents
                    : turn.activityEvents || []
                  : [];
              const stageAttachment =
                (turn.attachments || []).find((attachment) => Boolean(attachment.fileId)) ||
                (turn.attachments || [])[0];

              return (
                <div
                key={`${turn.user}-${index}`}
                className={`space-y-2 rounded-2xl px-2 py-1 transition-colors ${
                  selectedTurnIndex === index ? "bg-[#f5f5f7]" : ""
                }`}
                onClick={(event) => handleTurnClick(event, turn, index)}
              >
                <div className="flex justify-end">
                  <div className="max-w-[80%] space-y-2 group">
                    <div className="flex justify-end">
                      <span className="rounded-full border border-black/[0.08] bg-white px-2 py-0.5 text-[10px] text-[#6e6e73]">
                        {turn.mode === "company_agent" ? "Company Agent" : "Ask"}
                      </span>
                    </div>
                    {turn.attachments && turn.attachments.length > 0 ? (
                      <div className="space-y-1">
                        {turn.attachments.map((attachment, attachmentIdx) => (
                          <div
                            key={`${attachment.name}-${attachmentIdx}`}
                            className="bg-white border border-black/[0.08] rounded-xl px-3 py-2 shadow-sm"
                          >
                            <div className="flex items-center gap-2">
                              <FileText className="w-3.5 h-3.5 text-[#6e6e73] shrink-0" />
                              <span className="text-[13px] text-[#1d1d1f] truncate">
                                {attachment.name}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                    <div className="rounded-2xl bg-[#1d1d1f] text-white px-4 py-3 text-[14px] leading-relaxed">
                      {editingTurnIndex === index ? (
                        <textarea
                          value={editingText}
                          onClick={(event) => {
                            event.preventDefault();
                            event.stopPropagation();
                          }}
                          onChange={(event) => setEditingText(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === "Escape") {
                              event.preventDefault();
                              cancelInlineEdit();
                              return;
                            }
                            if (
                              event.key === "Enter" &&
                              (event.ctrlKey || event.metaKey)
                            ) {
                              event.preventDefault();
                              void saveInlineEdit();
                            }
                          }}
                          className="w-full min-w-[260px] max-w-[560px] bg-transparent border-0 resize-y text-[14px] leading-relaxed text-white placeholder:text-white/60 focus:outline-none"
                          rows={3}
                        />
                      ) : (
                        turn.user
                      )}
                    </div>
                    <div className="flex justify-end gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      {editingTurnIndex === index ? (
                        <>
                          <button
                            type="button"
                            onClick={(event) => {
                              stopBubbleAction(event);
                              void saveInlineEdit();
                            }}
                            disabled={isSending}
                            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-white bg-[#1d1d1f] border border-[#1d1d1f] hover:bg-[#2e2e30] transition-colors disabled:opacity-45 disabled:cursor-not-allowed"
                            title="Save edited message"
                          >
                            <span>Save</span>
                          </button>
                          <button
                            type="button"
                            onClick={(event) => {
                              stopBubbleAction(event);
                              cancelInlineEdit();
                            }}
                            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-[#6e6e73] bg-white border border-black/[0.08] hover:text-[#1d1d1f] hover:border-black/[0.18] transition-colors"
                            title="Cancel edit"
                          >
                            <span>Cancel</span>
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={(event) => {
                            stopBubbleAction(event);
                            beginInlineEdit(turn, index);
                          }}
                          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-[#6e6e73] bg-white border border-black/[0.08] hover:text-[#1d1d1f] hover:border-black/[0.18] transition-colors"
                          title="Edit message"
                        >
                          <PenLine className="w-3 h-3" />
                          <span>Edit</span>
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={(event) => {
                          stopBubbleAction(event);
                          void copyPlainText(turn.user, "User message");
                        }}
                        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-[#6e6e73] bg-white border border-black/[0.08] hover:text-[#1d1d1f] hover:border-black/[0.18] transition-colors"
                        title="Copy message"
                      >
                        <Copy className="w-3 h-3" />
                        <span>Copy</span>
                      </button>
                    </div>
                  </div>
                </div>
                {turnActivityEvents.length > 0 ? (
                  <div className="flex justify-end">
                    <div className="w-full max-w-[90%]">
                      <AgentActivityPanel
                        events={turnActivityEvents}
                        streaming={isLatestTurn && isActivityStreaming}
                        stageAttachment={stageAttachment}
                      />
                    </div>
                  </div>
                ) : null}
                <div className="flex justify-start">
                  <div className="max-w-[90%] space-y-1.5 group">
                    <div className="rounded-2xl bg-[#f5f5f7] text-[#1d1d1f] px-4 py-3 text-[14px] leading-relaxed">
                      <div
                        className="chat-answer-html [&_p]:mb-3 [&_p:last-child]:mb-0 [&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-6 [&_h1]:text-[22px] [&_h1]:font-semibold [&_h1]:mb-3 [&_h2]:text-[20px] [&_h2]:font-semibold [&_h2]:mb-2 [&_h3]:text-[18px] [&_h3]:font-semibold [&_h3]:mb-2 [&_pre]:bg-white [&_pre]:border [&_pre]:border-black/[0.08] [&_pre]:rounded-xl [&_pre]:p-3 [&_pre]:overflow-x-auto [&_code]:font-mono [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-black/[0.08] [&_th]:bg-white [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-black/[0.08] [&_td]:px-2 [&_td]:py-1 [&_blockquote]:border-l-4 [&_blockquote]:border-[#d2d2d7] [&_blockquote]:pl-3 [&_blockquote]:text-[#515154] [&_a]:text-[#3a3a3f] hover:[&_a]:underline [&_a.citation]:inline-flex [&_a.citation]:items-center [&_a.citation]:justify-center [&_a.citation]:ml-1 [&_a.citation]:px-1.5 [&_a.citation]:py-0.5 [&_a.citation]:rounded-md [&_a.citation]:bg-[#ececf0] [&_a.citation]:text-[#2f2f34] [&_a.citation]:text-[11px] [&_a.citation]:font-medium hover:[&_a.citation]:bg-[#e4e4e8] [&_details]:my-2 [&_summary]:cursor-pointer [&_img]:max-w-full [&_img]:rounded-lg [&_mark]:bg-[#fff5b5]"
                        dangerouslySetInnerHTML={{ __html: renderRichText(turn.assistant) }}
                      />
                    </div>
                    <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        type="button"
                        onClick={(event) => {
                          stopBubbleAction(event);
                          void copyPlainText(turn.assistant, "Assistant answer");
                        }}
                        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-[#6e6e73] bg-white border border-black/[0.08] hover:text-[#1d1d1f] hover:border-black/[0.18] transition-colors"
                        title="Copy answer"
                      >
                        <Copy className="w-3 h-3" />
                        <span>Copy</span>
                      </button>
                      <button
                        type="button"
                        onClick={(event) => {
                          stopBubbleAction(event);
                          retryTurn(turn);
                        }}
                        disabled={isSending}
                        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-[#6e6e73] bg-white border border-black/[0.08] hover:text-[#1d1d1f] hover:border-black/[0.18] transition-colors disabled:opacity-45"
                        title="Stage retry prompt"
                      >
                        <RotateCcw className="w-3 h-3" />
                        <span>Retry</span>
                      </button>
                      <button
                        type="button"
                        onClick={(event) => {
                          stopBubbleAction(event);
                          quoteAssistant(turn);
                        }}
                        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-[#6e6e73] bg-white border border-black/[0.08] hover:text-[#1d1d1f] hover:border-black/[0.18] transition-colors"
                        title="Quote in composer"
                      >
                        <span>Quote</span>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="border-t border-black/[0.06] bg-white">
        <div className="max-w-3xl mx-auto px-6 py-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="inline-flex rounded-xl bg-[#f5f5f7] p-1">
              {[
                { id: "ask", label: "Ask" },
                { id: "company_agent", label: "Company Agent" },
              ].map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onAgentModeChange(item.id as "ask" | "company_agent")}
                  className={`rounded-lg px-3 py-1.5 text-[12px] transition-colors ${
                    agentMode === item.id
                      ? "bg-white text-[#1d1d1f] shadow-sm"
                      : "text-[#6e6e73] hover:text-[#1d1d1f]"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
            {agentMode === "company_agent" ? (
              <div className="inline-flex rounded-xl bg-[#f5f5f7] p-1">
                {[
                  { id: "restricted", label: "Restricted" },
                  { id: "full_access", label: "Full Access" },
                ].map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onAccessModeChange(item.id as "restricted" | "full_access")}
                    className={`rounded-lg px-3 py-1.5 text-[11px] transition-colors ${
                      accessMode === item.id
                        ? "bg-white text-[#1d1d1f] shadow-sm"
                        : "text-[#6e6e73] hover:text-[#1d1d1f]"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>

          {messageActionStatus ? (
            <p className="mb-2 text-[12px] text-[#6e6e73]">{messageActionStatus}</p>
          ) : null}

          <div className="relative mb-3">
            <div className="bg-[#f5f5f7] rounded-2xl p-3 focus-within:ring-2 focus-within:ring-black/10 transition-all">
              {composerContext ? (
                <div className="mb-2 flex items-center gap-2 overflow-hidden rounded-xl border border-black/[0.08] bg-white px-2.5 py-2 shadow-sm">
                  <div className="shrink-0 rounded-md bg-[#f5f5f7] p-1">
                    {composerContext.kind === "retry" ? (
                      <RotateCcw className="w-3.5 h-3.5 text-[#6e6e73]" />
                    ) : (
                      <FileText className="w-3.5 h-3.5 text-[#6e6e73]" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] text-[#86868b]">
                      {composerContext.kind === "retry" ? "Retry prompt" : "Quoted answer"}
                    </p>
                    <p className="text-[13px] text-[#1d1d1f] truncate">
                      {`> ${composerContext.text}`}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setComposerContext(null)}
                    className="shrink-0 p-1 rounded-md hover:bg-black/5 transition-colors"
                    title="Remove prompt"
                  >
                    <X className="w-3.5 h-3.5 text-[#86868b]" />
                  </button>
                </div>
              ) : null}

              {attachments.length > 0 ? (
                <div className="mb-2 flex items-center gap-2 overflow-x-auto py-1">
                  {attachments.map((attachment) => (
                    <div
                      key={attachment.id}
                      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white border border-black/[0.08] shadow-sm min-w-0"
                      title={attachment.message || attachment.name}
                    >
                      <FileText className="w-3.5 h-3.5 text-[#6e6e73] shrink-0" />
                      <span className="text-[12px] text-[#1d1d1f] max-w-[150px] truncate">
                        {attachment.name}
                      </span>
                      {attachment.status === "uploading" ? (
                        <Loader2 className="w-3.5 h-3.5 text-[#6e6e73] animate-spin shrink-0" />
                      ) : null}
                      {attachment.status === "indexed" ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-[#1f8f4c] shrink-0" />
                      ) : null}
                      {attachment.status === "error" ? (
                        <AlertCircle className="w-3.5 h-3.5 text-[#c9342e] shrink-0" />
                      ) : null}
                      <button
                        onClick={() =>
                          setAttachments((prev) =>
                            prev.filter((item) => item.id !== attachment.id),
                          )
                        }
                        className="p-0.5 rounded hover:bg-black/5 transition-colors shrink-0"
                        aria-label={`Remove ${attachment.name}`}
                        type="button"
                      >
                        <X className="w-3 h-3 text-[#86868b]" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="flex items-end gap-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={onFileChange}
                />
                <button
                  className="p-2 hover:bg-black/5 rounded-lg transition-colors self-end disabled:opacity-40"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading || isSending}
                  title={isUploading ? "Uploading..." : "Upload files"}
                >
                  <Paperclip className="w-5 h-5 text-[#86868b]" />
                </button>

                <textarea
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder={
                    agentMode === "company_agent"
                      ? "Describe the company task: research, ads analysis, reporting, email, or invoice workflow"
                      : "Type a message, search the @web, or tag a file with @filename"
                  }
                  className="flex-1 bg-transparent border-0 resize-none text-[15px] text-[#1d1d1f] placeholder:text-[#86868b] focus:outline-none min-h-[24px] max-h-[120px] py-1"
                  rows={1}
                  onInput={(event) => {
                    const target = event.target as HTMLTextAreaElement;
                    target.style.height = "auto";
                    target.style.height = `${target.scrollHeight}px`;
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void submit();
                    }
                  }}
                />

                <button
                  className="p-2 bg-[#1d1d1f] hover:bg-[#3a3a3c] rounded-lg transition-all self-end disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
                  disabled={
                    (!message.trim() && !(composerContext?.text || "").trim()) ||
                    isSending ||
                    isUploading
                  }
                  onClick={() => void submit()}
                >
                  <Send className="w-5 h-5 text-white" />
                </button>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between text-[13px]">
            <div className="flex items-center gap-4">
              <span className="text-[#86868b]">Chat settings</span>

              <div className="relative">
                <button
                  onClick={() => setIsCitationDropdownOpen(!isCitationDropdownOpen)}
                  onBlur={() => setTimeout(() => setIsCitationDropdownOpen(false), 150)}
                  className="flex items-center gap-2 px-3 py-1.5 bg-white border border-[#e5e5e5] rounded-lg text-[#1d1d1f] hover:border-[#86868b] transition-colors"
                >
                  <span>citation: {citationMode}</span>
                  <ChevronDown
                    className={`w-3.5 h-3.5 text-[#86868b] transition-transform ${
                      isCitationDropdownOpen ? "rotate-180" : ""
                    }`}
                  />
                </button>

                {isCitationDropdownOpen && (
                  <div className="absolute top-full left-0 mt-1 w-[180px] bg-white border border-[#e5e5e5] rounded-lg shadow-lg overflow-hidden z-10">
                    {["highlight", "footnote", "inline"].map((mode) => (
                      <button
                        key={mode}
                        onClick={() => {
                          onCitationModeChange(mode);
                          setIsCitationDropdownOpen(false);
                        }}
                        className={`w-full px-3 py-2 text-left text-[13px] transition-colors ${
                          citationMode === mode
                            ? "bg-[#1d1d1f] text-white"
                            : "text-[#1d1d1f] hover:bg-[#f5f5f7]"
                        }`}
                      >
                        citation: {mode}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={mindmapEnabled}
                  onChange={(event) => onMindmapEnabledChange(event.target.checked)}
                  className="w-4 h-4 rounded border-black/[0.2] text-[#1d1d1f] focus:ring-2 focus:ring-black/10"
                />
                <span className="text-[#1d1d1f]">
                  Mindmap ({mindmapEnabled ? "on" : "off"})
                </span>
              </label>

              <button
                onClick={onToggleInfoPanel}
                className="p-1.5 rounded-lg hover:bg-black/5 transition-colors"
              >
                {isInfoPanelOpen ? (
                  <Minimize2 className="w-4 h-4 text-[#86868b]" />
                ) : (
                  <Maximize2 className="w-4 h-4 text-[#86868b]" />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
