import type { MutableRefObject } from "react";
import {
  buildOverlayRectsForRange,
  collectSpanSegments,
  findRangeByCharOffsets,
  findHighlightRange,
  type OverlayRect,
} from "./citationPdfHighlight";

type TryFocusHighlightParams = {
  targetPage: number;
  appliedKey: string;
  charStart?: number;
  charEnd?: number;
  searchCandidates: string[];
  externalOverlayRects: OverlayRect[];
  pageSurfaceRefs: MutableRefObject<Record<number, HTMLDivElement | null>>;
  overlayRectsByPageRef: MutableRefObject<Record<number, OverlayRect[]>>;
  appliedHighlightKeyRef: MutableRefObject<string>;
  clampPage: (value: number) => number;
  applyOverlayRects: (targetPage: number, rects: OverlayRect[]) => void;
  scrollToOverlayRect: (params: {
    pageSurface: HTMLElement;
    page: number;
    overlayRect: OverlayRect;
  }) => void;
};

export function tryFocusHighlight({
  targetPage,
  appliedKey,
  charStart,
  charEnd,
  searchCandidates,
  externalOverlayRects,
  pageSurfaceRefs,
  overlayRectsByPageRef,
  appliedHighlightKeyRef,
  clampPage,
  applyOverlayRects,
  scrollToOverlayRect,
}: TryFocusHighlightParams): boolean {
  const safePage = clampPage(targetPage);
  const pageSurface = pageSurfaceRefs.current[safePage];
  if (!pageSurface) {
    return false;
  }
  const currentRects = overlayRectsByPageRef.current[safePage] || [];
  if (appliedHighlightKeyRef.current === appliedKey && currentRects.length > 0) {
    return true;
  }
  if (externalOverlayRects.length) {
    applyOverlayRects(safePage, externalOverlayRects);
    scrollToOverlayRect({
      pageSurface,
      page: safePage,
      overlayRect: externalOverlayRects[0],
    });
    appliedHighlightKeyRef.current = appliedKey;
    return true;
  }
  if (!searchCandidates.length) {
    appliedHighlightKeyRef.current = appliedKey;
    return true;
  }
  const { segments, combined } = collectSpanSegments(pageSurface);
  const highlightRange =
    findRangeByCharOffsets(segments, charStart, charEnd) ||
    findHighlightRange({
      segments,
      combined,
      candidates: searchCandidates,
    });
  if (!highlightRange) {
    return false;
  }

  const overlayRects = buildOverlayRectsForRange(pageSurface, segments, highlightRange);
  if (!overlayRects.length) {
    return false;
  }
  applyOverlayRects(safePage, overlayRects);
  scrollToOverlayRect({
    pageSurface,
    page: safePage,
    overlayRect: overlayRects[0],
  });
  appliedHighlightKeyRef.current = appliedKey;
  return true;
}
