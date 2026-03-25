import { useCallback, useEffect, useRef, useState, type UIEvent as ReactUIEvent } from "react";

const SCROLL_ICON_SETTLE_MS = 1600;
const SCROLL_TO_LATEST_THRESHOLD_PX = 140;

type UseScrollControlsParams = {
  chatTurnCount: number;
  selectedTurnIndex: number;
  isSending: boolean;
  isActivityStreaming: boolean;
};

export function useScrollControls(params: UseScrollControlsParams) {
  const { chatTurnCount, selectedTurnIndex, isSending, isActivityStreaming } = params;
  const contentScrollRef = useRef<HTMLDivElement | null>(null);
  const scrollIconHideTimeoutRef = useRef<number | null>(null);
  const programmaticScrollRef = useRef(false);
  const programmaticScrollTimerRef = useRef<number | null>(null);
  const [scrollIconSettling, setScrollIconSettling] = useState(false);
  const [scrollIconHovering, setScrollIconHovering] = useState(false);
  const [showScrollToLatest, setShowScrollToLatest] = useState(false);
  const [composerCollapsed, setComposerCollapsed] = useState(false);
  const [composerHovering, setComposerHovering] = useState(false);
  const [composerFocused, setComposerFocused] = useState(false);

  const scrollLatestTurnToTop = useCallback(() => {
    const element = contentScrollRef.current;
    if (!element) {
      return;
    }
    const latestTurnIndex = chatTurnCount - 1;
    const latestTurnNode = element.querySelector<HTMLElement>(
      `[data-turn-index="${String(latestTurnIndex)}"]`,
    );
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false);
    const behavior: ScrollBehavior = prefersReducedMotion ? "auto" : "smooth";
    if (latestTurnNode) {
      latestTurnNode.scrollIntoView({
        behavior,
        block: "start",
        inline: "nearest",
      });
      return;
    }
    element.scrollTo({ top: element.scrollHeight, behavior });
  }, [chatTurnCount]);

  const refreshScrollToLatestVisibility = useCallback(
    (element?: HTMLDivElement | null) => {
      if (programmaticScrollRef.current) {
        return;
      }
      const container = element || contentScrollRef.current;
      if (!container || chatTurnCount === 0) {
        setShowScrollToLatest(false);
        return;
      }
      const distanceToBottom =
        container.scrollHeight - (container.scrollTop + container.clientHeight);
      setShowScrollToLatest(distanceToBottom > SCROLL_TO_LATEST_THRESHOLD_PX);
    },
    [chatTurnCount],
  );

  const scrollToLatestMessage = useCallback(() => {
    const element = contentScrollRef.current;
    if (!element) {
      return;
    }
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      (window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false);

    programmaticScrollRef.current = true;
    if (programmaticScrollTimerRef.current !== null) {
      window.clearTimeout(programmaticScrollTimerRef.current);
    }
    programmaticScrollTimerRef.current = window.setTimeout(() => {
      programmaticScrollRef.current = false;
      programmaticScrollTimerRef.current = null;
      setComposerCollapsed(false);
      setShowScrollToLatest(false);
    }, prefersReducedMotion ? 50 : 600);

    element.scrollTo({
      top: element.scrollHeight,
      behavior: prefersReducedMotion ? "auto" : "smooth",
    });
  }, []);

  const handleContentScroll = useCallback((event: ReactUIEvent<HTMLDivElement>) => {
    const container = event.currentTarget;
    setScrollIconSettling(true);
    refreshScrollToLatestVisibility(container);
    if (!composerFocused && !programmaticScrollRef.current && !isActivityStreaming) {
      const distanceToBottom =
        container.scrollHeight - (container.scrollTop + container.clientHeight);
      setComposerCollapsed(distanceToBottom > SCROLL_TO_LATEST_THRESHOLD_PX);
    }
    if (scrollIconHideTimeoutRef.current !== null) {
      window.clearTimeout(scrollIconHideTimeoutRef.current);
    }
    scrollIconHideTimeoutRef.current = window.setTimeout(() => {
      setScrollIconSettling(false);
      scrollIconHideTimeoutRef.current = null;
    }, SCROLL_ICON_SETTLE_MS);
  }, [composerFocused, isActivityStreaming, refreshScrollToLatestVisibility]);

  useEffect(
    () => () => {
      if (scrollIconHideTimeoutRef.current !== null) {
        window.clearTimeout(scrollIconHideTimeoutRef.current);
      }
      if (programmaticScrollTimerRef.current !== null) {
        window.clearTimeout(programmaticScrollTimerRef.current);
      }
    },
    [],
  );

  useEffect(() => {
    if (isActivityStreaming || isSending) {
      setComposerCollapsed(true);
      setComposerHovering(false);
      setComposerFocused(false);
      return;
    }
    setComposerCollapsed(false);
  }, [isActivityStreaming, isSending]);

  useEffect(() => {
    if (!isSending || showScrollToLatest) {
      return;
    }
    const rafId = window.requestAnimationFrame(() => {
      scrollLatestTurnToTop();
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [isSending, isActivityStreaming, scrollLatestTurnToTop, showScrollToLatest]);

  useEffect(() => {
    const rafId = window.requestAnimationFrame(() => {
      refreshScrollToLatestVisibility();
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [chatTurnCount, isSending, isActivityStreaming, selectedTurnIndex, refreshScrollToLatestVisibility]);

  useEffect(() => {
    const container = contentScrollRef.current;
    if (!container || composerFocused || programmaticScrollRef.current || isActivityStreaming) {
      return;
    }
    const distanceToBottom =
      container.scrollHeight - (container.scrollTop + container.clientHeight);
    setComposerCollapsed(distanceToBottom > SCROLL_TO_LATEST_THRESHOLD_PX);
  }, [chatTurnCount, composerFocused, isActivityStreaming, selectedTurnIndex]);

  return {
    contentScrollRef,
    scrollIconSettling,
    scrollIconHovering,
    showScrollToLatest,
    composerCollapsed,
    composerHovering,
    composerFocused,
    setScrollIconHovering,
    setComposerHovering,
    setComposerFocused,
    setComposerCollapsed,
    handleContentScroll,
    scrollToLatestMessage,
  };
}
