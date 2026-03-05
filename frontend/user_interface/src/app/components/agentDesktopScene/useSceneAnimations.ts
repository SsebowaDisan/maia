import { useEffect, useRef, useState } from "react";
import type { SceneAnimationState } from "./types";

type TypingProfile = {
  minChunk: number;
  maxChunk: number;
  baseDelayMs: number;
  jitterMs: number;
  punctuationPauseMs: number;
  newlinePauseMs: number;
  wordPauseMs: number;
  cadenceEvery: number;
  cadencePauseMs: number;
};

const DOC_TYPING_PROFILE: TypingProfile = {
  minChunk: 1,
  maxChunk: 4,
  baseDelayMs: 18,
  jitterMs: 16,
  punctuationPauseMs: 80,
  newlinePauseMs: 130,
  wordPauseMs: 22,
  cadenceEvery: 42,
  cadencePauseMs: 56,
};

const SHEET_TYPING_PROFILE: TypingProfile = {
  minChunk: 1,
  maxChunk: 3,
  baseDelayMs: 26,
  jitterMs: 24,
  punctuationPauseMs: 70,
  newlinePauseMs: 170,
  wordPauseMs: 28,
  cadenceEvery: 28,
  cadencePauseMs: 68,
};

function deterministicNoise(seed: number): number {
  const value = Math.sin((seed + 1) * 12.9898) * 43758.5453;
  return value - Math.floor(value);
}

function longestCommonPrefix(left: string, right: string): number {
  const maxPrefix = Math.min(left.length, right.length);
  let prefix = 0;
  while (prefix < maxPrefix && left[prefix] === right[prefix]) {
    prefix += 1;
  }
  return prefix;
}

function nextTypingChunk({
  targetText,
  cursor,
  profile,
}: {
  targetText: string;
  cursor: number;
  profile: TypingProfile;
}): number {
  const remaining = targetText.length - cursor;
  if (remaining <= 0) {
    return 0;
  }
  const rhythm = (Math.sin((cursor + 7) * 0.19) + 1) / 2;
  const jitter = deterministicNoise(cursor + remaining);
  const blended = rhythm * 0.62 + jitter * 0.38;
  const chunk = Math.round(
    profile.minChunk + (profile.maxChunk - profile.minChunk) * blended,
  );
  return Math.max(1, Math.min(remaining, chunk));
}

function nextTypingDelay({
  targetText,
  cursorStart,
  cursorEnd,
  profile,
}: {
  targetText: string;
  cursorStart: number;
  cursorEnd: number;
  profile: TypingProfile;
}): number {
  const chunkText = targetText.slice(cursorStart, cursorEnd);
  let delay =
    profile.baseDelayMs +
    Math.round(profile.jitterMs * deterministicNoise(cursorEnd + chunkText.length));

  if (/[,:;!?.)]\s*$/.test(chunkText)) {
    delay += profile.punctuationPauseMs;
  }
  if (chunkText.includes("\n")) {
    delay += profile.newlinePauseMs;
  }
  if (/\s$/.test(chunkText)) {
    delay += profile.wordPauseMs;
  }
  if (cursorEnd > 0 && cursorEnd % profile.cadenceEvery === 0) {
    delay += profile.cadencePauseMs;
  }

  return Math.max(10, delay);
}

function scheduleTypingAnimation({
  timerRef,
  currentValueRef,
  targetText,
  profile,
  setTypedValue,
}: {
  timerRef: { current: number | null };
  currentValueRef: { current: string };
  targetText: string;
  profile: TypingProfile;
  setTypedValue: (value: string) => void;
}) {
  if (timerRef.current) {
    window.clearTimeout(timerRef.current);
    timerRef.current = null;
  }

  if (!targetText) {
    setTypedValue("");
    return;
  }

  let cursor = longestCommonPrefix(currentValueRef.current, targetText);
  setTypedValue(targetText.slice(0, cursor));
  if (cursor >= targetText.length) {
    return;
  }

  const tick = () => {
    const chunkSize = nextTypingChunk({
      targetText,
      cursor,
      profile,
    });
    const cursorStart = cursor;
    cursor = Math.min(targetText.length, cursor + chunkSize);
    setTypedValue(targetText.slice(0, cursor));

    if (cursor >= targetText.length) {
      timerRef.current = null;
      return;
    }

    const delay = nextTypingDelay({
      targetText,
      cursorStart,
      cursorEnd: cursor,
      profile,
    });
    timerRef.current = window.setTimeout(tick, delay);
  };

  timerRef.current = window.setTimeout(tick, profile.baseDelayMs);
}

type UseSceneAnimationsParams = {
  activeEventType: string;
  clipboardPreview: string;
  emailBodyPreview: string;
  isDocsScene: boolean;
  isEmailScene: boolean;
  isSheetsScene: boolean;
  liveCopiedWordsKey: string;
  rawDocBodyPreview: string;
  rawSheetBodyPreview: string;
};

function useSceneAnimations({
  activeEventType,
  clipboardPreview,
  emailBodyPreview,
  isDocsScene,
  isEmailScene,
  isSheetsScene,
  liveCopiedWordsKey,
  rawDocBodyPreview,
  rawSheetBodyPreview,
}: UseSceneAnimationsParams): SceneAnimationState {
  const emailBodyScrollRef = useRef<HTMLDivElement | null>(null);
  const docBodyScrollRef = useRef<HTMLDivElement | null>(null);
  const docTypingTimerRef = useRef<number | null>(null);
  const sheetTypingTimerRef = useRef<number | null>(null);
  const copyPulseTimerRef = useRef<number | null>(null);
  const typedDocBodyRef = useRef("");
  const typedSheetBodyRef = useRef("");

  const [typedDocBodyPreview, setTypedDocBodyPreview] = useState("");
  const [typedSheetBodyPreview, setTypedSheetBodyPreview] = useState("");
  const [copyPulseText, setCopyPulseText] = useState("");
  const [copyPulseVisible, setCopyPulseVisible] = useState(false);

  const docBodyPreview = typedDocBodyPreview || rawDocBodyPreview;

  useEffect(() => {
    if (!isEmailScene) {
      return;
    }
    const node = emailBodyScrollRef.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [emailBodyPreview, isEmailScene]);

  useEffect(() => {
    typedDocBodyRef.current = typedDocBodyPreview;
  }, [typedDocBodyPreview]);

  useEffect(() => {
    typedSheetBodyRef.current = typedSheetBodyPreview;
  }, [typedSheetBodyPreview]);

  useEffect(() => {
    if (activeEventType !== "browser_copy_selection") {
      return;
    }
    const tokenFromKey =
      liveCopiedWordsKey
        .split("|")
        .map((item) => item.trim())
        .find((item) => item.length > 0) || "";
    const token =
      tokenFromKey ||
      clipboardPreview
        .split(/\s+/)
        .map((item) => item.trim())
        .find((item) => item.length > 0) ||
      "";
    if (!token) {
      return;
    }
    setCopyPulseText(token);
    setCopyPulseVisible(true);
    if (copyPulseTimerRef.current) {
      window.clearTimeout(copyPulseTimerRef.current);
      copyPulseTimerRef.current = null;
    }
    copyPulseTimerRef.current = window.setTimeout(() => {
      setCopyPulseVisible(false);
      copyPulseTimerRef.current = null;
    }, 1900);
  }, [activeEventType, clipboardPreview, liveCopiedWordsKey]);

  useEffect(() => {
    if (!isDocsScene) {
      return;
    }
    const node = docBodyScrollRef.current;
    if (!node) {
      return;
    }
    node.scrollTop = node.scrollHeight;
  }, [docBodyPreview, isDocsScene]);

  useEffect(() => {
    if (!isDocsScene) {
      return;
    }
    scheduleTypingAnimation({
      timerRef: docTypingTimerRef,
      currentValueRef: typedDocBodyRef,
      targetText: rawDocBodyPreview,
      profile: DOC_TYPING_PROFILE,
      setTypedValue: setTypedDocBodyPreview,
    });
    return () => {
      if (docTypingTimerRef.current) {
        window.clearTimeout(docTypingTimerRef.current);
        docTypingTimerRef.current = null;
      }
    };
  }, [isDocsScene, rawDocBodyPreview]);

  useEffect(() => {
    if (!isSheetsScene) {
      return;
    }
    scheduleTypingAnimation({
      timerRef: sheetTypingTimerRef,
      currentValueRef: typedSheetBodyRef,
      targetText: rawSheetBodyPreview,
      profile: SHEET_TYPING_PROFILE,
      setTypedValue: setTypedSheetBodyPreview,
    });
    return () => {
      if (sheetTypingTimerRef.current) {
        window.clearTimeout(sheetTypingTimerRef.current);
        sheetTypingTimerRef.current = null;
      }
    };
  }, [isSheetsScene, rawSheetBodyPreview]);

  useEffect(
    () => () => {
      if (copyPulseTimerRef.current) {
        window.clearTimeout(copyPulseTimerRef.current);
        copyPulseTimerRef.current = null;
      }
      if (docTypingTimerRef.current) {
        window.clearTimeout(docTypingTimerRef.current);
        docTypingTimerRef.current = null;
      }
      if (sheetTypingTimerRef.current) {
        window.clearTimeout(sheetTypingTimerRef.current);
        sheetTypingTimerRef.current = null;
      }
    },
    [],
  );

  return {
    copyPulseText,
    copyPulseVisible,
    docBodyScrollRef,
    emailBodyScrollRef,
    typedDocBodyPreview,
    typedSheetBodyPreview,
  };
}

export { useSceneAnimations };
