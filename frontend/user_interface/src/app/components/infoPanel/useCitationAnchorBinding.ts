import { useEffect, type RefObject } from "react";
import { getPdfHighlightTargetCached } from "../../../api/client/uploads";
import type { ChatTurn, CitationFocus } from "../../types";
import type { EvidenceCard } from "../../utils/infoInsights";
import {
  CITATION_ANCHOR_SELECTOR,
  resolveCitationAnchorInteractionPolicy,
  resolveCitationFocusFromAnchor,
  resolveStrengthTier,
  shouldOpenCitationSourceUrlForPointerEvent,
} from "../chatMain/citationFocus";

type UseCitationAnchorBindingParams = {
  containerRef: RefObject<HTMLDivElement | null>;
  renderedInfoHtml: string;
  userPrompt: string;
  assistantHtml: string;
  infoHtml: string;
  infoPanel?: Record<string, unknown> | null;
  evidenceCards: EvidenceCard[];
  onSelectCitationFocus?: (citation: CitationFocus) => void;
};

function useCitationAnchorBinding({
  containerRef,
  renderedInfoHtml,
  userPrompt,
  assistantHtml,
  infoHtml,
  infoPanel,
  evidenceCards,
  onSelectCitationFocus,
}: UseCitationAnchorBindingParams) {
  const getCitationAnchors = (container: HTMLDivElement): HTMLAnchorElement[] =>
    Array.from(container.querySelectorAll<HTMLAnchorElement>(CITATION_ANCHOR_SELECTOR));

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const citationAnchors = getCitationAnchors(container);
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
    }
  }, [containerRef, renderedInfoHtml]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !renderedInfoHtml) {
      return;
    }
    const turnForCitation: ChatTurn = {
      user: String(userPrompt || ""),
      assistant: String(assistantHtml || ""),
      info: String(infoHtml || ""),
      infoPanel: infoPanel || undefined,
      attachments: [],
    };
    const anchors = getCitationAnchors(container).slice(0, 4);
    if (!anchors.length) {
      return;
    }
    const timer = window.setTimeout(() => {
      const scheduledPrefetches = new Set<string>();
      for (const anchor of anchors) {
        const resolved = resolveCitationFocusFromAnchor({
          turn: turnForCitation,
          citationAnchor: anchor,
          evidenceCards,
        });
        const focus = resolved.focus;
        if (
          !focus.fileId ||
          !focus.page ||
          (!focus.extract && !focus.claimText) ||
          (Array.isArray(focus.highlightBoxes) && focus.highlightBoxes.length > 0) ||
          (Array.isArray(focus.evidenceUnits) && focus.evidenceUnits.length > 0)
        ) {
          continue;
        }
        const prefetchKey = [
          focus.fileId,
          focus.page || "",
          focus.chunkId || "",
        ].join("::");
        if (scheduledPrefetches.has(prefetchKey)) {
          continue;
        }
        scheduledPrefetches.add(prefetchKey);
        void getPdfHighlightTargetCached(focus.fileId, {
          page: focus.page,
          text: focus.extract || "",
          claim_text: focus.claimText || "",
          chunk_id: focus.chunkId || "",
        }).catch(() => undefined);
      }
    }, 300);
    return () => window.clearTimeout(timer);
  }, [assistantHtml, containerRef, evidenceCards, infoHtml, infoPanel, renderedInfoHtml, userPrompt]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const turnForCitation: ChatTurn = {
      user: String(userPrompt || ""),
      assistant: String(assistantHtml || ""),
      info: String(infoHtml || ""),
      infoPanel: infoPanel || undefined,
      attachments: [],
    };

    const isCitationAnchor = (anchor: HTMLAnchorElement): boolean => {
      const href = String(anchor.getAttribute("href") || "").trim();
      return (
        anchor.classList.contains("citation") ||
        href.startsWith("#evidence-") ||
        anchor.hasAttribute("data-file-id") ||
        anchor.hasAttribute("data-source-url") ||
        anchor.hasAttribute("data-viewer-url") ||
        anchor.hasAttribute("data-evidence-id")
      );
    };

    const findCitationAnchor = (target: EventTarget | null): HTMLAnchorElement | null => {
      if (!(target instanceof Element)) {
        if (target instanceof Node && target.parentElement) {
          return target.parentElement.closest(CITATION_ANCHOR_SELECTOR) as HTMLAnchorElement | null;
        }
        return null;
      }
      return target.closest(CITATION_ANCHOR_SELECTOR) as HTMLAnchorElement | null;
    };

    const openSourceUrl = (url: string) => {
      window.open(url, "_blank", "noopener,noreferrer");
    };
    const hoverPrefetches = new Set<string>();

    const selectCitationFromAnchor = (anchor: HTMLAnchorElement): boolean => {
      if (!onSelectCitationFocus || !isCitationAnchor(anchor)) {
        return false;
      }
      const resolved = resolveCitationFocusFromAnchor({
        turn: turnForCitation,
        citationAnchor: anchor,
        evidenceCards,
      });
      onSelectCitationFocus(resolved.focus);
      return true;
    };

    const prefetchCitationHighlight = (anchor: HTMLAnchorElement) => {
      const resolved = resolveCitationFocusFromAnchor({
        turn: turnForCitation,
        citationAnchor: anchor,
        evidenceCards,
      });
      const focus = resolved.focus;
      if (
        !focus.fileId ||
        !focus.page ||
        (!focus.extract && !focus.claimText) ||
        (Array.isArray(focus.highlightBoxes) && focus.highlightBoxes.length > 0) ||
        (Array.isArray(focus.evidenceUnits) && focus.evidenceUnits.length > 0)
      ) {
        return;
      }
      const prefetchKey = [
        focus.fileId,
        focus.page || "",
        focus.chunkId || "",
      ].join("::");
      if (hoverPrefetches.has(prefetchKey)) {
        return;
      }
      hoverPrefetches.add(prefetchKey);
      void getPdfHighlightTargetCached(focus.fileId, {
        page: focus.page,
        text: focus.extract || "",
        claim_text: focus.claimText || "",
        chunk_id: focus.chunkId || "",
      }).catch(() => undefined);
    };

    const onClick = (event: MouseEvent) => {
      const anchor = findCitationAnchor(event.target);
      if (!anchor || !isCitationAnchor(anchor)) {
        return;
      }
      const interactionPolicy = resolveCitationAnchorInteractionPolicy(anchor);
      if (
        shouldOpenCitationSourceUrlForPointerEvent(event, interactionPolicy) ||
        interactionPolicy.openDirectOnPrimaryClick
      ) {
        if (!interactionPolicy.directOpenUrl) {
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        openSourceUrl(interactionPolicy.directOpenUrl);
        return;
      }
      const selected = selectCitationFromAnchor(anchor);
      if (!selected) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
    };

    const onAuxClick = (event: MouseEvent) => {
      if (event.button !== 1) {
        return;
      }
      const anchor = findCitationAnchor(event.target);
      if (!anchor || !isCitationAnchor(anchor)) {
        return;
      }
      const interactionPolicy = resolveCitationAnchorInteractionPolicy(anchor);
      if (!interactionPolicy.directOpenUrl) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      openSourceUrl(interactionPolicy.directOpenUrl);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      const anchor = findCitationAnchor(event.target);
      if (!anchor || !isCitationAnchor(anchor)) {
        return;
      }
      const interactionPolicy = resolveCitationAnchorInteractionPolicy(anchor);
      if (
        interactionPolicy.directOpenUrl &&
        (interactionPolicy.openDirectOnPrimaryClick || event.ctrlKey || event.metaKey)
      ) {
        event.preventDefault();
        event.stopPropagation();
        openSourceUrl(interactionPolicy.directOpenUrl);
        return;
      }
      const selected = selectCitationFromAnchor(anchor);
      if (!selected) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
    };

    const onPointerEnter = (event: PointerEvent) => {
      const anchor = findCitationAnchor(event.target);
      if (!anchor || !isCitationAnchor(anchor)) {
        return;
      }
      prefetchCitationHighlight(anchor);
    };

    container.addEventListener("click", onClick);
    container.addEventListener("auxclick", onAuxClick);
    container.addEventListener("keydown", onKeyDown);
    container.addEventListener("pointerenter", onPointerEnter, true);
    return () => {
      container.removeEventListener("click", onClick);
      container.removeEventListener("auxclick", onAuxClick);
      container.removeEventListener("keydown", onKeyDown);
      container.removeEventListener("pointerenter", onPointerEnter, true);
    };
  }, [assistantHtml, containerRef, evidenceCards, infoHtml, infoPanel, onSelectCitationFocus, userPrompt]);
}

export { useCitationAnchorBinding };
