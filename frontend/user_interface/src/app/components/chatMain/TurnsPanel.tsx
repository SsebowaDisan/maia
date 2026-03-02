import { Copy, FileText, PenLine, RotateCcw } from "lucide-react";
import { type MouseEvent as ReactMouseEvent } from "react";
import type { AgentActivityEvent, ChatTurn } from "../../types";
import { renderRichText } from "../../utils/richText";
import { AgentActivityPanel } from "../AgentActivityPanel";
import { ChatTurnPlot } from "./ChatTurnPlot";

type TurnsPanelProps = {
  activityEvents: AgentActivityEvent[];
  beginInlineEdit: (turn: ChatTurn, turnIndex: number) => void;
  cancelInlineEdit: () => void;
  chatTurns: ChatTurn[];
  copyPlainText: (text: string, label: string) => Promise<void>;
  editingText: string;
  editingTurnIndex: number | null;
  isActivityStreaming: boolean;
  isSending: boolean;
  onTurnClick: (event: ReactMouseEvent<HTMLDivElement>, turn: ChatTurn, index: number) => void;
  quoteAssistant: (turn: ChatTurn) => void;
  retryTurn: (turn: ChatTurn) => void;
  saveInlineEdit: () => Promise<void>;
  selectedTurnIndex: number | null;
  setEditingText: (value: string) => void;
};

function stopBubbleAction(event: ReactMouseEvent<HTMLButtonElement>) {
  event.preventDefault();
  event.stopPropagation();
}

function TurnsPanel({
  activityEvents,
  beginInlineEdit,
  cancelInlineEdit,
  chatTurns,
  copyPlainText,
  editingText,
  editingTurnIndex,
  isActivityStreaming,
  isSending,
  onTurnClick,
  quoteAssistant,
  retryTurn,
  saveInlineEdit,
  selectedTurnIndex,
  setEditingText,
}: TurnsPanelProps) {
  return (
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
        const hasAssistantText = Boolean(String(turn.assistant || "").trim());
        const hasAssistantOutput = hasAssistantText || Boolean(turn.plot);

        return (
          <div
            key={`${turn.user}-${index}`}
            className={`space-y-2 rounded-2xl px-2 py-1 transition-colors ${
              selectedTurnIndex === index ? "bg-[#f5f5f7]" : ""
            }`}
            onClick={(event) => onTurnClick(event, turn, index)}
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
                        if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
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
                    needsHumanReview={Boolean(turn.needsHumanReview)}
                    humanReviewNotes={turn.humanReviewNotes || null}
                  />
                </div>
              </div>
            ) : null}
            {hasAssistantOutput ? (
              <div className="flex justify-start">
                <div className="max-w-[90%] space-y-1.5 group">
                  {hasAssistantText ? (
                    <div className="rounded-2xl border border-black/[0.06] bg-white px-4 py-3 text-[14px] leading-relaxed text-[#1d1d1f] shadow-[0_10px_28px_-22px_rgba(0,0,0,0.35)]">
                      <div
                        className="chat-answer-html [&_p]:mb-3 [&_p]:leading-[1.7] [&_p:last-child]:mb-0 [&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-6 [&_h1]:mb-3 [&_h1]:text-[24px] [&_h1]:font-semibold [&_h2]:mb-2 [&_h2]:text-[20px] [&_h2]:font-semibold [&_h3]:mb-2 [&_h3]:text-[17px] [&_h3]:font-semibold [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-black/[0.08] [&_pre]:bg-[#f7f7f9] [&_pre]:p-3 [&_code]:font-mono [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-black/[0.08] [&_th]:bg-[#f7f7f9] [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-black/[0.08] [&_td]:px-2 [&_td]:py-1 [&_blockquote]:border-l-4 [&_blockquote]:border-[#d2d2d7] [&_blockquote]:pl-3 [&_blockquote]:text-[#515154] [&_a]:text-[#0a66d9] hover:[&_a]:underline [&_a.citation]:ml-1 [&_a.citation]:inline-flex [&_a.citation]:items-center [&_a.citation]:justify-center [&_a.citation]:rounded-md [&_a.citation]:bg-[#ececf0] [&_a.citation]:px-1.5 [&_a.citation]:py-0.5 [&_a.citation]:text-[11px] [&_a.citation]:font-medium [&_a.citation]:text-[#2f2f34] hover:[&_a.citation]:bg-[#e4e4e8] [&_details]:my-2 [&_summary]:cursor-pointer [&_img]:max-w-full [&_img]:rounded-lg [&_mark]:bg-[#fff5b5]"
                        dangerouslySetInnerHTML={{ __html: renderRichText(turn.assistant) }}
                      />
                    </div>
                  ) : null}
                  <ChatTurnPlot plot={turn.plot} />
                  <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    {hasAssistantText ? (
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
                    ) : null}
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
                    {hasAssistantText ? (
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
                    ) : null}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export { TurnsPanel };
