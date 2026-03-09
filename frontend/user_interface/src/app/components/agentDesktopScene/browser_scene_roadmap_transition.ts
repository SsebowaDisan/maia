import { useEffect, useRef, useState } from "react";

type UseRoadmapTransitionOptions = {
  roadmapStepCount: number;
  roadmapActiveIndex: number;
  activeEventType: string;
};

function isRoadmapTriggerEvent(eventType: string): boolean {
  const normalized = String(eventType || "").trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return (
    normalized === "plan_ready" ||
    normalized === "plan_candidate" ||
    normalized === "plan_refined" ||
    normalized === "llm.plan_step" ||
    normalized.startsWith("llm.plan_") ||
    normalized.startsWith("plan_") ||
    normalized === "tool_completed"
  );
}

function useRoadmapTransition({
  roadmapStepCount,
  roadmapActiveIndex,
  activeEventType,
}: UseRoadmapTransitionOptions): boolean {
  const [roadmapVisible, setRoadmapVisible] = useState(false);
  const hideTimerRef = useRef<number | null>(null);
  const previousStepCountRef = useRef(roadmapStepCount);
  const previousActiveIndexRef = useRef(roadmapActiveIndex);

  useEffect(() => {
    if (roadmapStepCount <= 0) {
      setRoadmapVisible(false);
      if (hideTimerRef.current !== null) {
        window.clearTimeout(hideTimerRef.current);
        hideTimerRef.current = null;
      }
      previousStepCountRef.current = roadmapStepCount;
      previousActiveIndexRef.current = roadmapActiveIndex;
      return;
    }

    const planChanged = roadmapStepCount !== previousStepCountRef.current;
    const progressChanged = roadmapActiveIndex !== previousActiveIndexRef.current;
    const byEventType = isRoadmapTriggerEvent(activeEventType);
    previousStepCountRef.current = roadmapStepCount;
    previousActiveIndexRef.current = roadmapActiveIndex;
    if (!planChanged && !progressChanged && !byEventType) {
      return;
    }

    setRoadmapVisible(true);
    if (hideTimerRef.current !== null) {
      window.clearTimeout(hideTimerRef.current);
    }
    const holdMs = progressChanged ? 1700 : 1400;
    hideTimerRef.current = window.setTimeout(() => {
      setRoadmapVisible(false);
      hideTimerRef.current = null;
    }, holdMs);
  }, [activeEventType, roadmapActiveIndex, roadmapStepCount]);

  useEffect(
    () => () => {
      if (hideTimerRef.current !== null) {
        window.clearTimeout(hideTimerRef.current);
        hideTimerRef.current = null;
      }
    },
    [],
  );

  return roadmapVisible;
}

export { useRoadmapTransition };
