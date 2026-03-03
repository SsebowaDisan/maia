import { type MouseEvent as ReactMouseEvent } from "react";
import type { ChatTurn } from "../../types";
import type { CitationHighlightBox } from "../../types";
import { parseEvidence } from "../../utils/infoInsights";
import { ComposerPanel } from "./ComposerPanel";
import { EmptyState } from "./EmptyState";
import type { ChatMainProps } from "./types";
import { TurnsPanel } from "./TurnsPanel";
import { useChatMainInteractions } from "./useChatMainInteractions";

function normalizePageLabel(...candidates: Array<string | undefined | null>): string | undefined {
  for (const candidate of candidates) {
    const raw = String(candidate || "").trim();
    if (!raw) {
      continue;
    }
    const match = raw.match(/(\d{1,4})/);
    if (match?.[1]) {
      return match[1];
    }
  }
  return undefined;
}

function normalizeCitationExtract(...candidates: Array<string | undefined | null>): string {
  const MAX_EXTRACT_CHARS = 260;
  for (const candidate of candidates) {
    const raw = String(candidate || "").replace(/\s+/g, " ").trim();
    if (!raw) {
      continue;
    }
    if (/^\[\d{1,4}\]$/.test(raw)) {
      continue;
    }
    if (raw.length <= MAX_EXTRACT_CHARS) {
      return raw;
    }
    const clipped = raw.slice(0, MAX_EXTRACT_CHARS);
    const sentenceCut = Math.max(clipped.lastIndexOf("."), clipped.lastIndexOf("!"), clipped.lastIndexOf("?"));
    if (sentenceCut >= 120) {
      return clipped.slice(0, sentenceCut + 1).trim();
    }
    const wordCut = clipped.lastIndexOf(" ");
    if (wordCut >= 120) {
      return clipped.slice(0, wordCut).trim();
    }
    return clipped.trim();
  }
  return "No extract available for this citation.";
}

function parseHighlightBoxes(...candidates: Array<string | undefined | null>): CitationHighlightBox[] {
  const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
  for (const candidate of candidates) {
    const raw = String(candidate || "").trim();
    if (!raw) {
      continue;
    }
    try {
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        continue;
      }
      const boxes: CitationHighlightBox[] = [];
      for (const row of parsed) {
        if (!row || typeof row !== "object") {
          continue;
        }
        const x = Number((row as Record<string, unknown>).x);
        const y = Number((row as Record<string, unknown>).y);
        const width = Number((row as Record<string, unknown>).width);
        const height = Number((row as Record<string, unknown>).height);
        if (![x, y, width, height].every((value) => Number.isFinite(value))) {
          continue;
        }
        const nx = clamp01(x);
        const ny = clamp01(y);
        const nw = Math.max(0, Math.min(1 - nx, width));
        const nh = Math.max(0, Math.min(1 - ny, height));
        if (nw < 0.002 || nh < 0.002) {
          continue;
        }
        boxes.push({
          x: Number(nx.toFixed(6)),
          y: Number(ny.toFixed(6)),
          width: Number(nw.toFixed(6)),
          height: Number(nh.toFixed(6)),
        });
        if (boxes.length >= 24) {
          break;
        }
      }
      if (boxes.length) {
        return boxes;
      }
    } catch {
      // Ignore malformed payloads and continue with other candidates.
    }
  }
  return [];
}

function ChatMain({
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
  const interactions = useChatMainInteractions({
    accessMode,
    activityEvents,
    agentMode,
    chatTurns,
    citationMode,
    isSending,
    onAccessModeChange,
    onAgentModeChange,
    onSendMessage,
    onUpdateUserTurn,
    onUploadFiles,
  });

  const handleTurnClick = (
    event: ReactMouseEvent<HTMLDivElement>,
    turn: ChatTurn,
    index: number,
  ) => {
    const target = event.target as HTMLElement;
    const citationAnchor = target.closest(
      "a.citation, a[href^='#evidence-'], a[data-file-id]",
    ) as HTMLAnchorElement | null;
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
      const phraseAttr =
        citationAnchor.getAttribute("data-phrase") ||
        citationAnchor.getAttribute("data-search") ||
        "";
      const boxesAttr = citationAnchor.getAttribute("data-boxes") || "";
      const attachmentFileId =
        (turn.attachments || []).find((attachment) => Boolean(attachment.fileId))?.fileId || "";
      const sourceName = (matchedEvidence?.source || "Indexed source").replace(
        /^\[\d+\]\s*/,
        "",
      );
      const highlightBoxes = parseHighlightBoxes(
        boxesAttr,
        JSON.stringify(matchedEvidence?.highlightBoxes || []),
      );

      onCitationClick({
        fileId: fileIdAttr || matchedEvidence?.fileId || attachmentFileId,
        sourceName,
        page: normalizePageLabel(pageAttr, matchedEvidence?.page),
        extract: normalizeCitationExtract(
          phraseAttr,
          matchedEvidence?.extract,
          citationAnchor.textContent?.trim(),
        ),
        evidenceId: evidenceId || undefined,
        highlightBoxes: highlightBoxes.length ? highlightBoxes : undefined,
      });
      return;
    }
    onSelectTurn(index);
  };

  return (
    <div className="flex-1 min-h-0 min-w-0 flex flex-col bg-white overflow-hidden">
      <div className="flex-1 px-6 py-6 overflow-y-auto">
        {chatTurns.length === 0 ? (
          <EmptyState />
        ) : (
          <TurnsPanel
            activityEvents={activityEvents}
            beginInlineEdit={interactions.beginInlineEdit}
            cancelInlineEdit={interactions.cancelInlineEdit}
            chatTurns={chatTurns}
            copyPlainText={interactions.copyPlainText}
            editingText={interactions.editingText}
            editingTurnIndex={interactions.editingTurnIndex}
            isActivityStreaming={isActivityStreaming}
            isSending={isSending}
            onTurnClick={handleTurnClick}
            quoteAssistant={interactions.quoteAssistant}
            retryTurn={interactions.retryTurn}
            saveInlineEdit={interactions.saveInlineEdit}
            selectedTurnIndex={selectedTurnIndex}
            setEditingText={interactions.setEditingText}
          />
        )}
      </div>

      <ComposerPanel
        accessMode={accessMode}
        agentControlsVisible={interactions.agentControlsVisible}
        agentMode={agentMode}
        attachments={interactions.attachments}
        clearAttachments={interactions.clearAttachments}
        removeAttachment={interactions.removeAttachment}
        enableAgentMode={interactions.enableAgentMode}
        enableDeepResearch={interactions.enableDeepResearch}
        fileInputRef={interactions.fileInputRef}
        isSending={isSending}
        isUploading={interactions.isUploading}
        latestHighlightSnippets={interactions.latestHighlightSnippets}
        message={interactions.message}
        messageActionStatus={interactions.messageActionStatus}
        onAccessModeChange={onAccessModeChange}
        onFileChange={interactions.onFileChange}
        pasteHighlightsToComposer={interactions.pasteHighlightsToComposer}
        setMessage={interactions.setMessage}
        submit={interactions.submit}
      />
    </div>
  );
}

export { ChatMain };
