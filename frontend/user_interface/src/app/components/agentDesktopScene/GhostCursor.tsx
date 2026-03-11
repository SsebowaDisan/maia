"use client";

import React, { useEffect, useRef, useState } from "react";

type GhostCursorProps = {
  cursorX: number | null;
  cursorY: number | null;
  isClick?: boolean;
  advisory?: boolean;
};

/**
 * T1 Ghost Cursor — animated cursor overlaid on the BrowserScene.
 * Follows cursor_x/cursor_y (0–100% of viewport) with spring physics:
 * natural overshoot and settling rather than a simple exponential lerp.
 */
const ADVISORY_CURSOR_KEYFRAME_ID = "maia-ghost-cursor-advisory-style";
const ADVISORY_CURSOR_KEYFRAME_NAME = "maiaGhostCursorAdvisoryPulse";

export function GhostCursor({
  cursorX,
  cursorY,
  isClick = false,
  advisory = false,
}: GhostCursorProps) {
  const [displayX, setDisplayX] = useState<number>(cursorX ?? 50);
  const [displayY, setDisplayY] = useState<number>(cursorY ?? 50);

  const posRef = useRef({ x: cursorX ?? 50, y: cursorY ?? 50 });
  const targetRef = useRef({ x: cursorX ?? 50, y: cursorY ?? 50 });
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (cursorX == null || cursorY == null) return;
    targetRef.current = { x: cursorX, y: cursorY };
  }, [cursorX, cursorY]);

  useEffect(() => {
    if (cursorX == null || cursorY == null) return;
    const SMOOTHING = 0.22;
    const STOP_THRESHOLD = 0.03;

    const animate = () => {
      const dx = targetRef.current.x - posRef.current.x;
      const dy = targetRef.current.y - posRef.current.y;
      if (Math.abs(dx) < STOP_THRESHOLD && Math.abs(dy) < STOP_THRESHOLD) {
        posRef.current = { ...targetRef.current };
      } else {
        posRef.current.x += dx * SMOOTHING;
        posRef.current.y += dy * SMOOTHING;
      }

      setDisplayX(posRef.current.x);
      setDisplayY(posRef.current.y);

      rafRef.current = requestAnimationFrame(animate);
    };

    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(animate);

    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, [cursorX != null, cursorY != null]);

  useEffect(() => {
    if (!advisory || typeof document === "undefined") {
      return;
    }
    if (document.getElementById(ADVISORY_CURSOR_KEYFRAME_ID)) {
      return;
    }
    const style = document.createElement("style");
    style.id = ADVISORY_CURSOR_KEYFRAME_ID;
    style.textContent = `@keyframes ${ADVISORY_CURSOR_KEYFRAME_NAME} {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.06); }
    }`;
    document.head.appendChild(style);
  }, [advisory]);

  if (cursorX == null || cursorY == null) return null;

  return (
    <div
      className="pointer-events-none absolute z-30"
      // Offset so the arrow tip lands exactly on the cursor coordinate
      style={{
        left: `${displayX}%`,
        top: `${displayY}%`,
        transform: `translate(-1px, -1px) scale(${isClick ? 0.92 : 1})`,
        transition: "transform 120ms ease-out",
      }}
    >
      {isClick ? (
        <span className="absolute left-[2px] top-[2px] h-5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/80 bg-white/20 animate-ping" />
      ) : null}
      {/* macOS-style cursor arrow */}
      <svg
        width="18"
        height="24"
        viewBox="0 0 14 20"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{
          opacity: advisory ? 0.45 : 1,
          transformOrigin: "1px 1px",
          animation: advisory
            ? `${ADVISORY_CURSOR_KEYFRAME_NAME} 2s ease-in-out infinite`
            : undefined,
          filter: "drop-shadow(0 1px 4px rgba(0,0,0,0.55)) drop-shadow(0 0 7px rgba(255,255,255,0.16))",
        }}
      >
        {/* Arrow body: tip at (1,1), vertical left side, diagonal right edge, tail */}
        <path
          d="M1,1 L1,15 L5,11 L7.5,18 L10,17 L7.5,11 L12,11 Z"
          fill="white"
          stroke="rgba(0,0,0,0.55)"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}
