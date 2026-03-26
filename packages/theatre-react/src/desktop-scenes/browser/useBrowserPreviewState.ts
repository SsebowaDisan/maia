import { useEffect, useMemo, useRef, useState } from "react";
import { useBrowserPageQueue } from "./useBrowserPageQueue";
import { useBrowserSceneScrollState } from "./useBrowserSceneScrollState";
import { FRAME_VIEWPORT_BASE_HEIGHT, FRAME_VIEWPORT_BASE_WIDTH, shouldPreferProxyForUrl } from "./common";

type UseBrowserPreviewStateOptions = {
  browserUrl: string;
  openedPages: Array<{ url: string; title: string; pageIndex: number | null; reviewed: boolean }>;
  pageIndex: number | null;
  snapshotUrl: string;
  previewHint: string;
  shouldAnnotatePreview: boolean;
  blockedSignal: boolean;
  canRenderLiveUrl: boolean;
  scrollPercent: number | null;
  actionIndicatesScroll: boolean;
  eventIndicatesScroll: boolean;
  hasDirectionalScroll: boolean;
  normalizedAction: string;
  normalizedScrollDirection: string;
  readingMode: boolean;
  onSnapshotError?: () => void;
  computerUseScreenshotUrl: string;
  computerUseStreamUrl: string;
};

function useBrowserPreviewState(options: UseBrowserPreviewStateOptions) {
  const [snapshotErrored, setSnapshotErrored] = useState(false);
  const [snapshotReady, setSnapshotReady] = useState(false);
  const [crossFadeUrl, setCrossFadeUrl] = useState("");
  const [proxyLoaded, setProxyLoaded] = useState(false);
  const [frameScrollPercent, setFrameScrollPercent] = useState<number | null>(null);
  const [frameScale, setFrameScale] = useState(1);
  const [frameVirtualHeight, setFrameVirtualHeight] = useState(FRAME_VIEWPORT_BASE_HEIGHT);
  const prevSnapshotUrlRef = useRef<string>(options.computerUseScreenshotUrl || options.snapshotUrl);
  const frameRef = useRef<HTMLIFrameElement | null>(null);
  const frameViewportRef = useRef<HTMLDivElement | null>(null);
  const frameScrollObserverCleanupRef = useRef<(() => void) | null>(null);
  const lastTelemetryScrollPercentRef = useRef<number | null>(null);
  const frameScrollAnimationRef = useRef<number | null>(null);

  const { activePageUrl } = useBrowserPageQueue({
    browserUrl: options.browserUrl,
    openedPages: options.openedPages,
    pageIndex: options.pageIndex,
  });
  const resolvedPageUrl = options.computerUseStreamUrl || activePageUrl;
  const sceneSnapshotUrl = options.computerUseScreenshotUrl || options.snapshotUrl;

  const proxyPreviewUrl = useMemo(() => {
    const source = String(resolvedPageUrl || "").trim();
    if (!source || (!source.startsWith("http://") && !source.startsWith("https://"))) {
      return "";
    }
    const params = new URLSearchParams();
    params.set("url", source);
    if (options.shouldAnnotatePreview && options.previewHint) {
      params.set("highlight", options.previewHint);
      params.set("claim", options.previewHint);
      params.set("question", options.previewHint);
    }
    params.set("viewport", "desktop");
    params.set("highlight_strategy", "heuristic");
    return `/api/web/preview?${params.toString()}`;
  }, [options.previewHint, options.shouldAnnotatePreview, resolvedPageUrl]);

  const shouldUseProxyPreview =
    Boolean(proxyPreviewUrl) &&
    (options.blockedSignal ||
      options.shouldAnnotatePreview ||
      !options.canRenderLiveUrl ||
      shouldPreferProxyForUrl(resolvedPageUrl));
  const preferPreviewProxy = shouldUseProxyPreview && (!sceneSnapshotUrl || snapshotErrored);
  const showSnapshotPrimary = Boolean(sceneSnapshotUrl) && !snapshotErrored && !preferPreviewProxy;
  const frameUrl = useMemo(() => {
    if (shouldUseProxyPreview && proxyPreviewUrl) {
      return proxyPreviewUrl;
    }
    return resolvedPageUrl;
  }, [proxyPreviewUrl, resolvedPageUrl, shouldUseProxyPreview]);
  const showFramePreview = Boolean(frameUrl);

  useEffect(() => {
    if (!sceneSnapshotUrl || sceneSnapshotUrl === prevSnapshotUrlRef.current) {
      return;
    }
    if (prevSnapshotUrlRef.current) {
      setCrossFadeUrl(prevSnapshotUrlRef.current);
    }
    setSnapshotReady(false);
    setSnapshotErrored(false);
  }, [sceneSnapshotUrl]);

  const handleSnapshotLoad = () => {
    setSnapshotReady(true);
    prevSnapshotUrlRef.current = sceneSnapshotUrl;
    window.setTimeout(() => setCrossFadeUrl(""), 400);
  };

  useEffect(() => {
    setProxyLoaded(false);
    setFrameScrollPercent(null);
    if (frameScrollObserverCleanupRef.current) {
      frameScrollObserverCleanupRef.current();
      frameScrollObserverCleanupRef.current = null;
    }
  }, [frameUrl]);

  useEffect(
    () => () => {
      if (frameScrollObserverCleanupRef.current) {
        frameScrollObserverCleanupRef.current();
        frameScrollObserverCleanupRef.current = null;
      }
      if (frameScrollAnimationRef.current !== null) {
        window.cancelAnimationFrame(frameScrollAnimationRef.current);
        frameScrollAnimationRef.current = null;
      }
    },
    [],
  );

  useEffect(() => {
    const viewport = frameViewportRef.current;
    if (!viewport) {
      return;
    }
    const updateScale = () => {
      const rect = viewport.getBoundingClientRect();
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      const nextScale = Math.max(0.25, Math.min(1, width / FRAME_VIEWPORT_BASE_WIDTH));
      const nextVirtualHeight = Math.max(FRAME_VIEWPORT_BASE_HEIGHT, Math.ceil(height / nextScale));
      setFrameScale((previous) => (Math.abs(previous - nextScale) >= 0.002 ? nextScale : previous));
      setFrameVirtualHeight((previous) =>
        Math.abs(previous - nextVirtualHeight) >= 2 ? nextVirtualHeight : previous,
      );
    };
    updateScale();
    const observer = new ResizeObserver(updateScale);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  const bindFrameScrollObserver = () => {
    if (frameScrollObserverCleanupRef.current) {
      frameScrollObserverCleanupRef.current();
      frameScrollObserverCleanupRef.current = null;
    }
    const frame = frameRef.current;
    if (!frame) {
      return;
    }
    try {
      const computePercent = () => {
        try {
          const liveFrame = frameRef.current;
          const frameWindow = liveFrame?.contentWindow;
          const frameDocument = frameWindow?.document;
          if (!frameWindow || !frameDocument) {
            setFrameScrollPercent(null);
            return;
          }
          const doc = frameDocument.documentElement;
          const body = frameDocument.body;
          const scrollTop = Number(frameWindow.scrollY || doc?.scrollTop || body?.scrollTop || 0);
          const scrollHeight = Number(doc?.scrollHeight || body?.scrollHeight || 0);
          const viewportHeight = Number(frameWindow.innerHeight || doc?.clientHeight || 0);
          const maxScrollable = Math.max(0, scrollHeight - viewportHeight);
          if (maxScrollable <= 0) {
            setFrameScrollPercent(0);
            return;
          }
          const nextPercent = Math.max(0, Math.min(100, (scrollTop / maxScrollable) * 100));
          setFrameScrollPercent(nextPercent);
        } catch {
          setFrameScrollPercent(null);
        }
      };
      const frameWindow = frame.contentWindow;
      if (!frameWindow) {
        return;
      }
      frameWindow.addEventListener("scroll", computePercent, { passive: true });
      frameWindow.addEventListener("hashchange", computePercent);
      frameWindow.addEventListener("popstate", computePercent);
      frame.addEventListener("load", computePercent);
      computePercent();
      const syncTimer = window.setTimeout(computePercent, 150);
      const syncInterval = window.setInterval(computePercent, 900);
      frameScrollObserverCleanupRef.current = () => {
        frameWindow.removeEventListener("scroll", computePercent);
        frameWindow.removeEventListener("hashchange", computePercent);
        frameWindow.removeEventListener("popstate", computePercent);
        frame.removeEventListener("load", computePercent);
        window.clearTimeout(syncTimer);
        window.clearInterval(syncInterval);
      };
    } catch {
      setFrameScrollPercent(null);
    }
  };

  const canProgrammaticallyScrollFrame = showFramePreview && shouldUseProxyPreview && !showSnapshotPrimary;

  const scrollFrameToPercent = (percent: number): boolean => {
    if (!canProgrammaticallyScrollFrame) {
      return false;
    }
    const frame = frameRef.current;
    if (!frame) {
      return false;
    }
    try {
      const frameWindow = frame.contentWindow;
      const frameDocument = frameWindow?.document;
      if (!frameWindow || !frameDocument) {
        return false;
      }
      const doc = frameDocument.documentElement;
      const body = frameDocument.body;
      const scrollHeight = Number(doc?.scrollHeight || body?.scrollHeight || 0);
      const viewportHeight = Number(frameWindow.innerHeight || doc?.clientHeight || 0);
      const maxScrollable = Math.max(0, scrollHeight - viewportHeight);
      if (maxScrollable <= 0) {
        return false;
      }
      const nextPercent = Math.max(0, Math.min(100, Number(percent)));
      const targetTop = (nextPercent / 100) * maxScrollable;
      const currentTop = Number(frameWindow.scrollY || doc?.scrollTop || body?.scrollTop || 0);
      if (frameScrollAnimationRef.current !== null) {
        window.cancelAnimationFrame(frameScrollAnimationRef.current);
        frameScrollAnimationRef.current = null;
      }
      const distance = Math.abs(targetTop - currentTop);
      const durationMs = Math.max(900, Math.min(2200, 700 + distance * 0.6));
      const startAt = performance.now();
      const easeInOutCubic = (t: number) =>
        t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      const animateScroll = (now: number) => {
        const progress = Math.max(0, Math.min(1, (now - startAt) / durationMs));
        const eased = easeInOutCubic(progress);
        const nextTop = currentTop + (targetTop - currentTop) * eased;
        frameWindow.scrollTo(0, nextTop);
        if (progress < 1) {
          frameScrollAnimationRef.current = window.requestAnimationFrame(animateScroll);
          return;
        }
        frameScrollAnimationRef.current = null;
      };
      frameScrollAnimationRef.current = window.requestAnimationFrame(animateScroll);
      setFrameScrollPercent(nextPercent);
      return true;
    } catch {
      return false;
    }
  };

  useEffect(() => {
    if (!canProgrammaticallyScrollFrame || !proxyLoaded) {
      lastTelemetryScrollPercentRef.current = null;
      return;
    }
    if (typeof options.scrollPercent !== "number" || !Number.isFinite(options.scrollPercent)) {
      return;
    }
    const nextPercent = Math.max(0, Math.min(100, Number(options.scrollPercent)));
    const previousPercent = lastTelemetryScrollPercentRef.current;
    if (previousPercent !== null && Math.abs(previousPercent - nextPercent) < 1.5) {
      return;
    }
    const currentFramePercent =
      typeof frameScrollPercent === "number" && Number.isFinite(frameScrollPercent)
        ? Math.max(0, Math.min(100, frameScrollPercent))
        : null;
    if (currentFramePercent !== null && Math.abs(currentFramePercent - nextPercent) < 1.5) {
      lastTelemetryScrollPercentRef.current = nextPercent;
      return;
    }
    const sync = window.setTimeout(() => {
      if (scrollFrameToPercent(nextPercent)) {
        lastTelemetryScrollPercentRef.current = nextPercent;
      }
    }, 40);
    return () => window.clearTimeout(sync);
  }, [canProgrammaticallyScrollFrame, frameScrollPercent, options.scrollPercent, proxyLoaded]);

  const resolvedScrollPercent = canProgrammaticallyScrollFrame
    ? frameScrollPercent ?? options.scrollPercent
    : options.scrollPercent;
  const { navigationHint, effectiveScrollPercent, handleScrollSelect } = useBrowserSceneScrollState({
    activePageUrl: resolvedPageUrl,
    actionIndicatesScroll: options.actionIndicatesScroll,
    eventIndicatesScroll: options.eventIndicatesScroll,
    hasDirectionalScroll: options.hasDirectionalScroll,
    normalizedAction: options.normalizedAction,
    normalizedScrollDirection: options.normalizedScrollDirection,
    readingMode: options.readingMode,
    scrollPercent: resolvedScrollPercent,
    allowSyntheticScroll: false,
    canSelect: canProgrammaticallyScrollFrame,
    onSelectPercent: scrollFrameToPercent,
  });

  const viewportScrollOffsetPx = useMemo(() => {
    if (canProgrammaticallyScrollFrame) {
      return 0;
    }
    if (typeof effectiveScrollPercent !== "number" || !Number.isFinite(effectiveScrollPercent)) {
      return 0;
    }
    const viewportHeight = frameViewportRef.current?.clientHeight || 0;
    if (viewportHeight <= 0) {
      return 0;
    }
    const travelDistance = Math.max(36, Math.min(260, viewportHeight * 0.42));
    return -1 * (Math.max(0, Math.min(100, effectiveScrollPercent)) / 100) * travelDistance;
  }, [canProgrammaticallyScrollFrame, effectiveScrollPercent]);

  const handleSnapshotError = () => {
    setSnapshotReady(false);
    setSnapshotErrored(true);
    options.onSnapshotError?.();
  };

  const handleFrameLoad = () => {
    setProxyLoaded(true);
    if (shouldUseProxyPreview) {
      bindFrameScrollObserver();
    } else {
      setFrameScrollPercent(null);
    }
  };

  return {
    canProgrammaticallyScrollFrame,
    crossFadeUrl,
    effectiveScrollPercent,
    frameRef,
    frameScale,
    frameUrl,
    frameViewportRef,
    frameVirtualHeight,
    handleFrameLoad,
    handleScrollSelect,
    handleSnapshotError,
    handleSnapshotLoad,
    navigationHint,
    preferPreviewProxy,
    proxyLoaded,
    resolvedPageUrl,
    sceneSnapshotUrl,
    shouldUseProxyPreview,
    showFramePreview,
    showSnapshotPrimary,
    snapshotReady,
    viewportScrollOffsetPx,
  };
}

export { useBrowserPreviewState };
