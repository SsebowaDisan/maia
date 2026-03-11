import { useEffect, useRef, useState } from "react";

function shortHostLabel(url: string): string {
  try {
    const host = new URL(String(url || "").trim()).hostname.replace(/^www\./, "");
    return host || "new page";
  } catch {
    return "new page";
  }
}

type BrowserSceneScrollStateArgs = {
  activePageUrl: string;
  actionIndicatesScroll: boolean;
  eventIndicatesScroll: boolean;
  hasDirectionalScroll: boolean;
  normalizedAction: string;
  normalizedScrollDirection: string;
  readingMode: boolean;
  scrollPercent: number | null;
  allowSyntheticScroll?: boolean;
  canSelect?: boolean;
  onSelectPercent?: (percent: number) => boolean | void;
};

function useBrowserSceneScrollState({
  activePageUrl,
  actionIndicatesScroll,
  eventIndicatesScroll,
  hasDirectionalScroll,
  normalizedAction,
  normalizedScrollDirection,
  readingMode,
  scrollPercent,
  allowSyntheticScroll = false,
  canSelect = false,
  onSelectPercent,
}: BrowserSceneScrollStateArgs): {
  navigationHint: string;
  effectiveScrollPercent: number | null;
  handleScrollSelect: (percent: number) => void;
} {
  const [navigationHint, setNavigationHint] = useState("");
  const boundaryHintRef = useRef<"start" | "end" | null>(null);
  const boundaryHintTimeoutRef = useRef<number | null>(null);
  const previousPageUrlRef = useRef(activePageUrl);

  const [syntheticScrollPercent, setSyntheticScrollPercent] = useState<number | null>(null);
  const syntheticTickRef = useRef(0);
  const syntheticIntervalRef = useRef<number | null>(null);
  const syntheticDirectionRef = useRef(1);
  const effectiveScrollPercent = syntheticScrollPercent ?? scrollPercent;

  useEffect(() => {
    const nextUrl = String(activePageUrl || "").trim();
    const previousUrl = String(previousPageUrlRef.current || "").trim();
    previousPageUrlRef.current = nextUrl;
    if (!nextUrl || !previousUrl || nextUrl === previousUrl) {
      return;
    }
    boundaryHintRef.current = null;
    if (boundaryHintTimeoutRef.current !== null) {
      window.clearTimeout(boundaryHintTimeoutRef.current);
      boundaryHintTimeoutRef.current = null;
    }
    setNavigationHint(`Navigating to ${shortHostLabel(nextUrl)}`);
    const timer = window.setTimeout(() => setNavigationHint(""), 1400);
    return () => window.clearTimeout(timer);
  }, [activePageUrl]);

  useEffect(() => {
    return () => {
      if (boundaryHintTimeoutRef.current !== null) {
        window.clearTimeout(boundaryHintTimeoutRef.current);
        boundaryHintTimeoutRef.current = null;
      }
      if (syntheticIntervalRef.current !== null) {
        window.clearInterval(syntheticIntervalRef.current);
        syntheticIntervalRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (normalizedScrollDirection === "up") {
      syntheticDirectionRef.current = -1;
      return;
    }
    if (normalizedScrollDirection === "down") {
      syntheticDirectionRef.current = 1;
    }
  }, [normalizedScrollDirection]);

  useEffect(() => {
    if (syntheticIntervalRef.current !== null) {
      window.clearInterval(syntheticIntervalRef.current);
      syntheticIntervalRef.current = null;
    }
    if (scrollPercent !== null) {
      setSyntheticScrollPercent(null);
      return;
    }
    if (!allowSyntheticScroll) {
      setSyntheticScrollPercent(null);
      return;
    }
    const shouldSimulate =
      actionIndicatesScroll ||
      eventIndicatesScroll ||
      hasDirectionalScroll ||
      normalizedAction === "navigate" ||
      normalizedAction === "extract" ||
      normalizedAction === "verify" ||
      readingMode;
    if (!shouldSimulate) {
      setSyntheticScrollPercent(null);
      return;
    }
    if (syntheticTickRef.current <= 0 || syntheticTickRef.current >= 100) {
      syntheticTickRef.current = normalizedScrollDirection === "up" ? 84 : 16;
    }
    setSyntheticScrollPercent(syntheticTickRef.current);
    syntheticIntervalRef.current = window.setInterval(() => {
      const nextTick = syntheticTickRef.current + syntheticDirectionRef.current * 3.5;
      if (syntheticDirectionRef.current > 0) {
        syntheticTickRef.current = Math.min(92, nextTick);
      } else if (syntheticDirectionRef.current < 0) {
        syntheticTickRef.current = Math.max(8, nextTick);
      } else {
        syntheticTickRef.current = Math.max(8, Math.min(92, nextTick));
      }
      setSyntheticScrollPercent(syntheticTickRef.current);
    }, 140);
    return () => {
      if (syntheticIntervalRef.current !== null) {
        window.clearInterval(syntheticIntervalRef.current);
        syntheticIntervalRef.current = null;
      }
    };
  }, [
    actionIndicatesScroll,
    allowSyntheticScroll,
    eventIndicatesScroll,
    hasDirectionalScroll,
    normalizedAction,
    normalizedScrollDirection,
    readingMode,
    scrollPercent,
  ]);

  const handleScrollSelect = (percent: number) => {
    if (!canSelect) {
      return;
    }
    const nextPercent = Number(percent);
    if (!Number.isFinite(nextPercent)) {
      return;
    }
    const normalizedPercent = Math.max(0, Math.min(100, nextPercent));
    const accepted = onSelectPercent ? onSelectPercent(normalizedPercent) : true;
    if (accepted === false) {
      return;
    }
    if (syntheticIntervalRef.current !== null) {
      window.clearInterval(syntheticIntervalRef.current);
      syntheticIntervalRef.current = null;
    }
    syntheticDirectionRef.current = 0;
    syntheticTickRef.current = normalizedPercent;
    setSyntheticScrollPercent(normalizedPercent);
  };

  useEffect(() => {
    if (typeof effectiveScrollPercent !== "number") {
      boundaryHintRef.current = null;
      return;
    }
    const boundary =
      effectiveScrollPercent < 5 ? "start" : effectiveScrollPercent > 95 ? "end" : null;
    if (!boundary) {
      boundaryHintRef.current = null;
      return;
    }
    if (navigationHint) {
      return;
    }
    if (boundaryHintRef.current === boundary) {
      return;
    }
    boundaryHintRef.current = boundary;
    const hintText = boundary === "start" ? "Start of page" : "End of page";
    setNavigationHint(hintText);
    if (boundaryHintTimeoutRef.current !== null) {
      window.clearTimeout(boundaryHintTimeoutRef.current);
    }
    boundaryHintTimeoutRef.current = window.setTimeout(() => {
      setNavigationHint((current) => (current === hintText ? "" : current));
      boundaryHintTimeoutRef.current = null;
    }, 1100);
  }, [effectiveScrollPercent, navigationHint]);

  return { navigationHint, effectiveScrollPercent, handleScrollSelect };
}

export { useBrowserSceneScrollState };
