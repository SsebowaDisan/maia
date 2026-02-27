import {
  type ChangeEvent,
  type MouseEvent as ReactMouseEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Copy,
  FileText,
  PenLine,
  RotateCcw,
  Send,
  X,
} from "lucide-react";
import type { AgentActivityEvent, ChatAttachment, ChatTurn, CitationFocus } from "../types";
import type { UploadResponse } from "../../api/client";
import { renderRichText } from "../utils/richText";
import { parseEvidence } from "../utils/infoInsights";
import { AccessModeDropdown } from "./AccessModeDropdown";
import { AgentActivityPanel } from "./AgentActivityPanel";
import { ComposerQuickActionsCard } from "./ComposerQuickActionsCard";

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

export function ChatMain({
  chatTurns,
  selectedTurnIndex,
  onSelectTurn,
  onUpdateUserTurn,
  onSendMessage,
  onUploadFiles,
  isSending,
  citationMode,
  onCitationClick,
  agentMode,
  onAgentModeChange,
  accessMode,
  onAccessModeChange,
  activityEvents,
  isActivityStreaming,
}: ChatMainProps) {
  const [message, setMessage] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [agentControlsVisible, setAgentControlsVisible] = useState(false);
  const [messageActionStatus, setMessageActionStatus] = useState("");
  const [editingTurnIndex, setEditingTurnIndex] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const statusTimerRef = useRef<number | null>(null);
  const lastClipboardEventRef = useRef<string>("");

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
    const payload = message.trim();
    if (!payload || isSending) {
      return;
    }
    const turnAttachments: ChatAttachment[] = attachments
      .filter((item) => item.status !== "error")
      .map((item) => ({ name: item.name, fileId: item.fileId }));
    setMessage("");
    await onSendMessage(payload, turnAttachments, {
      citationMode,
      useMindmap: false,
      agentMode,
      accessMode,
    });
    setAttachments([]);
  };

  const latestHighlightSnippets = useMemo(() => {
    const snippets: string[] = [];
    for (let index = activityEvents.length - 1; index >= 0; index -= 1) {
      const event = activityEvents[index];
      const copied = event.data?.["copied_snippets"];
      if (Array.isArray(copied)) {
        for (const row of copied) {
          const text = String(row || "").trim();
          if (text && !snippets.includes(text)) {
            snippets.push(text);
          }
          if (snippets.length >= 8) {
            return snippets;
          }
        }
      }
      const clipboardText =
        typeof event.data?.["clipboard_text"] === "string"
          ? event.data["clipboard_text"].trim()
          : "";
      if (clipboardText && !snippets.includes(clipboardText)) {
        snippets.push(clipboardText);
      }
      if (snippets.length >= 8) {
        return snippets;
      }
    }
    return snippets;
  }, [activityEvents]);

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
      useMindmap: false,
      agentMode,
      accessMode,
    });
  };

  const retryTurn = (turn: ChatTurn) => {
    setMessage(turn.user);
    setAttachments(mapTurnAttachments(turn.attachments));
    showActionStatus("Retry prompt loaded into the command bar.");
  };

  const enableAgentMode = () => {
    setAgentControlsVisible(true);
    onAgentModeChange("company_agent");
    showActionStatus("Agent mode enabled.");
  };

  const enableDeepResearch = () => {
    setAgentControlsVisible(false);
    onAgentModeChange("ask");
    onAccessModeChange("restricted");
    showActionStatus("Deep research enabled in Ask mode.");
  };

  const pasteHighlightsToComposer = () => {
    if (!latestHighlightSnippets.length) {
      showActionStatus("No copied highlights available yet.");
      return;
    }
    const block = [
      "Copied highlights:",
      ...latestHighlightSnippets.slice(0, 6).map((snippet) => `- ${snippet}`),
    ].join("\n");
    setMessage((previous) => {
      const current = previous.trim();
      return current ? `${current}\n\n${block}` : block;
    });
    showActionStatus("Highlights pasted into the command bar.");
  };

  const quoteAssistant = (turn: ChatTurn) => {
    const quoteSource = turn.assistant.replace(/\s+/g, " ").trim();
    if (!quoteSource) {
      return;
    }
    const quoted = `> ${quoteSource.slice(0, 350)}`;
    setMessage((previous) => {
      const base = previous.trim();
      return base ? `${base}\n${quoted}` : quoted;
    });
    showActionStatus("Quoted answer loaded into the command bar.");
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

  useEffect(() => {
    if (!activityEvents.length) {
      return;
    }
    const latest = activityEvents[activityEvents.length - 1];
    if (!latest?.event_id || latest.event_id === lastClipboardEventRef.current) {
      return;
    }
    if (
      latest.event_type === "highlights_detected" ||
      latest.event_type === "doc_copy_clipboard" ||
      latest.event_type === "browser_copy_selection"
    ) {
      lastClipboardEventRef.current = latest.event_id;
      showActionStatus("Highlights copied. Use + -> Paste highlights.");
    }
  }, [activityEvents]);

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
          <div className="mx-auto w-full max-w-[1800px] space-y-4">
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
              const hasAssistantOutput = Boolean(String(turn.assistant || "").trim());

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
                        {turn.mode === "company_agent" ? "Agent" : "Ask"}
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
                {hasAssistantOutput ? (
                  <div className="flex justify-start">
                    <div className="max-w-[90%] space-y-1.5 group">
                      <div className="rounded-2xl border border-black/[0.06] bg-white px-4 py-3 text-[14px] leading-relaxed text-[#1d1d1f] shadow-[0_10px_28px_-22px_rgba(0,0,0,0.35)]">
                        <div
                          className="chat-answer-html [&_p]:mb-3 [&_p]:leading-[1.7] [&_p:last-child]:mb-0 [&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-6 [&_h1]:mb-3 [&_h1]:text-[24px] [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:text-[20px] [&_h2]:font-semibold [&_h3]:mb-2 [&_h3]:text-[17px] [&_h3]:font-semibold [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-black/[0.08] [&_pre]:bg-[#f7f7f9] [&_pre]:p-3 [&_code]:font-mono [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-black/[0.08] [&_th]:bg-[#f7f7f9] [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-black/[0.08] [&_td]:px-2 [&_td]:py-1 [&_blockquote]:border-l-4 [&_blockquote]:border-[#d2d2d7] [&_blockquote]:pl-3 [&_blockquote]:text-[#515154] [&_a]:text-[#0a66d9] hover:[&_a]:underline [&_a.citation]:ml-1 [&_a.citation]:inline-flex [&_a.citation]:items-center [&_a.citation]:justify-center [&_a.citation]:rounded-md [&_a.citation]:bg-[#ececf0] [&_a.citation]:px-1.5 [&_a.citation]:py-0.5 [&_a.citation]:text-[11px] [&_a.citation]:font-medium [&_a.citation]:text-[#2f2f34] hover:[&_a.citation]:bg-[#e4e4e8] [&_details]:my-2 [&_summary]:cursor-pointer [&_img]:max-w-full [&_img]:rounded-lg [&_mark]:bg-[#fff5b5]"
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
                ) : null}
              </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="border-t border-black/[0.06] bg-white">
        <div className="mx-auto w-full max-w-[1800px] px-6 py-4">
          <div className="assistantComposer rounded-[22px] border border-black/[0.08] bg-[#f3f3f5]">
            <div className="assistantComposerInputShell rounded-[14px] border border-black/[0.08] bg-white">
              <input
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                placeholder="Ask for follow-up changes"
                className="assistantComposerInput min-w-0 flex-1 border-0 bg-transparent text-[15px] text-[#1d1d1f] placeholder:text-[#86868b] focus:outline-none"
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void submit();
                  }
                }}
              />
            </div>

            <div className="assistantComposerToolbar">
              <div className="assistantComposerTools">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={onFileChange}
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

                {attachments.length > 0 ? (
                  <button
                    type="button"
                    onClick={() => setAttachments([])}
                    className="inline-flex h-7 items-center gap-1 rounded-full border border-black/[0.08] bg-white px-2 text-[11px] text-[#1d1d1f]"
                    title="Clear attached files"
                  >
                    <span>{attachments.length}</span>
                    <X className="h-3 w-3 text-[#86868b]" />
                  </button>
                ) : null}
              </div>

              <div className="assistantComposerActions">
                <button
                  type="button"
                  className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-black/[0.08] bg-[#a4a4aa] text-white shadow-[0_6px_14px_-12px_rgba(0,0,0,0.45)] transition-colors duration-150 hover:bg-[#98989e] disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={!message.trim() || isSending || isUploading}
                  onClick={() => void submit()}
                  aria-label="Send message"
                  title="Send"
                >
                  <Send className="h-4.5 w-4.5" />
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
      </div>
    </div>
  );
}
