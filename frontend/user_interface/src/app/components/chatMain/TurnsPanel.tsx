import { type MouseEvent as ReactMouseEvent, useEffect, useRef, useState } from "react";
import type { AgentActivityEvent, ChatTurn, CitationFocus } from "../../types";
import type { EvidenceCard } from "../../utils/infoInsights";
import { FilePreviewModal } from "./shared/FilePreviewModal";
import { CitationPreviewTooltip } from "./turns/CitationPreviewTooltip";
import { TurnListItem, type TurnCopyFeedback } from "./turns/TurnListItem";
import { useCitationPreview } from "./turns/useCitationPreview";
import type { FilePreviewAttachment } from "./types";

type TurnsPanelProps = {
  activityEvents: AgentActivityEvent[];
  beginInlineEdit: (turn: ChatTurn, turnIndex: number) => void;
  cancelInlineEdit: () => void;
  chatTurns: ChatTurn[];
  copyPlainText: (text: string, label: string) => Promise<boolean>;
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
  citationFocus?: CitationFocus | null;
};

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
  citationFocus = null,
}: TurnsPanelProps) {
  const turnsRootRef = useRef<HTMLDivElement | null>(null);
  const evidenceCacheRef = useRef<Map<number, { info: string; cards: EvidenceCard[] }>>(new Map());
  const copyFeedbackTimerRef = useRef<number | null>(null);
  const editFeedbackTimerRef = useRef<number | null>(null);
  const [previewAttachment, setPreviewAttachment] = useState<FilePreviewAttachment | null>(null);
  const [citationPreview, setCitationPreview] = useState<{
    left: number;
    top: number;
    width: number;
    placeAbove: boolean;
    sourceName: string;
    page?: string;
    extract: string;
    strengthLabel?: string;
    citationRef?: string;
  } | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<TurnCopyFeedback>(null);
  const [editingFeedbackTurnIndex, setEditingFeedbackTurnIndex] = useState<number | null>(null);

  useEffect(
    () => () => {
      if (copyFeedbackTimerRef.current) {
        window.clearTimeout(copyFeedbackTimerRef.current);
      }
      if (editFeedbackTimerRef.current) {
        window.clearTimeout(editFeedbackTimerRef.current);
      }
    },
    [],
  );

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

  useCitationPreview({
    chatTurns,
    turnsRootRef,
    evidenceCacheRef,
    setCitationPreview,
  });

  const showCopyFeedback = (key: string, status: "success" | "error") => {
    setCopyFeedback({ key, status });
    if (copyFeedbackTimerRef.current) {
      window.clearTimeout(copyFeedbackTimerRef.current);
    }
    copyFeedbackTimerRef.current = window.setTimeout(() => {
      setCopyFeedback((current) => (current?.key === key ? null : current));
      copyFeedbackTimerRef.current = null;
    }, 1400);
  };

  const showEditingFeedback = (turnIndex: number) => {
    setEditingFeedbackTurnIndex(turnIndex);
    if (editFeedbackTimerRef.current) {
      window.clearTimeout(editFeedbackTimerRef.current);
    }
    editFeedbackTimerRef.current = window.setTimeout(() => {
      setEditingFeedbackTurnIndex((current) => (current === turnIndex ? null : current));
      editFeedbackTimerRef.current = null;
    }, 1200);
  };

  return (
    <div ref={turnsRootRef} className="mx-auto w-full max-w-[1800px] space-y-4">
      {chatTurns.map((turn, index) => (
        <TurnListItem
          key={`${turn.user}-${index}`}
          turn={turn}
          index={index}
          selected={selectedTurnIndex === index}
          citationFocus={citationFocus}
          isLatestTurn={index === chatTurns.length - 1}
          isActivityStreaming={isActivityStreaming}
          activityEvents={activityEvents}
          isSending={isSending}
          editingTurnIndex={editingTurnIndex}
          editingText={editingText}
          editingFeedbackTurnIndex={editingFeedbackTurnIndex}
          copyFeedback={copyFeedback}
          onTurnClick={onTurnClick}
          onSetEditingText={setEditingText}
          onBeginInlineEdit={beginInlineEdit}
          onCancelInlineEdit={cancelInlineEdit}
          onSaveInlineEdit={saveInlineEdit}
          onShowEditingFeedback={showEditingFeedback}
          onCopyPlainText={copyPlainText}
          onShowCopyFeedback={showCopyFeedback}
          onRetryTurn={retryTurn}
          onQuoteAssistant={quoteAssistant}
          onOpenPreviewAttachment={setPreviewAttachment}
        />
      ))}

      <CitationPreviewTooltip preview={citationPreview} />

      <FilePreviewModal
        attachment={previewAttachment}
        onClose={() => setPreviewAttachment(null)}
        emptyPreviewMessage="Preview unavailable for this file."
      />
    </div>
  );
}

export { TurnsPanel };
