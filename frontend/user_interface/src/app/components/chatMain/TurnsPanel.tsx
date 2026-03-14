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
  onTurnAuxClick: (event: ReactMouseEvent<HTMLDivElement>, turn: ChatTurn, index: number) => void;
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
  onTurnAuxClick,
  quoteAssistant,
  retryTurn,
  saveInlineEdit,
  selectedTurnIndex,
  setEditingText,
  citationFocus = null,
}: TurnsPanelProps) {
  const turnsRootRef = useRef<HTMLDivElement | null>(null);
  const pendingTheatreCenterTurnRef = useRef<number | null>(null);
  const centeredTurnFallbackRef = useRef<number | null>(null);
  const centeredTheatreAnchorRef = useRef<number | null>(null);
  const previousTurnCountRef = useRef<number>(chatTurns.length);
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

  const latestTurnIndex = chatTurns.length > 0 ? chatTurns.length - 1 : null;
  const latestAssistantLength =
    latestTurnIndex === null
      ? 0
      : String(chatTurns[latestTurnIndex]?.assistant || "").trim().length;
  const latestTurnMode = latestTurnIndex === null ? null : chatTurns[latestTurnIndex]?.mode || null;
  const latestTurnUsesTheatre =
    latestTurnMode === "company_agent" ||
    latestTurnMode === "deep_search" ||
    latestTurnMode === "web_search";

  const queueTheatreCenter = (turnIndex: number) => {
    pendingTheatreCenterTurnRef.current = turnIndex;
    centeredTurnFallbackRef.current = null;
    centeredTheatreAnchorRef.current = null;
  };

  const scheduleCenteredScroll = (target: HTMLElement) => {
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false);
    const behavior: ScrollBehavior = prefersReducedMotion ? "auto" : "smooth";
    const rafId = window.requestAnimationFrame(() => {
      target.scrollIntoView({ behavior, block: "start", inline: "nearest" });
    });
    return () => window.cancelAnimationFrame(rafId);
  };

  useEffect(() => {
    if (!isSending || latestTurnIndex === null) {
      return;
    }
    queueTheatreCenter(latestTurnIndex);
  }, [isSending, latestTurnIndex]);

  useEffect(() => {
    const previousCount = previousTurnCountRef.current;
    const currentCount = chatTurns.length;
    previousTurnCountRef.current = currentCount;

    if (latestTurnIndex === null || currentCount <= previousCount) {
      return;
    }

    // Covers modes where the newest turn is appended after send settles (e.g. web search).
    if (!isSending && !isActivityStreaming && previousCount <= 0) {
      return;
    }

    queueTheatreCenter(latestTurnIndex);
  }, [chatTurns.length, isSending, isActivityStreaming, latestTurnIndex]);

  useEffect(() => {
    if (latestTurnIndex === null) {
      pendingTheatreCenterTurnRef.current = null;
      return;
    }
    if (pendingTheatreCenterTurnRef.current !== null && pendingTheatreCenterTurnRef.current !== latestTurnIndex) {
      pendingTheatreCenterTurnRef.current = null;
      return;
    }
    if (pendingTheatreCenterTurnRef.current !== latestTurnIndex) {
      return;
    }

    const theatreAnchor =
      turnsRootRef.current?.querySelector<HTMLElement>("[data-theatre-anchor='true']") || null;
    const latestTurnNode =
      turnsRootRef.current?.querySelector<HTMLElement>(
        `[data-turn-index="${String(latestTurnIndex)}"]`,
      ) || null;

    if (!theatreAnchor && latestTurnUsesTheatre && (isSending || isActivityStreaming)) {
      return;
    }

    const target = theatreAnchor || latestTurnNode;
    if (!target) {
      return;
    }

    if (theatreAnchor) {
      if (centeredTheatreAnchorRef.current === latestTurnIndex) {
        return;
      }
      centeredTheatreAnchorRef.current = latestTurnIndex;
      pendingTheatreCenterTurnRef.current = null;
      return scheduleCenteredScroll(theatreAnchor);
    }

    if (centeredTurnFallbackRef.current === latestTurnIndex) {
      return;
    }
    centeredTurnFallbackRef.current = latestTurnIndex;
    const cleanup = scheduleCenteredScroll(target);
    return cleanup;
  }, [
    activityEvents.length,
    chatTurns.length,
    isActivityStreaming,
    isSending,
    latestAssistantLength,
    latestTurnIndex,
    latestTurnUsesTheatre,
  ]);

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
          onTurnAuxClick={onTurnAuxClick}
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
