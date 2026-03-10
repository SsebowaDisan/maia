import { useEffect, useRef, useState } from "react";

function useSceneSurfaceTransition({
  sceneSurfaceKey,
  sceneSurfaceLabel,
  streaming,
}: {
  sceneSurfaceKey: string;
  sceneSurfaceLabel: string;
  streaming: boolean;
}): {
  stableSceneSurfaceKey: string;
  stableSceneSurfaceLabel: string;
  sceneTransitionLabel: string;
} {
  const [stableSceneSurfaceKey, setStableSceneSurfaceKey] = useState(sceneSurfaceKey);
  const [stableSceneSurfaceLabel, setStableSceneSurfaceLabel] = useState(sceneSurfaceLabel);
  const [sceneTransitionLabel, setSceneTransitionLabel] = useState("");

  const sceneTransitionTimerRef = useRef<number | null>(null);
  const sceneSurfaceCommitTimerRef = useRef<number | null>(null);
  const previousSceneSurfaceRef = useRef("");

  useEffect(() => {
    const reduceMotion =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!streaming) {
      setStableSceneSurfaceKey(sceneSurfaceKey);
      setStableSceneSurfaceLabel(sceneSurfaceLabel);
      return;
    }
    if (sceneSurfaceKey === stableSceneSurfaceKey) {
      return;
    }
    if (sceneSurfaceCommitTimerRef.current) {
      window.clearTimeout(sceneSurfaceCommitTimerRef.current);
      sceneSurfaceCommitTimerRef.current = null;
    }
    if (reduceMotion) {
      setStableSceneSurfaceKey(sceneSurfaceKey);
      setStableSceneSurfaceLabel(sceneSurfaceLabel);
      return;
    }
    sceneSurfaceCommitTimerRef.current = window.setTimeout(() => {
      setStableSceneSurfaceKey(sceneSurfaceKey);
      setStableSceneSurfaceLabel(sceneSurfaceLabel);
      sceneSurfaceCommitTimerRef.current = null;
    }, 180);
  }, [sceneSurfaceKey, sceneSurfaceLabel, stableSceneSurfaceKey, streaming]);

  useEffect(() => {
    const reduceMotion =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!streaming) {
      return;
    }
    const previous = previousSceneSurfaceRef.current;
    if (!previous) {
      previousSceneSurfaceRef.current = stableSceneSurfaceKey;
      return;
    }
    if (previous === stableSceneSurfaceKey) {
      return;
    }
    previousSceneSurfaceRef.current = stableSceneSurfaceKey;
    setSceneTransitionLabel(`Switched to ${stableSceneSurfaceLabel}`);
    if (sceneTransitionTimerRef.current) {
      window.clearTimeout(sceneTransitionTimerRef.current);
      sceneTransitionTimerRef.current = null;
    }
    if (reduceMotion) {
      setSceneTransitionLabel("");
      return;
    }
    sceneTransitionTimerRef.current = window.setTimeout(() => {
      setSceneTransitionLabel("");
      sceneTransitionTimerRef.current = null;
    }, 1100);
  }, [stableSceneSurfaceKey, stableSceneSurfaceLabel, streaming]);

  useEffect(
    () => () => {
      if (sceneTransitionTimerRef.current) {
        window.clearTimeout(sceneTransitionTimerRef.current);
        sceneTransitionTimerRef.current = null;
      }
      if (sceneSurfaceCommitTimerRef.current) {
        window.clearTimeout(sceneSurfaceCommitTimerRef.current);
        sceneSurfaceCommitTimerRef.current = null;
      }
    },
    [],
  );

  return {
    stableSceneSurfaceKey,
    stableSceneSurfaceLabel,
    sceneTransitionLabel,
  };
}

export { useSceneSurfaceTransition };
