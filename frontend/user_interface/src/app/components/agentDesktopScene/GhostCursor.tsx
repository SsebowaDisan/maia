"use client";

import React, { useEffect, useRef, useState } from "react";

type GhostCursorProps = {
  cursorX: number | null;
  cursorY: number | null;
  isClick?: boolean;
};

/**
 * T1 Ghost Cursor — animated cursor overlaid on the BrowserScene.
 * Follows cursor_x/cursor_y (0–100% of viewport) with spring physics:
 * natural overshoot and settling rather than a simple exponential lerp.
 */
export function GhostCursor({ cursorX, cursorY }: GhostCursorProps) {
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

  if (cursorX == null || cursorY == null) return null;

  return (
    <div
      className="pointer-events-none absolute z-30"
      // Offset so the arrow tip lands exactly on the cursor coordinate
      style={{ left: `${displayX}%`, top: `${displayY}%`, transform: "translate(-1px, -1px)" }}
    >
      {/* macOS-style cursor arrow */}
      <svg
        width="18"
        height="24"
        viewBox="0 0 14 20"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={{ filter: "drop-shadow(0 1px 4px rgba(0,0,0,0.55)) drop-shadow(0 0 7px rgba(255,255,255,0.16))" }}
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
