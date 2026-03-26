import { useEffect, useMemo, useRef, useState } from "react";
import type { ClickRippleEntry } from "@maia/theatre";
import { emitTheatreMetric } from "../agentActivityPanel/theatreTelemetry";
import {
  INTERACTION_SUGGESTION_MIN_CONFIDENCE,
  mergeSuggestion,
  type InteractionSuggestion,
  type InteractionSuggestionRejectReason,
} from "../agentActivityPanel/interactionSuggestionMerge";
import { parsePercent } from "./sceneRuntime";
import type { HighlightRegion } from "./types";

type SceneRecord = Record<string, unknown>;

type UseInteractionSceneStateOptions = {
  action: string;
  actionTarget: SceneRecord;
  actionTargetLabel: string;
  activeEventType: string;
  activeSceneData: SceneRecord;
  activeStepIndex: number | null;
  interactionSuggestion: InteractionSuggestion[] | null;
  isBrowserScene: boolean;
  isDocsScene: boolean;
  isDocumentScene: boolean;
  isPdfScene: boolean;
  isSheetsScene: boolean;
  pdfScrollPercent: number | null;
  regionSource: SceneRecord;
  runId: string;
  scrollPercent: number | null;
  targetRegion: HighlightRegion | null;
};

function useInteractionSceneState({
  action,
  actionTarget,
  actionTargetLabel,
  activeEventType,
  activeSceneData,
  activeStepIndex,
  interactionSuggestion,
  isBrowserScene,
  isDocsScene,
  isDocumentScene,
  isPdfScene,
  isSheetsScene,
  pdfScrollPercent,
  regionSource,
  runId,
  scrollPercent,
  targetRegion,
}: UseInteractionSceneStateOptions) {
  const inferredCursorX =
    parsePercent(
      activeSceneData["cursor_x"] ??
        actionTarget["x"] ??
        actionTarget["region_x"] ??
        regionSource["x"] ??
        regionSource["region_x"],
    ) ?? (targetRegion ? targetRegion.x + targetRegion.width / 2 : null);
  const inferredCursorY =
    parsePercent(
      activeSceneData["cursor_y"] ??
        actionTarget["y"] ??
        actionTarget["region_y"] ??
        regionSource["y"] ??
        regionSource["region_y"],
    ) ?? (targetRegion ? targetRegion.y + targetRegion.height / 2 : null);
  const normalizedInteractionEventType = String(activeEventType || "").trim().toLowerCase();
  const interactionAction = String(action || "").trim().toLowerCase();
  const interactionSurfaceActive =
    isBrowserScene || isPdfScene || isDocsScene || isSheetsScene || isDocumentScene;
  const deterministicScrollPercent = isPdfScene ? pdfScrollPercent ?? scrollPercent : scrollPercent;
  const syntheticCursorFallback = (() => {
    if (!interactionSurfaceActive) {
      return null;
    }
    if (interactionAction === "scroll" || normalizedInteractionEventType.includes("scroll")) {
      const y =
        typeof deterministicScrollPercent === "number"
          ? Math.max(8, Math.min(92, deterministicScrollPercent))
          : 52;
      return { x: 88, y };
    }
    if (interactionAction === "navigate" || interactionAction === "open") {
      return { x: 24, y: 9 };
    }
    if (
      interactionAction === "type" ||
      interactionAction === "fill" ||
      interactionAction === "input" ||
      normalizedInteractionEventType.includes("type")
    ) {
      return { x: 46, y: 42 };
    }
    if (
      interactionAction === "find" ||
      interactionAction === "extract" ||
      interactionAction === "verify" ||
      normalizedInteractionEventType.includes("find") ||
      normalizedInteractionEventType.includes("extract")
    ) {
      return { x: 56, y: 48 };
    }
    if (
      normalizedInteractionEventType.startsWith("browser_") ||
      normalizedInteractionEventType.startsWith("web_") ||
      normalizedInteractionEventType.startsWith("pdf_") ||
      normalizedInteractionEventType.startsWith("doc_") ||
      normalizedInteractionEventType.startsWith("docs.") ||
      normalizedInteractionEventType.startsWith("sheet_") ||
      normalizedInteractionEventType.startsWith("sheets.")
    ) {
      return { x: 58, y: 50 };
    }
    return null;
  })();

  const interactionMerge = useMemo(() => {
    let rejected: { reason: InteractionSuggestionRejectReason; confidence: number | null } | null = null;
    const merged = mergeSuggestion(
      inferredCursorX,
      inferredCursorY,
      interactionAction,
      actionTargetLabel,
      deterministicScrollPercent,
      interactionSuggestion,
      INTERACTION_SUGGESTION_MIN_CONFIDENCE,
      syntheticCursorFallback,
      (reason, suggestion) => {
        rejected = { reason, confidence: suggestion?.confidence ?? null };
      },
    );
    return { merged, rejected };
  }, [
    actionTargetLabel,
    deterministicScrollPercent,
    inferredCursorX,
    inferredCursorY,
    interactionAction,
    interactionSuggestion,
    syntheticCursorFallback,
  ]);

  const mergedInteraction = interactionMerge.merged;
  const rejectedInteractionSuggestion = interactionMerge.rejected;
  const actionForScene = mergedInteraction.action || interactionAction;
  const actionTargetLabelForScene = mergedInteraction.targetLabel || actionTargetLabel;
  const scrollPercentForScene = mergedInteraction.scrollPercent;
  const cursorX = mergedInteraction.cursorX;
  const cursorY = mergedInteraction.cursorY;
  const isClickEvent =
    /(^|[._])(left|right|double)?click([._]|$)/i.test(normalizedInteractionEventType) ||
    /(^|[._])(tap|press|select|submit|open)([._]|$)/i.test(normalizedInteractionEventType) ||
    ["click", "tap", "press", "select", "submit", "open"].includes(interactionAction);
  const isDeterministicClickCue = isClickEvent && mergedInteraction.source !== "suggested";

  useEffect(() => {
    if (mergedInteraction.source === "none") {
      return;
    }
    emitTheatreMetric("interaction_signal_source", {
      source: mergedInteraction.source,
      action: mergedInteraction.action || interactionAction,
      confidence: mergedInteraction.suggestionConfidence,
      run_id: runId || null,
      step_index: activeStepIndex,
    });
  }, [
    activeStepIndex,
    interactionAction,
    mergedInteraction.action,
    mergedInteraction.source,
    mergedInteraction.suggestionConfidence,
    runId,
  ]);

  useEffect(() => {
    if (!rejectedInteractionSuggestion) {
      return;
    }
    emitTheatreMetric("interaction_suggestion_rejected", {
      reason: rejectedInteractionSuggestion.reason,
      confidence: rejectedInteractionSuggestion.confidence,
      run_id: runId || null,
      step_index: activeStepIndex,
    });
  }, [activeStepIndex, rejectedInteractionSuggestion, runId]);

  const rippleCounterRef = useRef(0);
  const prevEventTypeRef = useRef("");
  const [clickRipples, setClickRipples] = useState<ClickRippleEntry[]>([]);

  useEffect(() => {
    if (activeEventType === prevEventTypeRef.current) {
      return;
    }
    prevEventTypeRef.current = activeEventType;
    if (!isDeterministicClickCue || cursorX === null || cursorY === null) {
      return;
    }
    const id = String(++rippleCounterRef.current);
    setClickRipples((previous) => [...previous, { id, x: cursorX, y: cursorY, type: "click" }]);
    const timer = window.setTimeout(() => {
      setClickRipples((previous) => previous.filter((ripple) => ripple.id !== id));
    }, 700);
    return () => window.clearTimeout(timer);
  }, [activeEventType, cursorX, cursorY, isDeterministicClickCue]);

  return {
    actionForScene,
    actionTargetLabelForScene,
    clickRipples,
    cursorSource: mergedInteraction.source,
    cursorX,
    cursorY,
    isClickEvent,
    isDeterministicClickCue,
    scrollPercentForScene,
  };
}

export { useInteractionSceneState };
