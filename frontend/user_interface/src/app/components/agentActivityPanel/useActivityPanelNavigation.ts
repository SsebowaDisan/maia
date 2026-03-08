import { useEffect, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import type { AgentActivityEvent } from "../../types";
import { normalizeTokenList, readEventString, readEventStringList } from "./eventTokens";

type WorkGraphJumpTarget = {
  graphNodeIds?: string[];
  sceneRefs?: string[];
  eventRefs?: string[];
  eventIndexStart?: number | null;
  eventIndexEnd?: number | null;
  nonce?: string;
};

type UseJumpTargetSelectionParams = {
  jumpTarget: WorkGraphJumpTarget | null;
  orderedEvents: AgentActivityEvent[];
  setCursor: Dispatch<SetStateAction<number>>;
  setIsPlaying: Dispatch<SetStateAction<boolean>>;
};

function useJumpTargetSelection({
  jumpTarget,
  orderedEvents,
  setCursor,
  setIsPlaying,
}: UseJumpTargetSelectionParams) {
  useEffect(() => {
    if (!jumpTarget || !orderedEvents.length) {
      return;
    }
    const targetGraphNodeIds = normalizeTokenList(jumpTarget.graphNodeIds);
    const targetSceneRefs = normalizeTokenList(jumpTarget.sceneRefs);
    const targetEventRefs = normalizeTokenList(jumpTarget.eventRefs);
    if (!targetGraphNodeIds.length && !targetSceneRefs.length && !targetEventRefs.length) {
      return;
    }

    let matchedIndex = -1;
    for (let index = orderedEvents.length - 1; index >= 0; index -= 1) {
      const event = orderedEvents[index];
      const eventId = String(event.event_id || "").trim().toLowerCase();
      const graphNodeId = readEventString(event, "graph_node_id").toLowerCase();
      const sceneRef = readEventString(event, "scene_ref").toLowerCase();
      const graphNodeIds = readEventStringList(event, "graph_node_ids");
      const sceneRefs = readEventStringList(event, "scene_refs");
      const eventRefs = readEventStringList(event, "event_refs");
      const byEventRef = targetEventRefs.some((ref) => ref === eventId || eventRefs.includes(ref));
      const byGraphNode =
        targetGraphNodeIds.some((ref) => ref === graphNodeId) ||
        targetGraphNodeIds.some((ref) => graphNodeIds.includes(ref));
      const bySceneRef =
        targetSceneRefs.some((ref) => ref === sceneRef) ||
        targetSceneRefs.some((ref) => sceneRefs.includes(ref));
      if (byEventRef || byGraphNode || bySceneRef) {
        matchedIndex = index;
        break;
      }
    }
    if (matchedIndex < 0) {
      return;
    }
    setCursor(matchedIndex);
    setIsPlaying(false);
  }, [jumpTarget?.nonce, orderedEvents, setCursor, setIsPlaying]);
}

type UseOverlayKeyboardShortcutsParams = {
  isFullscreenViewer: boolean;
  isCinemaMode: boolean;
  streaming: boolean;
  orderedEventsLength: number;
  setIsFullscreenViewer: Dispatch<SetStateAction<boolean>>;
  setIsCinemaMode: Dispatch<SetStateAction<boolean>>;
  setIsPlaying: Dispatch<SetStateAction<boolean>>;
  setCursor: Dispatch<SetStateAction<number>>;
};

function useOverlayKeyboardShortcuts({
  isFullscreenViewer,
  isCinemaMode,
  streaming,
  orderedEventsLength,
  setIsFullscreenViewer,
  setIsCinemaMode,
  setIsPlaying,
  setCursor,
}: UseOverlayKeyboardShortcutsParams) {
  useEffect(() => {
    if (!isFullscreenViewer && !isCinemaMode) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsFullscreenViewer(false);
        setIsCinemaMode(false);
      }
      if (!isCinemaMode) return;
      if (event.key === " " || event.code === "Space") {
        event.preventDefault();
        if (!streaming) setIsPlaying((prev) => !prev);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        setCursor((prev) => Math.max(0, prev - 1));
        setIsPlaying(false);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        setCursor((prev) => Math.min(orderedEventsLength - 1, prev + 1));
        setIsPlaying(false);
      }
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [
    isFullscreenViewer,
    isCinemaMode,
    streaming,
    orderedEventsLength,
    setIsFullscreenViewer,
    setIsCinemaMode,
    setIsPlaying,
    setCursor,
  ]);
}

type UseAutoScrollTimelineParams = {
  streaming: boolean;
  orderedEventsLength: number;
  activeEventId: string | undefined;
  listRef: MutableRefObject<HTMLDivElement | null>;
};

function useAutoScrollTimeline({
  streaming,
  orderedEventsLength,
  activeEventId,
  listRef,
}: UseAutoScrollTimelineParams) {
  useEffect(() => {
    if (!streaming) {
      return;
    }
    const node = listRef.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [streaming, orderedEventsLength, activeEventId, listRef]);
}

export { useAutoScrollTimeline, useJumpTargetSelection, useOverlayKeyboardShortcuts };
