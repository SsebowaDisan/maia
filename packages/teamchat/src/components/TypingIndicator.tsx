/**
 * TypingIndicator — shows when an agent is thinking/composing a response.
 */
import React from "react";
import type { ACPCapabilities } from "@maia/acp";

export interface TypingIndicatorProps {
  agentId: string;
  agents?: Map<string, ACPCapabilities>;
  detail?: string;
}

const COLORS = ["#8B5CF6", "#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#EC4899"];

function hashColor(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = id.charCodeAt(i) + ((h << 5) - h);
  return COLORS[Math.abs(h) % COLORS.length];
}

export function TypingIndicator({ agentId, agents, detail }: TypingIndicatorProps) {
  const caps = agents?.get(agentId);
  const name = caps?.name ?? agentId.replace("agent://", "");
  const color = caps?.personality?.avatar_color ?? hashColor(agentId);

  return (
    <div className="flex items-center gap-3 py-2 pl-1">
      <div
        className="flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-semibold text-white"
        style={{ backgroundColor: color }}
      >
        {caps?.personality?.avatar_emoji ?? name[0]?.toUpperCase()}
      </div>
      <div className="flex items-center gap-1.5 text-[12px] text-gray-400">
        <span className="font-medium text-gray-500">{name}</span>
        <span className="italic">{detail ?? "is thinking"}</span>
        <span className="inline-flex gap-0.5">
          <span className="h-1 w-1 animate-bounce rounded-full bg-gray-400" style={{ animationDelay: "0ms" }} />
          <span className="h-1 w-1 animate-bounce rounded-full bg-gray-400" style={{ animationDelay: "150ms" }} />
          <span className="h-1 w-1 animate-bounce rounded-full bg-gray-400" style={{ animationDelay: "300ms" }} />
        </span>
      </div>
    </div>
  );
}