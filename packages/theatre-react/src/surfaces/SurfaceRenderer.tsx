import React from "react";
import type { SurfaceState } from "./types";

interface SurfaceRendererProps {
  surface: SurfaceState;
  className?: string;
}

function SurfaceRenderer({ surface, className = "" }: SurfaceRendererProps) {
  return (
    <div className={`rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-700 ${className}`}>
      {surface.title ? <div className="font-semibold text-gray-900">{surface.title}</div> : null}
      {surface.detail ? <div className="mt-1 text-gray-600">{surface.detail}</div> : null}
      {surface.url ? <div className="mt-2 truncate font-mono text-xs text-gray-500">{surface.url}</div> : null}
      {surface.html ? (
        <div
          className="prose prose-sm mt-3 max-w-none"
          dangerouslySetInnerHTML={{ __html: surface.html }}
        />
      ) : null}
      {!surface.html && surface.text ? (
        <pre className="mt-3 whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-xs text-gray-700">
          {surface.text}
        </pre>
      ) : null}
    </div>
  );
}

export { SurfaceRenderer };
export type { SurfaceRendererProps };
