"use client";

import { useEffect, useRef, useState } from "react";

type ThoughtBubbleProps = {
  text: string | null | undefined;
};

/**
 * T5: Thought Bubble — slides up for 2.5s then fades out.
 * Triggered by a change in `text`; identical consecutive values are deduplicated.
 */
function ThoughtBubble({ text }: ThoughtBubbleProps) {
  const [visible, setVisible] = useState(false);
  const [displayText, setDisplayText] = useState("");
  const prevTextRef = useRef<string>("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const clean = (text ?? "").trim();
    if (!clean || clean === prevTextRef.current) return;
    prevTextRef.current = clean;

    if (timerRef.current) clearTimeout(timerRef.current);
    setDisplayText(clean);
    setVisible(true);
    timerRef.current = setTimeout(() => setVisible(false), 2500);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [text]);

  if (!displayText) return null;

  return (
    <>
      <style>{`
        @keyframes thought-slide-up {
          0%   { opacity: 0; transform: translateY(12px); }
          15%  { opacity: 1; transform: translateY(0); }
          75%  { opacity: 1; transform: translateY(0); }
          100% { opacity: 0; transform: translateY(-6px); }
        }
        .thought-bubble-anim {
          animation: thought-slide-up 2600ms ease-in-out forwards;
        }
      `}</style>
      {visible ? (
        <div
          key={displayText}
          className="pointer-events-none absolute bottom-14 left-1/2 z-40 -translate-x-1/2 thought-bubble-anim"
        >
          <div className="flex items-center gap-2 rounded-full border border-white/25 bg-[#1d1d1f]/80 px-3.5 py-2 shadow-lg backdrop-blur-sm">
            <span className="h-2 w-2 shrink-0 rounded-full bg-[#86d9ff] opacity-80" />
            <p className="max-w-[220px] text-[11px] font-medium text-white/95">{displayText}</p>
          </div>
        </div>
      ) : null}
    </>
  );
}

export { ThoughtBubble };
