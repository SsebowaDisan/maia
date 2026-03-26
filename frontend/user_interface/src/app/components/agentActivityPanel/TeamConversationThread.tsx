import type { RefObject } from "react";
import { Users } from "lucide-react";

import type { ConversationGroup } from "./teamConversationModel";
import { bubbleClass } from "./teamConversationModel";

type TeamConversationThreadProps = {
  groups: ConversationGroup[];
  isLive: boolean;
  containerRef: RefObject<HTMLDivElement | null>;
  listEndRef: RefObject<HTMLDivElement | null>;
  onScroll?: () => void;
};

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function timeDivider(current: ConversationGroup, previous?: ConversationGroup): string {
  if (!previous) {
    return "";
  }
  if (current.startedAt - previous.lastAt < 6 * 60 * 1000) {
    return "";
  }
  return new Date(current.startedAt).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

export function TeamConversationThread({
  groups,
  isLive,
  containerRef,
  listEndRef,
  onScroll,
}: TeamConversationThreadProps) {
  return (
    <div
      ref={containerRef}
      onScroll={onScroll}
      className="min-h-0 flex-1 overflow-y-auto rounded-[20px] border border-[#eaecf0] bg-[linear-gradient(180deg,#fcfdff_0%,#f7f9fc_100%)] px-3 py-3 scroll-smooth"
    >
      <div className="flex min-h-full flex-col gap-3">
        {groups.map((group, index) => {
          const divider = timeDivider(group, groups[index - 1]);
          return (
            <div key={group.id} className="space-y-2">
              {divider ? (
                <div className="flex items-center gap-2 px-1">
                  <div className="h-px flex-1 bg-[#e4e7ec]" />
                  <span className="text-[10px] font-medium uppercase tracking-[0.06em] text-[#98a2b3]">
                    {divider}
                  </span>
                  <div className="h-px flex-1 bg-[#e4e7ec]" />
                </div>
              ) : null}

              <article className="flex items-start gap-2.5">
                <div className="sticky top-0 w-8 shrink-0 pt-0.5">
                  <span
                    className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/80 text-[10px] font-semibold text-[#1f2937] shadow-[0_1px_2px_rgba(16,24,40,0.08)]"
                    style={{ backgroundColor: group.avatarColor }}
                  >
                    {group.avatarLabel}
                  </span>
                </div>

                <div className="min-w-0 flex-1 space-y-1.5">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1 px-0.5">
                    <span className="text-[12px] font-semibold text-[#111827]">{group.from}</span>
                    {group.role ? (
                      <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-medium text-[#667085] ring-1 ring-black/[0.06]">
                        {group.role}
                      </span>
                    ) : null}
                    {group.audience ? (
                      <span className="rounded-full border border-black/[0.08] bg-white px-2 py-0.5 text-[10px] font-semibold text-[#667085]">
                        {group.audience}
                      </span>
                    ) : null}
                    {group.mood ? (
                      <span className="rounded-full border border-[#dbeafe] bg-[#eff6ff] px-2 py-0.5 text-[10px] font-medium text-[#1d4ed8]">
                        {group.mood}
                      </span>
                    ) : null}
                    {group.threadLabel ? (
                      <span className="rounded-full border border-[#e4e7ec] bg-white px-2 py-0.5 text-[10px] font-medium text-[#475467]">
                        {group.threadLabel}
                      </span>
                    ) : null}
                    <span className="text-[10px] font-medium text-[#98a2b3]">{formatTime(group.startedAt)}</span>
                  </div>

                  <div className="relative ml-1 space-y-1.5 before:absolute before:bottom-2 before:left-[-11px] before:top-1 before:w-px before:bg-[#e4e7ec] before:content-['']">
                    {group.bubbles.map((bubble, bubbleIndex) => (
                      <div key={bubble.id} className="relative pl-3 before:absolute before:left-[-13px] before:top-5 before:h-px before:w-3 before:bg-[#e4e7ec] before:content-['']">
                        <div
                          className={`max-w-[96%] rounded-[20px] border px-3 py-2.5 shadow-[0_1px_0_rgba(17,24,39,0.02)] ${bubbleClass(
                            bubble.entryType,
                            group.from,
                          )}`}
                        >
                          {bubble.replyPreview ? (
                            <div className="mb-2 rounded-2xl border border-black/[0.06] bg-white/80 px-2.5 py-1.5 text-[10px] leading-[1.45] text-[#667085]">
                              Replying to: {bubble.replyPreview}
                            </div>
                          ) : null}
                          <p className="text-[12px] leading-[1.6] text-[#1f2937]">{bubble.text}</p>
                          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
                            <span className="font-semibold uppercase tracking-[0.05em] text-[#667085]">
                              {bubble.badge}
                            </span>
                            {bubble.action ? (
                              <span className="rounded-full bg-white/90 px-2 py-0.5 font-medium text-[#475467] ring-1 ring-black/[0.06]">
                                {bubble.action}
                              </span>
                            ) : null}
                            {bubble.deliveryStatus ? (
                              <span className="rounded-full bg-white/90 px-2 py-0.5 font-medium text-[#475467] ring-1 ring-black/[0.06]">
                                {bubble.deliveryStatus}
                              </span>
                            ) : null}
                            {bubble.requiresAck ? (
                              <span className="rounded-full border border-[#fcd34d] bg-[#fffbeb] px-2 py-0.5 font-semibold text-[#b54708]">
                                ack required
                              </span>
                            ) : null}
                            {bubble.mentions.length > 0 ? (
                              <span className="rounded-full bg-white/90 px-2 py-0.5 font-medium text-[#475467] ring-1 ring-black/[0.06]">
                                {bubble.mentions.map((mention) => `@${mention}`).join(" ")}
                              </span>
                            ) : null}
                            {bubbleIndex > 0 ? (
                              <span className="ml-auto font-medium text-[#98a2b3]">{formatTime(bubble.timestamp)}</span>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </article>
            </div>
          );
        })}

        <div className="mt-auto rounded-2xl border border-dashed border-[#d0d5dd] bg-white/70 px-3 py-2 text-[11px] text-[#667085]">
          <div className="flex items-center gap-2">
            <Users size={13} className="text-[#667085]" />
            <span>{isLive ? "Following teammate chat live." : "Showing the latest saved teammate thread."}</span>
          </div>
        </div>
        <div ref={listEndRef} />
      </div>
    </div>
  );
}
