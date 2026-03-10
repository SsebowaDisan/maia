import { useEffect, useState } from "react";

type UseTypewriterTextOptions = {
  charIntervalMs?: number;
  caretBlinkMs?: number;
  caret?: boolean;
};

function useTypewriterText(
  sourceText: string,
  { charIntervalMs = 52, caretBlinkMs = 560, caret = false }: UseTypewriterTextOptions = {},
): { typedText: string; showCaret: boolean } {
  const targetText = String(sourceText || "").trim();
  const [typedText, setTypedText] = useState(targetText);
  const [showCaret, setShowCaret] = useState(true);

  useEffect(() => {
    if (!targetText) {
      setTypedText("");
      return;
    }

    const reduceMotion =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      setTypedText(targetText);
      return;
    }

    let index = 0;
    setTypedText("");
    const timer = window.setInterval(() => {
      index += 1;
      setTypedText(targetText.slice(0, Math.min(index, targetText.length)));
      if (index >= targetText.length) {
        window.clearInterval(timer);
      }
    }, Math.max(12, Math.round(charIntervalMs)));

    return () => window.clearInterval(timer);
  }, [charIntervalMs, targetText]);

  useEffect(() => {
    if (!caret) {
      setShowCaret(false);
      return;
    }
    setShowCaret(true);
    const timer = window.setInterval(
      () => setShowCaret((previous) => !previous),
      Math.max(180, Math.round(caretBlinkMs)),
    );
    return () => window.clearInterval(timer);
  }, [caret, caretBlinkMs]);

  return { typedText, showCaret };
}

export { useTypewriterText };
