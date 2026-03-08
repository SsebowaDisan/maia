"use client";

import React from "react";

type TracePoint = { x: number; y: number };

type InteractionTraceProps = {
  points: TracePoint[];
};

/**
 * T7 Interaction Trace Overlay — breadcrumb trail of last 5 interactions.
 * Dots connected by a dashed SVG polyline; most recent dot is opaque,
 * oldest is nearly transparent.
 */
export function InteractionTrace({ points }: InteractionTraceProps) {
  if (points.length < 2) return null;
  const recent = points.slice(-5);

  const polylinePoints = recent.map((p) => `${p.x},${p.y}`).join(" ");

  return (
    <svg
      className="pointer-events-none absolute inset-0 z-25 h-full w-full"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
    >
      <polyline
        points={polylinePoints}
        fill="none"
        stroke="rgba(134,217,255,0.4)"
        strokeWidth="0.4"
        strokeDasharray="1.5 1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {recent.map((p, i) => {
        const opacity = 0.1 + (i / Math.max(1, recent.length - 1)) * 0.8;
        const r = i === recent.length - 1 ? 0.9 : 0.55;
        return (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={r}
            fill={`rgba(134,217,255,${opacity.toFixed(2)})`}
          />
        );
      })}
    </svg>
  );
}

export type { TracePoint };
