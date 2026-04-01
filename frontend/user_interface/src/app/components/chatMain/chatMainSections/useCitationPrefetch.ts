import { useEffect, type RefObject } from "react";

import { getPdfHighlightTargetCached } from "../../../../api/client/uploads";
import type { ChatTurn } from "../../../types";
import {
  CITATION_ANCHOR_SELECTOR,
  prefetchCitationSources,
  resolveCitationFocusFromAnchor,
} from "../citationFocus";

type UseCitationPrefetchParams = {
  contentScrollRef: RefObject<HTMLDivElement | null>;
  chatTurns: ChatTurn[];
};

export function useCitationPrefetch({ contentScrollRef, chatTurns }: UseCitationPrefetchParams) {
  useEffect(() => {
    const container = contentScrollRef.current;
    if (!container || chatTurns.length === 0) {
      return;
    }
    const timer = window.setTimeout(() => prefetchCitationSources(container), 500);
    return () => window.clearTimeout(timer);
  }, [chatTurns, contentScrollRef]);

  useEffect(() => {
    const container = contentScrollRef.current;
    if (!container || chatTurns.length === 0) {
      return;
    }

    const prefetchCitationGeometry = (anchor: HTMLAnchorElement) => {
      const turnNode = anchor.closest<HTMLElement>("[data-turn-index]");
      const turnIndex = Number(turnNode?.dataset.turnIndex || Number.NaN);
      if (!Number.isFinite(turnIndex) || turnIndex < 0 || turnIndex >= chatTurns.length) {
        return;
      }
      const turn = chatTurns[turnIndex];
      if (!turn) {
        return;
      }
      const resolved = resolveCitationFocusFromAnchor({ turn, citationAnchor: anchor });
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
      void getPdfHighlightTargetCached(focus.fileId, {
        page: focus.page,
        text: focus.extract || "",
        claim_text: focus.claimText || "",
        chunk_id: focus.chunkId || "",
      }).catch(() => undefined);
    };

    const warmVisibleCitations = () => {
      const anchors = Array.from(
        container.querySelectorAll<HTMLAnchorElement>(".chat-answer-html a.citation"),
      ).slice(0, 8);
      for (const anchor of anchors) {
        prefetchCitationGeometry(anchor);
      }
    };

    const onPointerEnter = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      const anchor = target?.closest?.(CITATION_ANCHOR_SELECTOR) as HTMLAnchorElement | null;
      if (!anchor) {
        return;
      }
      prefetchCitationGeometry(anchor);
    };

    const timer = window.setTimeout(warmVisibleCitations, 320);
    container.addEventListener("pointerenter", onPointerEnter, true);
    return () => {
      window.clearTimeout(timer);
      container.removeEventListener("pointerenter", onPointerEnter, true);
    };
  }, [chatTurns, contentScrollRef]);
}
