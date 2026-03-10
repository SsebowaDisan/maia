import { useEffect, useRef, useState } from "react";
import type { AgentActivityEvent } from "../../types";
import { buildSceneNarrative } from "./sceneNarrative";

function useSceneTextTyping(activeEvent: AgentActivityEvent | null): string {
  const [sceneText, setSceneText] = useState("");
  const typeTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!activeEvent) {
      setSceneText("");
      return;
    }

    const targetText = buildSceneNarrative(activeEvent) || "Processing step...";
    const reduceMotion =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      setSceneText(targetText);
      return;
    }
    setSceneText("");

    let index = 0;
    if (typeTimerRef.current) {
      window.clearInterval(typeTimerRef.current);
      typeTimerRef.current = null;
    }

    typeTimerRef.current = window.setInterval(() => {
      index += 1;
      setSceneText(targetText.slice(0, index));
      if (index >= targetText.length && typeTimerRef.current) {
        window.clearInterval(typeTimerRef.current);
        typeTimerRef.current = null;
      }
    }, 8);

    return () => {
      if (typeTimerRef.current) {
        window.clearInterval(typeTimerRef.current);
        typeTimerRef.current = null;
      }
    };
  }, [activeEvent?.event_id]);

  return sceneText;
}

export { useSceneTextTyping };
