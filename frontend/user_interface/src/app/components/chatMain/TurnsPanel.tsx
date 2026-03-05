import { Copy, ExternalLink, FileText, PenLine, RotateCcw, X } from "lucide-react";
import { type MouseEvent as ReactMouseEvent, useEffect, useMemo, useRef, useState } from "react";
import { buildRawFileUrl } from "../../../api/client";
import type { AgentActivityEvent, ChatTurn } from "../../types";
import { parseEvidence } from "../../utils/infoInsights";
import type { EvidenceCard } from "../../utils/infoInsights";
import { renderRichText } from "../../utils/richText";
import { AgentActivityPanel } from "../AgentActivityPanel";
import {
  CITATION_ANCHOR_SELECTOR,
  resolveCitationFocusFromAnchor,
  resolveStrengthTier,
} from "./citationFocus";
import { ChatTurnPlot } from "./ChatTurnPlot";
import type { FilePreviewAttachment } from "./types";

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

type CitationPreview = {
  left: number;
  top: number;
  width: number;
  placeAbove: boolean;
  sourceName: string;
  page?: string;
  extract: string;
  strengthLabel?: string;
  citationRef?: string;
};

function strengthTierLabel(tier: number): string {
  if (tier >= 3) {
    return "Strong evidence";
  }
  if (tier >= 2) {
    return "Moderate evidence";
  }
  if (tier >= 1) {
    return "Supporting evidence";
  }
  return "";
}

function formatPreviewExtract(raw: string): string {
  const compact = String(raw || "").replace(/\s+/g, " ").trim();
  if (!compact) {
    return "No extract available for this citation.";
  }
  const unquoted = compact.replace(/^[“"'`]+/, "").replace(/[”"'`]+$/, "").trim();
  const text = unquoted || compact;
  if (text.length <= 260) {
    return text;
  }
  const clipped = text.slice(0, 260);
  const wordCut = clipped.lastIndexOf(" ");
  return `${(wordCut >= 140 ? clipped.slice(0, wordCut) : clipped).trim()}…`;
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
  const turnsRootRef = useRef<HTMLDivElement | null>(null);
  const evidenceCacheRef = useRef<Map<number, { info: string; cards: EvidenceCard[] }>>(new Map());
  const [previewAttachment, setPreviewAttachment] = useState<FilePreviewAttachment | null>(null);
  const [citationPreview, setCitationPreview] = useState<CitationPreview | null>(null);
  const previewUrl = useMemo(() => {
    if (!previewAttachment?.fileId) return "";
    return buildRawFileUrl(previewAttachment.fileId);
  }, [previewAttachment]);
  const previewNameLower = String(previewAttachment?.name || "").toLowerCase();
  const previewIsImage = /\.(png|jpe?g|gif|bmp|webp|svg|tiff?)$/i.test(previewNameLower);
  const previewIsPdf = previewNameLower.endsWith(".pdf");

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
    const cache = evidenceCacheRef.current;
    for (const key of Array.from(cache.keys())) {
      if (key < 0 || key >= chatTurns.length) {
        cache.delete(key);
      }
    }
  }, [chatTurns.length]);

  useEffect(() => {
    const container = turnsRootRef.current;
    if (!container) {
      return;
    }

    const citationAnchors = Array.from(
      container.querySelectorAll<HTMLAnchorElement>(".chat-answer-html a.citation"),
    );
    for (const anchor of citationAnchors) {
      const tier = resolveStrengthTier(
        Number(anchor.getAttribute("data-strength-tier") || ""),
        Number(anchor.getAttribute("data-strength") || ""),
      );
      if (tier > 0) {
        anchor.setAttribute("data-strength-tier-resolved", String(tier));
      } else {
        anchor.removeAttribute("data-strength-tier-resolved");
      }
      if (!anchor.hasAttribute("href")) {
        anchor.setAttribute("tabindex", "0");
        anchor.setAttribute("role", "button");
      }
      const refLabel = String(anchor.textContent || "").replace(/\s+/g, " ").trim();
      let displayNumber = String(anchor.getAttribute("data-citation-number") || "").trim();
      if (!/^\d{1,4}$/.test(displayNumber)) {
        const fallbackMatch = refLabel.match(/(\d{1,4})/);
        displayNumber = fallbackMatch?.[1] || "";
        if (displayNumber) {
          anchor.setAttribute("data-citation-number", displayNumber);
        }
      }
      const pageLabel = String(anchor.getAttribute("data-page") || "")
        .replace(/\s+/g, " ")
        .trim();
      const labelParts = [displayNumber ? `Citation ${displayNumber}` : (refLabel || "Citation")];
      const tierLabel = strengthTierLabel(tier);
      if (tierLabel) {
        labelParts.push(tierLabel.toLowerCase());
      }
      if (pageLabel) {
        labelParts.push(`page ${pageLabel}`);
      }
      anchor.setAttribute("aria-label", labelParts.join(", "));
    }
  }, [chatTurns]);

  useEffect(() => {
    const container = turnsRootRef.current;
    if (!container) {
      return;
    }

    let hoverTimer: number | null = null;
    const findCitationAnchor = (target: EventTarget | null): HTMLAnchorElement | null => {
      if (!(target instanceof Element)) {
        if (target instanceof Node && target.parentElement) {
          return target.parentElement.closest(CITATION_ANCHOR_SELECTOR) as HTMLAnchorElement | null;
        }
        return null;
      }
      return target.closest(CITATION_ANCHOR_SELECTOR) as HTMLAnchorElement | null;
    };

    const clearHoverTimer = () => {
      if (hoverTimer !== null) {
        window.clearTimeout(hoverTimer);
        hoverTimer = null;
      }
    };

    const hidePreview = () => {
      clearHoverTimer();
      setCitationPreview(null);
    };

    const getEvidenceCards = (turnIndex: number, turn: ChatTurn): EvidenceCard[] => {
      const infoHtml = String(turn.info || "");
      const cached = evidenceCacheRef.current.get(turnIndex);
      if (cached && cached.info === infoHtml) {
        return cached.cards;
      }
      const cards = parseEvidence(infoHtml);
      evidenceCacheRef.current.set(turnIndex, { info: infoHtml, cards });
      return cards;
    };

    const showPreviewFromAnchor = (anchor: HTMLAnchorElement) => {
      const turnNode = anchor.closest<HTMLElement>("[data-turn-index]");
      const turnIndex = Number(turnNode?.getAttribute("data-turn-index") || "");
      if (!Number.isFinite(turnIndex) || turnIndex < 0 || turnIndex >= chatTurns.length) {
        hidePreview();
        return;
      }

      const turn = chatTurns[turnIndex];
      const evidenceCards = getEvidenceCards(turnIndex, turn);
      const resolved = resolveCitationFocusFromAnchor({
        turn,
        citationAnchor: anchor,
        evidenceCards,
      });
      const rect = anchor.getBoundingClientRect();
      const width = Math.max(180, Math.min(360, window.innerWidth - 24));
      const minCenter = 12 + width / 2;
      const maxCenter = window.innerWidth - 12 - width / 2;
      const center = rect.left + rect.width / 2;
      const left = minCenter > maxCenter
        ? window.innerWidth / 2
        : Math.max(minCenter, Math.min(maxCenter, center));
      const placeAbove = rect.top > 172;
      const top = placeAbove ? rect.top - 8 : rect.bottom + 8;
      const tierLabel = strengthTierLabel(resolved.strengthTierResolved);
      if (resolved.strengthTierResolved > 0) {
        anchor.setAttribute("data-strength-tier-resolved", String(resolved.strengthTierResolved));
      }
      setCitationPreview({
        left,
        top,
        width,
        placeAbove,
        sourceName: resolved.focus.sourceName || "Indexed source",
        page: resolved.focus.page,
        extract: formatPreviewExtract(resolved.focus.extract),
        strengthLabel: tierLabel || undefined,
        citationRef: String(anchor.textContent || "").replace(/\s+/g, " ").trim(),
      });
    };

    const handleMouseOver = (event: MouseEvent) => {
      const anchor = findCitationAnchor(event.target);
      if (!anchor || !container.contains(anchor)) {
        return;
      }
      clearHoverTimer();
      hoverTimer = window.setTimeout(() => {
        showPreviewFromAnchor(anchor);
      }, 180);
    };

    const handleMouseOut = (event: MouseEvent) => {
      const anchor = findCitationAnchor(event.target);
      if (!anchor || !container.contains(anchor)) {
        return;
      }
      clearHoverTimer();
      setCitationPreview(null);
    };

    const handleFocusIn = (event: FocusEvent) => {
      const anchor = findCitationAnchor(event.target);
      if (!anchor || !container.contains(anchor)) {
        return;
      }
      clearHoverTimer();
      showPreviewFromAnchor(anchor);
    };

    const handleFocusOut = (event: FocusEvent) => {
      const anchor = findCitationAnchor(event.target);
      if (!anchor || !container.contains(anchor)) {
        return;
      }
      if (event.relatedTarget instanceof Node && anchor.contains(event.relatedTarget)) {
        return;
      }
      setCitationPreview(null);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        hidePreview();
      }
    };
    const handleClick = () => {
      setCitationPreview(null);
    };

    container.addEventListener("mouseover", handleMouseOver);
    container.addEventListener("mouseout", handleMouseOut);
    container.addEventListener("focusin", handleFocusIn);
    container.addEventListener("focusout", handleFocusOut);
    container.addEventListener("keydown", handleKeyDown);
    container.addEventListener("click", handleClick, true);
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("resize", hidePreview);
    document.addEventListener("scroll", hidePreview, true);

    return () => {
      clearHoverTimer();
      container.removeEventListener("mouseover", handleMouseOver);
      container.removeEventListener("mouseout", handleMouseOut);
      container.removeEventListener("focusin", handleFocusIn);
      container.removeEventListener("focusout", handleFocusOut);
      container.removeEventListener("keydown", handleKeyDown);
      container.removeEventListener("click", handleClick, true);
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("resize", hidePreview);
      document.removeEventListener("scroll", hidePreview, true);
    };
  }, [chatTurns]);

  return (
    <div ref={turnsRootRef} className="mx-auto w-full max-w-[1800px] space-y-4">
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
            data-turn-index={index}
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
                      <button
                        key={`${attachment.name}-${attachmentIdx}`}
                        type="button"
                        onClick={(event) => {
                          stopBubbleAction(event);
                          setPreviewAttachment({
                            name: attachment.name,
                            fileId: attachment.fileId,
                            status: "indexed",
                          });
                        }}
                        className="bg-white border border-black/[0.08] rounded-xl px-3 py-2 shadow-sm"
                        title={attachment.fileId ? "Open file preview" : "Preview unavailable"}
                      >
                        <div className="flex items-center gap-2">
                          <FileText className="w-3.5 h-3.5 text-[#6e6e73] shrink-0" />
                          <span className="text-[13px] text-[#1d1d1f] truncate">
                            {attachment.name}
                          </span>
                        </div>
                      </button>
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
                <div className="w-full max-w-[98%] xl:max-w-full">
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
                    <div className="rounded-2xl border border-black/[0.06] bg-white px-4 py-3 text-[15px] leading-[1.72] text-[#1d1d1f] shadow-[0_10px_28px_-22px_rgba(0,0,0,0.35)]">
                      <div
                        className="chat-answer-html [&_p]:mb-3.5 [&_p]:leading-[1.78] [&_p:last-child]:mb-0 [&_ul]:mb-3.5 [&_ul]:list-disc [&_ul]:pl-6 [&_ul>li]:mb-1.5 [&_ol]:mb-3.5 [&_ol]:list-decimal [&_ol]:pl-6 [&_ol>li]:mb-1.5 [&_h1]:mb-3 [&_h1]:text-[22px] [&_h1]:font-semibold [&_h1]:tracking-[-0.01em] [&_h2]:mt-5 [&_h2]:mb-2.5 [&_h2]:text-[18px] [&_h2]:font-semibold [&_h2]:tracking-[-0.01em] [&_h2]:text-[#141518] [&_h3]:mt-4 [&_h3]:mb-2 [&_h3]:text-[16px] [&_h3]:font-semibold [&_h3]:text-[#1a2430] [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-black/[0.08] [&_pre]:bg-[#f7f7f9] [&_pre]:p-3 [&_code]:font-mono [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-black/[0.08] [&_th]:bg-[#f7f7f9] [&_th]:px-2 [&_th]:py-1 [&_td]:border [&_td]:border-black/[0.08] [&_td]:px-2 [&_td]:py-1 [&_blockquote]:border-l-4 [&_blockquote]:border-[#d2d2d7] [&_blockquote]:pl-3 [&_blockquote]:text-[#515154] [&_details]:my-2 [&_summary]:cursor-pointer [&_img]:max-w-full [&_img]:rounded-lg"
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

      {citationPreview ? (
        <div
          role="tooltip"
          aria-live="polite"
          className="citation-peek-tooltip pointer-events-none fixed z-[130] rounded-xl border border-[#d4d9e4] bg-white/98 p-3 text-left shadow-[0_22px_46px_-26px_rgba(18,28,45,0.55)] backdrop-blur-[1px]"
          style={{
            left: citationPreview.left,
            top: citationPreview.top,
            width: citationPreview.width,
            transform: citationPreview.placeAbove ? "translate(-50%, -100%)" : "translate(-50%, 0)",
          }}
        >
          <div className="mb-1.5 flex items-center gap-2 text-[10px] text-[#5f6472]">
            {citationPreview.citationRef ? (
              <span className="rounded-full border border-[#ccd3e2] bg-[#f5f7fb] px-2 py-0.5 font-semibold text-[#2f3a51]">
                {citationPreview.citationRef}
              </span>
            ) : null}
            <span className="truncate" title={citationPreview.sourceName}>
              {citationPreview.sourceName}
            </span>
            {citationPreview.page ? (
              <span className="shrink-0 rounded-full border border-black/[0.08] bg-white px-1.5 py-0.5 text-[#6e6e73]">
                p. {citationPreview.page}
              </span>
            ) : null}
            {citationPreview.strengthLabel ? (
              <span className="shrink-0 rounded-full border border-black/[0.08] bg-white px-1.5 py-0.5 text-[#6e6e73]">
                {citationPreview.strengthLabel}
              </span>
            ) : null}
          </div>
          <p className="citation-peek-tooltip-text citation-peek-snippet text-[12px] leading-[1.45] text-[#1e2532]">
            {citationPreview.extract}
          </p>
        </div>
      ) : null}

      {previewAttachment ? (
        <div className="fixed inset-0 z-[140] bg-black/45 backdrop-blur-[2px] px-4 py-6" onClick={() => setPreviewAttachment(null)}>
          <div
            className="mx-auto flex h-full w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-black/[0.08] bg-white shadow-[0_24px_70px_-28px_rgba(0,0,0,0.65)]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-black/[0.06] px-4 py-3">
              <p className="min-w-0 truncate text-[14px] font-medium text-[#1d1d1f]" title={previewAttachment.name}>
                {previewAttachment.name}
              </p>
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
                  Preview unavailable for this file.
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

export { TurnsPanel };
