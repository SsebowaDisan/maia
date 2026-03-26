/**
 * ReviewBadge — inline review result shown after a conversation thread.
 */
import React from "react";
import type { ACPEvent, ACPReview } from "@maia/acp";

export interface ReviewBadgeProps {
  event: ACPEvent;
}

const VERDICT_STYLE: Record<string, { icon: string; bg: string; text: string }> = {
  approve:  { icon: "\u2705", bg: "bg-green-50",  text: "text-green-700" },
  revise:   { icon: "\u270F\uFE0F", bg: "bg-yellow-50", text: "text-yellow-700" },
  reject:   { icon: "\u274C", bg: "bg-red-50",    text: "text-red-700" },
  escalate: { icon: "\u26A0\uFE0F", bg: "bg-orange-50", text: "text-orange-700" },
};

export function ReviewBadge({ event }: ReviewBadgeProps) {
  const rev = event.payload as unknown as ACPReview;
  const style = VERDICT_STYLE[rev.verdict] ?? VERDICT_STYLE.approve;
  const reviewer = (rev.reviewer ?? "").replace("agent://", "");
  const author = (rev.author ?? "").replace("agent://", "");

  return (
    <div className={`ml-12 flex items-center gap-2 rounded-lg px-3 py-1.5 ${style.bg}`}>
      <span>{style.icon}</span>
      <span className={`text-[12px] font-medium ${style.text}`}>
        {reviewer} {rev.verdict === "approve" ? "approved" : `${rev.verdict}d`} {author}'s work
      </span>
      {rev.score != null && (
        <span className="text-[11px] text-gray-400">({Math.round(rev.score * 100)}%)</span>
      )}
      {rev.round && rev.round > 1 && (
        <span className="text-[10px] text-gray-400">round {rev.round}</span>
      )}
      {rev.feedback && (
        <span className="ml-1 truncate text-[11px] text-gray-500">{rev.feedback}</span>
      )}
    </div>
  );
}