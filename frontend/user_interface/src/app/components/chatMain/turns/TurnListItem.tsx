import { Check, Copy, FileText, PenLine, RotateCcw } from "lucide-react";
import { type MouseEvent as ReactMouseEvent } from "react";
import type { AgentActivityEvent, ChatTurn, CitationFocus } from "../../../types";
import { fallbackAssistantBlocks } from "../../../messageBlocks";
import { AgentActivityPanel } from "../../AgentActivityPanel";
import { MessageBlocks } from "../../messages/MessageBlocks";
import { ChatTurnPlot } from "../ChatTurnPlot";
import type { FilePreviewAttachment } from "../types";

type TurnCopyFeedback = {
  key: string;
  status: "success" | "error";
} | null;

type TurnListItemProps = {
  turn: ChatTurn;
  index: number;
  selected: boolean;
  citationFocus: CitationFocus | null;
  isLatestTurn: boolean;
  isActivityStreaming: boolean;
  activityEvents: AgentActivityEvent[];
  isSending: boolean;
  editingTurnIndex: number | null;
  editingText: string;
  editingFeedbackTurnIndex: number | null;
  copyFeedback: TurnCopyFeedback;
  onTurnClick: (event: ReactMouseEvent<HTMLDivElement>, turn: ChatTurn, index: number) => void;
  onSetEditingText: (value: string) => void;
  onBeginInlineEdit: (turn: ChatTurn, turnIndex: number) => void;
  onCancelInlineEdit: () => void;
  onSaveInlineEdit: () => Promise<void>;
  onShowEditingFeedback: (turnIndex: number) => void;
  onCopyPlainText: (text: string, label: string) => Promise<boolean>;
  onShowCopyFeedback: (key: string, status: "success" | "error") => void;
  onRetryTurn: (turn: ChatTurn) => void;
  onQuoteAssistant: (turn: ChatTurn) => void;
  onOpenPreviewAttachment: (attachment: FilePreviewAttachment) => void;
};

function stopBubbleAction(event: ReactMouseEvent<HTMLButtonElement>) {
  event.preventDefault();
  event.stopPropagation();
}

function resolveTurnModeLabel(mode: ChatTurn["mode"]): string {
  if (mode === "web_search") {
    return "Web Search";
  }
  if (mode === "deep_search") {
    return "Deep Search";
  }
  if (mode === "company_agent") {
    return "Agent";
  }
  return "Ask";
}

function TurnListItem({
  turn,
  index,
  selected,
  citationFocus,
  isLatestTurn,
  isActivityStreaming,
  activityEvents,
  isSending,
  editingTurnIndex,
  editingText,
  editingFeedbackTurnIndex,
  copyFeedback,
  onTurnClick,
  onSetEditingText,
  onBeginInlineEdit,
  onCancelInlineEdit,
  onSaveInlineEdit,
  onShowEditingFeedback,
  onCopyPlainText,
  onShowCopyFeedback,
  onRetryTurn,
  onQuoteAssistant,
  onOpenPreviewAttachment,
}: TurnListItemProps) {
  const turnActivityEvents =
    turn.mode === "company_agent" || turn.mode === "deep_search" || turn.mode === "web_search"
      ? isLatestTurn && activityEvents.length > 0
        ? activityEvents
        : turn.activityEvents || []
      : [];
  const stageAttachment =
    (turn.attachments || []).find((attachment) => Boolean(attachment.fileId)) || (turn.attachments || [])[0];
  const assistantBlocks =
    turn.blocks && turn.blocks.length > 0
      ? turn.blocks
      : fallbackAssistantBlocks(turn.assistant);
  const hasAssistantOutput = assistantBlocks.length > 0 || Boolean(turn.plot);
  const userCopyFeedbackKey = `user-${index}`;
  const assistantCopyFeedbackKey = `assistant-${index}`;
  const userCopyFeedback = copyFeedback?.key === userCopyFeedbackKey ? copyFeedback.status : null;
  const assistantCopyFeedback = copyFeedback?.key === assistantCopyFeedbackKey ? copyFeedback.status : null;

  return (
    <div
      data-turn-index={index}
      className={`space-y-2 rounded-2xl px-2 py-1 transition-colors ${selected ? "bg-[#f5f5f7]" : ""}`}
      onClick={(event) => onTurnClick(event, turn, index)}
    >
      <div className="flex justify-end">
        <div className="group max-w-[80%] space-y-2">
          <div className="flex justify-end">
            <span className="rounded-full border border-black/[0.08] bg-white px-2 py-0.5 text-[10px] text-[#6e6e73]">
              {resolveTurnModeLabel(turn.mode)}
            </span>
          </div>
          {turn.attachments && turn.attachments.length > 0 ? (
            <div className="space-y-1">
              {turn.attachments.map((attachment, attachmentIdx) => (
                <button
                  key={`${attachment.name}-${attachmentIdx}`}
                  type="button"
                  onClick={(event) => {
                    stopBubbleAction(event);
                    onOpenPreviewAttachment({
                      name: attachment.name,
                      fileId: attachment.fileId,
                      status: "indexed",
                    });
                  }}
                  className="rounded-xl border border-black/[0.08] bg-white px-3 py-2 shadow-sm"
                  title={attachment.fileId ? "Open file preview" : "Preview unavailable"}
                >
                  <div className="flex items-center gap-2">
                    <FileText className="h-3.5 w-3.5 shrink-0 text-[#6e6e73]" />
                    <span className="truncate text-[13px] text-[#1d1d1f]">{attachment.name}</span>
                  </div>
                </button>
              ))}
            </div>
          ) : null}
          <div className="rounded-2xl bg-[#1d1d1f] px-4 py-3 text-[14px] leading-relaxed text-white">
            {editingTurnIndex === index ? (
              <textarea
                value={editingText}
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                }}
                onChange={(event) => onSetEditingText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    event.preventDefault();
                    onCancelInlineEdit();
                    return;
                  }
                  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                    event.preventDefault();
                    void onSaveInlineEdit();
                  }
                }}
                className="w-full min-w-[260px] max-w-[560px] resize-y border-0 bg-transparent text-[14px] leading-relaxed text-white placeholder:text-white/60 focus:outline-none"
                rows={3}
              />
            ) : (
              turn.user
            )}
          </div>
          <div className="flex justify-end gap-1.5 opacity-0 transition-opacity group-hover:opacity-100">
            {editingTurnIndex === index ? (
              <>
                {editingFeedbackTurnIndex === index ? (
                  <span className="inline-flex items-center gap-1 rounded-full border border-black/[0.08] bg-[#f5f5f7] px-2 py-1 text-[10px] font-medium text-[#1d1d1f]">
                    <Check className="h-3 w-3" />
                    <span>Editing</span>
                  </span>
                ) : null}
                <button
                  type="button"
                  onClick={(event) => {
                    stopBubbleAction(event);
                    void onSaveInlineEdit();
                  }}
                  disabled={isSending}
                  className="inline-flex items-center gap-1 rounded-md border border-[#1d1d1f] bg-[#1d1d1f] px-2 py-1 text-[11px] text-white transition-colors hover:bg-[#2e2e30] disabled:cursor-not-allowed disabled:opacity-45 active:scale-[0.98]"
                  title="Save edited message"
                >
                  <span>Save</span>
                </button>
                <button
                  type="button"
                  onClick={(event) => {
                    stopBubbleAction(event);
                    onCancelInlineEdit();
                  }}
                  className="inline-flex items-center gap-1 rounded-md border border-black/[0.08] bg-white px-2 py-1 text-[11px] text-[#6e6e73] transition-colors hover:border-black/[0.18] hover:text-[#1d1d1f] active:scale-[0.98]"
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
                  onShowEditingFeedback(index);
                  onBeginInlineEdit(turn, index);
                }}
                className="inline-flex items-center gap-1 rounded-md border border-black/[0.08] bg-white px-2 py-1 text-[11px] text-[#6e6e73] transition-colors hover:border-black/[0.18] hover:text-[#1d1d1f] active:scale-[0.98]"
                title="Edit message"
              >
                <PenLine className="h-3 w-3" />
                <span>Edit</span>
              </button>
            )}
            <button
              type="button"
              onClick={async (event) => {
                stopBubbleAction(event);
                const success = await onCopyPlainText(turn.user, "User message");
                onShowCopyFeedback(userCopyFeedbackKey, success ? "success" : "error");
              }}
              className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors active:scale-[0.98] ${
                userCopyFeedback === "success"
                  ? "border-[#cde7d0] bg-[#eef7ef] text-[#1f6b2b]"
                  : userCopyFeedback === "error"
                    ? "border-[#efcdcd] bg-[#fff4f4] text-[#b42323]"
                    : "border-black/[0.08] bg-white text-[#6e6e73] hover:border-black/[0.18] hover:text-[#1d1d1f]"
              }`}
              title="Copy message"
            >
              {userCopyFeedback === "success" ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              <span>
                {userCopyFeedback === "success" ? "Copied" : userCopyFeedback === "error" ? "Try again" : "Copy"}
              </span>
            </button>
          </div>
        </div>
      </div>
      {turnActivityEvents.length > 0 ? (
        <div className="flex justify-end">
          <div
            className="w-full max-w-[98%] xl:max-w-full"
            data-theatre-anchor={isLatestTurn ? "true" : undefined}
          >
            <AgentActivityPanel
              events={turnActivityEvents}
              streaming={isLatestTurn && isActivityStreaming}
              stageAttachment={stageAttachment}
              needsHumanReview={Boolean(turn.needsHumanReview)}
              humanReviewNotes={turn.humanReviewNotes || null}
              jumpTarget={
                selected && citationFocus
                  ? {
                      graphNodeIds: citationFocus.graphNodeIds || [],
                      sceneRefs: citationFocus.sceneRefs || [],
                      eventRefs: citationFocus.eventRefs || [],
                      nonce: [
                        citationFocus.evidenceId || "",
                        citationFocus.graphNodeIds?.join("|") || "",
                        citationFocus.sceneRefs?.join("|") || "",
                        citationFocus.eventRefs?.join("|") || "",
                      ].join(":"),
                    }
                  : null
              }
            />
          </div>
        </div>
      ) : null}
      {hasAssistantOutput ? (
        <div className="flex justify-start">
          <div className="group max-w-[90%] space-y-1.5">
            {assistantBlocks.length > 0 ? (
              <div className="assistantAnswerCard">
                <MessageBlocks blocks={assistantBlocks} documents={turn.documents || []} />
              </div>
            ) : null}
            <ChatTurnPlot plot={turn.plot} />
            <div className="flex items-center gap-1.5 opacity-0 transition-opacity group-hover:opacity-100">
              {assistantBlocks.length > 0 ? (
                <button
                  type="button"
                  onClick={async (event) => {
                    stopBubbleAction(event);
                    const success = await onCopyPlainText(turn.assistant, "Assistant answer");
                    onShowCopyFeedback(assistantCopyFeedbackKey, success ? "success" : "error");
                  }}
                  className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] transition-colors active:scale-[0.98] ${
                    assistantCopyFeedback === "success"
                      ? "border-[#cde7d0] bg-[#eef7ef] text-[#1f6b2b]"
                      : assistantCopyFeedback === "error"
                        ? "border-[#efcdcd] bg-[#fff4f4] text-[#b42323]"
                        : "border-black/[0.08] bg-white text-[#6e6e73] hover:border-black/[0.18] hover:text-[#1d1d1f]"
                  }`}
                  title="Copy answer"
                >
                  {assistantCopyFeedback === "success" ? (
                    <Check className="h-3 w-3" />
                  ) : (
                    <Copy className="h-3 w-3" />
                  )}
                  <span>
                    {assistantCopyFeedback === "success"
                      ? "Copied"
                      : assistantCopyFeedback === "error"
                        ? "Try again"
                        : "Copy"}
                  </span>
                </button>
              ) : null}
              <button
                type="button"
                onClick={(event) => {
                  stopBubbleAction(event);
                  onRetryTurn(turn);
                }}
                disabled={isSending}
                className="inline-flex items-center gap-1 rounded-md border border-black/[0.08] bg-white px-2 py-1 text-[11px] text-[#6e6e73] transition-colors hover:border-black/[0.18] hover:text-[#1d1d1f] disabled:opacity-45"
                title="Stage retry prompt"
              >
                <RotateCcw className="h-3 w-3" />
                <span>Retry</span>
              </button>
              {assistantBlocks.length > 0 ? (
                <button
                  type="button"
                  onClick={(event) => {
                    stopBubbleAction(event);
                    onQuoteAssistant(turn);
                  }}
                  className="inline-flex items-center gap-1 rounded-md border border-black/[0.08] bg-white px-2 py-1 text-[11px] text-[#6e6e73] transition-colors hover:border-black/[0.18] hover:text-[#1d1d1f]"
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
}

export type { TurnCopyFeedback };
export { TurnListItem };
