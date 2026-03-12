import { useEffect, type Dispatch, type MutableRefObject, type RefObject, type SetStateAction } from "react";
import type { ChatTurn } from "../../../types";
import { parseEvidence } from "../../../utils/infoInsights";
import type { EvidenceCard } from "../../../utils/infoInsights";
import {
  CITATION_ANCHOR_SELECTOR,
  resolveCitationAnchorInteractionPolicy,
  resolveCitationFocusFromAnchor,
  resolveStrengthTier,
} from "../citationFocus";
import type { CitationPreview } from "./CitationPreviewTooltip";

const CHAT_CITATION_SELECTOR = CITATION_ANCHOR_SELECTOR
  .split(",")
  .map((selector) => `.chat-answer-html ${selector.trim()}`)
  .join(", ");

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
  const unquoted = compact
    .replace(/^[\u201c\u201d"'`]+/, "")
    .replace(/[\u201c\u201d"'`]+$/, "")
    .trim();
  const text = unquoted || compact;
  if (text.length <= 260) {
    return text;
  }
  const clipped = text.slice(0, 260);
  const wordCut = clipped.lastIndexOf(" ");
  return `${(wordCut >= 140 ? clipped.slice(0, wordCut) : clipped).trim()}...`;
}

type UseCitationPreviewParams = {
  chatTurns: ChatTurn[];
  turnsRootRef: RefObject<HTMLDivElement | null>;
  evidenceCacheRef: MutableRefObject<Map<number, { info: string; cards: EvidenceCard[] }>>;
  setCitationPreview: Dispatch<SetStateAction<CitationPreview | null>>;
};

function useCitationPreview({
  chatTurns,
  turnsRootRef,
  evidenceCacheRef,
  setCitationPreview,
}: UseCitationPreviewParams) {
  useEffect(() => {
    const cache = evidenceCacheRef.current;
    for (const key of Array.from(cache.keys())) {
      if (key < 0 || key >= chatTurns.length) {
        cache.delete(key);
      }
    }
  }, [chatTurns.length, evidenceCacheRef]);

  useEffect(() => {
    const container = turnsRootRef.current;
    if (!container) {
      return;
    }

    const citationAnchors = Array.from(
      container.querySelectorAll<HTMLAnchorElement>(CHAT_CITATION_SELECTOR),
    );
    for (const anchor of citationAnchors) {
      const interactionPolicy = resolveCitationAnchorInteractionPolicy(anchor);
      const tier = resolveStrengthTier(
        Number(anchor.getAttribute("data-strength-tier") || ""),
        Number(anchor.getAttribute("data-strength") || ""),
      );
      if (tier > 0) {
        anchor.setAttribute("data-strength-tier-resolved", String(tier));
      } else {
        anchor.removeAttribute("data-strength-tier-resolved");
      }
      if (interactionPolicy.openDirectOnPrimaryClick) {
        anchor.setAttribute("data-direct-url", "true");
      } else {
        anchor.removeAttribute("data-direct-url");
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
      const pageLabel = String(anchor.getAttribute("data-page") || "").replace(/\s+/g, " ").trim();
      const labelParts = [displayNumber ? `Citation ${displayNumber}` : (refLabel || "Citation")];
      const tierLabel = strengthTierLabel(tier);
      if (tierLabel) {
        labelParts.push(tierLabel.toLowerCase());
      }
      if (pageLabel) {
        labelParts.push(`page ${pageLabel}`);
      }
      if (interactionPolicy.openDirectOnPrimaryClick) {
        labelParts.push("opens source directly");
      }
      anchor.setAttribute("aria-label", labelParts.join(", "));
    }
  }, [chatTurns, turnsRootRef]);

  useEffect(() => {
    const container = turnsRootRef.current;
    if (!container) {
      return;
    }

    let hoverTimer: number | null = null;
    const findCitationAnchor = (target: EventTarget | null): HTMLAnchorElement | null => {
      if (target instanceof Element) {
        const match = target.closest(CHAT_CITATION_SELECTOR);
        return match instanceof HTMLAnchorElement ? match : null;
      }
      if (target instanceof Node && target.parentElement) {
        const match = target.parentElement.closest(CHAT_CITATION_SELECTOR);
        return match instanceof HTMLAnchorElement ? match : null;
      }
      return null;
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
      const cards = parseEvidence(infoHtml, {
        infoPanel: (turn.infoPanel as Record<string, unknown>) || null,
      });
      evidenceCacheRef.current.set(turnIndex, { info: infoHtml, cards });
      return cards;
    };

    const resolveTurnIndexFromAnchor = (anchor: HTMLAnchorElement): number => {
      const turnNode = anchor.closest<HTMLElement>("[data-turn-index]");
      const parsed = Number(turnNode?.getAttribute("data-turn-index") || "");
      if (Number.isFinite(parsed) && parsed >= 0 && parsed < chatTurns.length) {
        return Math.round(parsed);
      }
      return chatTurns.length ? chatTurns.length - 1 : -1;
    };

    const showPreviewFromAnchor = (anchor: HTMLAnchorElement) => {
      const turnIndex = resolveTurnIndexFromAnchor(anchor);
      if (turnIndex < 0 || turnIndex >= chatTurns.length) {
        hidePreview();
        return;
      }

      try {
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
        const left =
          minCenter > maxCenter
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
      } catch {
        hidePreview();
      }
    };

    const handlePointerOver = (event: PointerEvent) => {
      const anchor = findCitationAnchor(event.target);
      if (!anchor || !container.contains(anchor)) {
        return;
      }
      const from = event.relatedTarget;
      if (from instanceof Node && anchor.contains(from)) {
        return;
      }
      clearHoverTimer();
      hoverTimer = window.setTimeout(() => {
        showPreviewFromAnchor(anchor);
      }, 90);
    };

    const handlePointerOut = (event: PointerEvent) => {
      const anchor = findCitationAnchor(event.target);
      if (!anchor || !container.contains(anchor)) {
        return;
      }
      const related = event.relatedTarget;
      if (related instanceof Node && anchor.contains(related)) {
        return;
      }
      hidePreview();
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
      const related = event.relatedTarget;
      if (related instanceof Node && anchor.contains(related)) {
        return;
      }
      hidePreview();
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        hidePreview();
      }
    };

    const handleClick = () => {
      setCitationPreview(null);
    };

    container.addEventListener("pointerover", handlePointerOver);
    container.addEventListener("pointerout", handlePointerOut);
    container.addEventListener("focusin", handleFocusIn);
    container.addEventListener("focusout", handleFocusOut);
    container.addEventListener("keydown", handleKeyDown);
    container.addEventListener("click", handleClick, true);
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("resize", hidePreview);
    document.addEventListener("scroll", hidePreview, true);

    return () => {
      clearHoverTimer();
      container.removeEventListener("pointerover", handlePointerOver);
      container.removeEventListener("pointerout", handlePointerOut);
      container.removeEventListener("focusin", handleFocusIn);
      container.removeEventListener("focusout", handleFocusOut);
      container.removeEventListener("keydown", handleKeyDown);
      container.removeEventListener("click", handleClick, true);
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("resize", hidePreview);
      document.removeEventListener("scroll", hidePreview, true);
    };
  }, [chatTurns, evidenceCacheRef, turnsRootRef, setCitationPreview]);
}

export { useCitationPreview };
