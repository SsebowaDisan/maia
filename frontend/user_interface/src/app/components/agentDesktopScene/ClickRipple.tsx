"use client";

import React from "react";

type ClickRippleEntry = {
  id: string;
  x: number;
  y: number;
  type: "click" | "hover";
};

type ClickRippleProps = {
  ripples: ClickRippleEntry[];
};

/**
 * T1 Click/Hover Element Glow.
 * Click: two concentric expanding rings (inner fast, outer slow) — satisfying water-drop effect.
 * Hover: soft blue halo.
 */
export function ClickRipple({ ripples }: ClickRippleProps) {
  return (
    <>
      {ripples.map((r) => (
        <div
          key={r.id}
          className="pointer-events-none absolute z-20"
          style={{ left: `${r.x}%`, top: `${r.y}%`, transform: "translate(-50%, -50%)" }}
        >
          {r.type === "click" ? (
            <>
              {/* Inner ring — fast, opaque */}
              <div
                className="absolute rounded-full border-2 border-white/90"
                style={{
                  width: 10,
                  height: 10,
                  left: -5,
                  top: -5,
                  animation: "ripple-inner 500ms cubic-bezier(0.2,0.8,0.4,1) forwards",
                }}
              />
              {/* Outer ring — slower, more transparent */}
              <div
                className="absolute rounded-full border border-white/55"
                style={{
                  width: 10,
                  height: 10,
                  left: -5,
                  top: -5,
                  animation: "ripple-outer 700ms cubic-bezier(0.2,0.8,0.4,1) forwards",
                }}
              />
              {/* Center flash */}
              <div
                className="absolute rounded-full bg-white/50"
                style={{
                  width: 6,
                  height: 6,
                  left: -3,
                  top: -3,
                  animation: "ripple-flash 200ms ease-out forwards",
                }}
              />
            </>
          ) : (
            <div
              className="rounded-full bg-white/15"
              style={{
                width: 32,
                height: 32,
                animation: "hover-halo 350ms ease-out forwards",
              }}
            />
          )}
        </div>
      ))}
      <style>{`
        @keyframes ripple-inner {
          0%   { transform: scale(1);   opacity: 1; }
          100% { transform: scale(4.5); opacity: 0; }
        }
        @keyframes ripple-outer {
          0%   { transform: scale(1);   opacity: 0.7; }
          100% { transform: scale(7);   opacity: 0; }
        }
        @keyframes ripple-flash {
          0%   { transform: scale(1);   opacity: 1; }
          100% { transform: scale(2.5); opacity: 0; }
        }
        @keyframes hover-halo {
          0%   { opacity: 0; transform: scale(0.6); }
          100% { opacity: 1; transform: scale(1); }
        }
      `}</style>
    </>
  );
}

export type { ClickRippleEntry };
