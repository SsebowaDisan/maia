import { useEffect, useRef, useState } from "react";
import type { SceneAnimationState } from "./types";

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
    if (docTypingTimerRef.current) {
      window.clearInterval(docTypingTimerRef.current);
      docTypingTimerRef.current = null;
    }
    if (!rawDocBodyPreview) {
      setTypedDocBodyPreview("");
      return;
    }
    let cursor = 0;
    const current = typedDocBodyRef.current;
    const maxPrefix = Math.min(current.length, rawDocBodyPreview.length);
    while (cursor < maxPrefix && current[cursor] === rawDocBodyPreview[cursor]) {
      cursor += 1;
    }
    setTypedDocBodyPreview(rawDocBodyPreview.slice(0, cursor));
    if (cursor >= rawDocBodyPreview.length) {
      return;
    }
    docTypingTimerRef.current = window.setInterval(() => {
      cursor = Math.min(
        rawDocBodyPreview.length,
        cursor + Math.max(1, Math.ceil((rawDocBodyPreview.length - cursor) / 22)),
      );
      setTypedDocBodyPreview(rawDocBodyPreview.slice(0, cursor));
      if (cursor >= rawDocBodyPreview.length && docTypingTimerRef.current) {
        window.clearInterval(docTypingTimerRef.current);
        docTypingTimerRef.current = null;
      }
    }, 16);
    return () => {
      if (docTypingTimerRef.current) {
        window.clearInterval(docTypingTimerRef.current);
        docTypingTimerRef.current = null;
      }
    };
  }, [isDocsScene, rawDocBodyPreview]);

  useEffect(() => {
    if (!isSheetsScene) {
      return;
    }
    if (sheetTypingTimerRef.current) {
      window.clearInterval(sheetTypingTimerRef.current);
      sheetTypingTimerRef.current = null;
    }
    if (!rawSheetBodyPreview) {
      setTypedSheetBodyPreview("");
      return;
    }
    let cursor = 0;
    const current = typedSheetBodyRef.current;
    const maxPrefix = Math.min(current.length, rawSheetBodyPreview.length);
    while (cursor < maxPrefix && current[cursor] === rawSheetBodyPreview[cursor]) {
      cursor += 1;
    }
    setTypedSheetBodyPreview(rawSheetBodyPreview.slice(0, cursor));
    if (cursor >= rawSheetBodyPreview.length) {
      return;
    }
    sheetTypingTimerRef.current = window.setInterval(() => {
      cursor = Math.min(
        rawSheetBodyPreview.length,
        cursor + Math.max(1, Math.ceil((rawSheetBodyPreview.length - cursor) / 26)),
      );
      setTypedSheetBodyPreview(rawSheetBodyPreview.slice(0, cursor));
      if (cursor >= rawSheetBodyPreview.length && sheetTypingTimerRef.current) {
        window.clearInterval(sheetTypingTimerRef.current);
        sheetTypingTimerRef.current = null;
      }
    }, 16);
    return () => {
      if (sheetTypingTimerRef.current) {
        window.clearInterval(sheetTypingTimerRef.current);
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
        window.clearInterval(docTypingTimerRef.current);
        docTypingTimerRef.current = null;
      }
      if (sheetTypingTimerRef.current) {
        window.clearInterval(sheetTypingTimerRef.current);
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
