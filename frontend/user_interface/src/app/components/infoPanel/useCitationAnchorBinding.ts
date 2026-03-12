import { useEffect, type RefObject } from "react";
import type { ChatTurn, CitationFocus } from "../../types";
import type { EvidenceCard } from "../../utils/infoInsights";
import { normalizeEvidenceId } from "./urlHelpers";
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
  evidenceCards: EvidenceCard[];
  onSelectCitationFocus?: (citation: CitationFocus) => void;
};

function useCitationAnchorBinding({
  containerRef,
  renderedInfoHtml,
  userPrompt,
  assistantHtml,
  infoHtml,
  evidenceCards,
  onSelectCitationFocus,
}: UseCitationAnchorBindingParams) {
  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const citationAnchors = Array.from(container.querySelectorAll<HTMLAnchorElement>(".chat-answer-html a.citation"));
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
    if (!container) {
      return;
    }
    const turnForCitation: ChatTurn = {
      user: String(userPrompt || ""),
      assistant: String(assistantHtml || ""),
      info: String(infoHtml || ""),
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

    const focusEvidenceDetails = (evidenceId: string | undefined) => {
      const normalizedId = normalizeEvidenceId(evidenceId);
      if (!normalizedId || !/^evidence-[a-z0-9_-]{1,64}$/i.test(normalizedId)) {
        return;
      }
      const detailsNode = container.querySelector<HTMLElement>(`#${normalizedId}`);
      if (!detailsNode) {
        return;
      }
      if (detailsNode.tagName === "DETAILS") {
        (detailsNode as HTMLDetailsElement).open = true;
      }
      detailsNode.scrollIntoView({ block: "nearest" });
    };

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
      focusEvidenceDetails(resolved.focus.evidenceId);
      return true;
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

    container.addEventListener("click", onClick);
    container.addEventListener("auxclick", onAuxClick);
    container.addEventListener("keydown", onKeyDown);
    return () => {
      container.removeEventListener("click", onClick);
      container.removeEventListener("auxclick", onAuxClick);
      container.removeEventListener("keydown", onKeyDown);
    };
  }, [assistantHtml, containerRef, evidenceCards, infoHtml, onSelectCitationFocus, userPrompt]);
}

export { useCitationAnchorBinding };
