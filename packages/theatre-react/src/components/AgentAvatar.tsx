/**
 * AgentAvatar - consistent agent identity across Theatre.
 */
import React from "react";

export interface AgentAvatarProps {
  agentId: string;
  name?: string;
  emoji?: string;
  color?: string;
  size?: "sm" | "md" | "lg";
  mood?: string;
  activity?: string;
  availability?: "available" | "focused" | "busy" | "offline";
  activeTaskCount?: number;
}

const SIZE_MAP = { sm: 28, md: 36, lg: 48 };

const DEFAULT_COLORS = [
  "#8B5CF6", "#3B82F6", "#10B981", "#F59E0B",
  "#EF4444", "#EC4899", "#6366F1", "#14B8A6",
  "#F97316", "#84CC16", "#06B6D4", "#A855F7",
];

const ACTIVITY_RING: Record<string, string> = {
  thinking: "animate-pulse border-amber-400",
  searching: "border-sky-400",
  writing: "border-emerald-400",
  reviewing: "border-violet-400",
  browsing: "border-cyan-400",
  error: "border-rose-500",
  idle: "border-slate-300",
};

const AVAILABILITY_DOT: Record<NonNullable<AgentAvatarProps["availability"]>, string> = {
  available: "bg-emerald-400",
  focused: "bg-sky-400",
  busy: "bg-amber-400",
  offline: "bg-slate-400",
};

function hashColor(id: string): string {
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = id.charCodeAt(i) + ((hash << 5) - hash);
  }
  return DEFAULT_COLORS[Math.abs(hash) % DEFAULT_COLORS.length];
}

function initials(name: string): string {
  return name
    .replace("agent://", "")
    .split(/[_\-\s]+/)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .slice(0, 2)
    .join("");
}

export function AgentAvatar({
  agentId,
  name,
  emoji,
  color,
  size = "md",
  mood,
  activity,
  availability = "available",
  activeTaskCount,
}: AgentAvatarProps) {
  const px = SIZE_MAP[size];
  const bg = color ?? hashColor(agentId);
  const label = name ?? agentId.replace("agent://", "");
  const ringClass = activity ? ACTIVITY_RING[activity] ?? "" : "";
  const showTaskCount = typeof activeTaskCount === "number" && activeTaskCount > 0;

  return (
    <div
      className={`relative inline-flex items-center justify-center rounded-full border-2 ${
        ringClass || "border-transparent"
      }`}
      style={{ width: px, height: px, backgroundColor: bg }}
      title={[
        label,
        mood ? `(${mood})` : "",
        activity ? `activity: ${activity}` : "",
        availability ? `status: ${availability}` : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span
        className="select-none font-semibold text-white"
        style={{ fontSize: px * 0.38 }}
      >
        {emoji ?? initials(label)}
      </span>

      <span
        className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border border-white ${
          AVAILABILITY_DOT[availability]
        }`}
      />

      {showTaskCount && (
        <span className="absolute -top-1 -right-1 inline-flex min-w-[16px] items-center justify-center rounded-full bg-slate-950 px-1 text-[9px] font-semibold leading-4 text-white shadow-sm dark:bg-white dark:text-slate-900">
          {activeTaskCount}
        </span>
      )}
    </div>
  );
}
