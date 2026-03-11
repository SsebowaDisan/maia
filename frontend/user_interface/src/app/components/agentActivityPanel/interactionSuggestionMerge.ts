import type { AgentActivityEvent } from "../../types";
import { EVT_INTERACTION_SUGGESTION } from "../../constants/eventTypes";
import { readBooleanField, readNumberField, readStringField } from "./value_readers";

const INTERACTION_SUGGESTION_MIN_CONFIDENCE = 0.4;

type InteractionSuggestionSource = "llm_suggestion";

type InteractionSuggestion = {
  action: string;
  targetLabel: string;
  highlightText?: string;
  cursorX: number | null;
  cursorY: number | null;
  scrollPercent: number | null;
  confidence: number;
  reason: string;
  advisory: true;
  noExecution: true;
  source: InteractionSuggestionSource;
  stepIndex: number | null;
  eventId: string;
  runId: string;
};

type InteractionSuggestionRejectReason = "low_confidence" | "missing_advisory_guard";

type MergedInteractionSource = "deterministic" | "suggested" | "synthetic_fallback" | "none";

type MergedInteractionState = {
  cursorX: number | null;
  cursorY: number | null;
  action: string;
  targetLabel: string;
  scrollPercent: number | null;
  source: MergedInteractionSource;
  suggestionConfidence: number | null;
  suggestionReason: string | null;
};

function clampPercent(value: number | null): number | null {
  if (value === null || !Number.isFinite(value)) {
    return null;
  }
  return Math.max(0, Math.min(100, Number(value)));
}

function normalizeSuggestionKey({
  runId,
  stepIndex,
  fallbackEventId,
}: {
  runId: string;
  stepIndex: number | null;
  fallbackEventId: string;
}): string {
  if (stepIndex !== null) {
    return `${runId || "run"}:${String(stepIndex)}`;
  }
  return fallbackEventId;
}

function isInteractionSuggestionEvent(event: AgentActivityEvent | null): boolean {
  if (!event) {
    return false;
  }
  return String(event.event_type || "").trim().toLowerCase() === EVT_INTERACTION_SUGGESTION;
}

function suggestionLookupKeyForEvent(event: AgentActivityEvent | null): string {
  if (!event) {
    return "";
  }
  const stepIndex = readNumberField(event.metadata?.["step_index"] ?? event.data?.["step_index"]);
  return normalizeSuggestionKey({
    runId: String(event.run_id || "").trim(),
    stepIndex,
    fallbackEventId: String(event.event_id || "").trim(),
  });
}

function extractSuggestionLayer(events: AgentActivityEvent[]): Map<string, InteractionSuggestion[]> {
  const layer = new Map<string, InteractionSuggestion[]>();
  for (const event of events) {
    if (!isInteractionSuggestionEvent(event)) {
      continue;
    }
    const data = event.data && typeof event.data === "object" ? event.data : {};
    const metadata = event.metadata && typeof event.metadata === "object" ? event.metadata : {};
    const advisory = readBooleanField(data["advisory"] ?? metadata["advisory"]);
    const noExecution = readBooleanField(
      data["__no_execution"] ?? metadata["__no_execution"] ?? data["no_execution"] ?? metadata["no_execution"],
    );
    if (advisory !== true || noExecution !== true) {
      continue;
    }
    const confidenceRaw = readNumberField(data["confidence"] ?? metadata["confidence"]);
    const confidence = confidenceRaw === null ? 0 : Math.max(0, Math.min(1, confidenceRaw));
    const stepIndex = readNumberField(metadata["step_index"] ?? data["step_index"]);
    const suggestion: InteractionSuggestion = {
      action: readStringField(data["action"] ?? metadata["action"]).toLowerCase(),
      targetLabel: readStringField(data["target_label"] ?? metadata["target_label"]),
      highlightText: readStringField(data["highlight_text"] ?? metadata["highlight_text"] ?? data["highlightText"] ?? metadata["highlightText"]) || undefined,
      cursorX: clampPercent(readNumberField(data["cursor_x"] ?? metadata["cursor_x"])),
      cursorY: clampPercent(readNumberField(data["cursor_y"] ?? metadata["cursor_y"])),
      scrollPercent: clampPercent(
        readNumberField(data["scroll_percent"] ?? metadata["scroll_percent"]),
      ),
      confidence,
      reason: readStringField(data["reason"] ?? metadata["reason"]),
      advisory: true,
      noExecution: true,
      source: "llm_suggestion",
      stepIndex,
      eventId: String(event.event_id || "").trim(),
      runId: String(event.run_id || "").trim(),
    };
    const key = normalizeSuggestionKey({
      runId: suggestion.runId,
      stepIndex: suggestion.stepIndex,
      fallbackEventId: suggestion.eventId,
    });
    if (!key) {
      continue;
    }
    const entries = layer.get(key) ?? [];
    entries.push(suggestion);
    layer.set(key, entries);
  }
  return layer;
}

function mergeSuggestion(
  deterministicCursorX: number | null,
  deterministicCursorY: number | null,
  deterministicAction: string,
  deterministicTargetLabel: string,
  deterministicScrollPercent: number | null,
  suggestions: InteractionSuggestion[] | null,
  confidenceThreshold: number = INTERACTION_SUGGESTION_MIN_CONFIDENCE,
  syntheticFallbackCursor: { x: number | null; y: number | null } | null = null,
  onRejected?: (reason: InteractionSuggestionRejectReason, suggestion: InteractionSuggestion) => void,
): MergedInteractionState {
  const suggestion = suggestions
    ? [...suggestions].sort((a, b) => b.confidence - a.confidence)[0] ?? null
    : null;

  if (deterministicCursorX !== null && deterministicCursorY !== null) {
    return {
      cursorX: deterministicCursorX,
      cursorY: deterministicCursorY,
      action: String(deterministicAction || "").trim().toLowerCase(),
      targetLabel: String(deterministicTargetLabel || "").trim(),
      scrollPercent: clampPercent(deterministicScrollPercent),
      source: "deterministic",
      suggestionConfidence: null,
      suggestionReason: null,
    };
  }

  if (suggestion) {
    if (suggestion.advisory !== true || suggestion.noExecution !== true) {
      onRejected?.("missing_advisory_guard", suggestion);
    } else if (suggestion.confidence < confidenceThreshold) {
      onRejected?.("low_confidence", suggestion);
    } else {
      const mergedAction =
        String(deterministicAction || "").trim().toLowerCase() || String(suggestion.action || "").trim().toLowerCase();
      const deterministicScroll = clampPercent(deterministicScrollPercent);
      const suggestionScroll =
        mergedAction === "scroll" ? clampPercent(suggestion.scrollPercent) : null;
      return {
        cursorX: suggestion.cursorX,
        cursorY: suggestion.cursorY,
        action: mergedAction,
        targetLabel:
          String(deterministicTargetLabel || "").trim() || String(suggestion.targetLabel || "").trim(),
        scrollPercent: deterministicScroll ?? suggestionScroll,
        source: "suggested",
        suggestionConfidence: suggestion.confidence,
        suggestionReason: suggestion.reason || null,
      };
    }
  }

  const fallbackX = clampPercent(syntheticFallbackCursor?.x ?? null);
  const fallbackY = clampPercent(syntheticFallbackCursor?.y ?? null);
  if (fallbackX !== null && fallbackY !== null) {
    return {
      cursorX: fallbackX,
      cursorY: fallbackY,
      action: String(deterministicAction || "").trim().toLowerCase(),
      targetLabel: String(deterministicTargetLabel || "").trim(),
      scrollPercent: clampPercent(deterministicScrollPercent),
      source: "synthetic_fallback",
      suggestionConfidence: null,
      suggestionReason: null,
    };
  }

  return {
    cursorX: null,
    cursorY: null,
    action: String(deterministicAction || "").trim().toLowerCase(),
    targetLabel: String(deterministicTargetLabel || "").trim(),
    scrollPercent: clampPercent(deterministicScrollPercent),
    source: "none",
    suggestionConfidence: null,
    suggestionReason: null,
  };
}

export {
  extractSuggestionLayer,
  INTERACTION_SUGGESTION_MIN_CONFIDENCE,
  isInteractionSuggestionEvent,
  mergeSuggestion,
  suggestionLookupKeyForEvent,
};
export type {
  InteractionSuggestion,
  InteractionSuggestionRejectReason,
  MergedInteractionSource,
  MergedInteractionState,
};
