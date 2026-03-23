/**
 * TeamChatSkin — live agent team chat in the Theatre.
 *
 * Features:
 * - Chat bubbles with agent avatars, colors, and names
 * - "thinking..." animation before responses
 * - Mood indicators (curious, confident, skeptical, excited)
 * - Reply threading (shows who they're responding to)
 * - Summary messages styled differently
 * - Typing indicator while conversation is live
 */

type TeamChatMessage = {
  message_id: string;
  speaker_id?: string;
  speaker_name: string;
  speaker_role: string;
  speaker_avatar: string;
  speaker_color: string;
  content: string;
  timestamp: number;
  message_type?: string; // message | thinking | searching | reaction | summary
  mood?: string; // neutral | curious | confident | skeptical | excited | concerned
  reply_to_id?: string;
  reaction?: string;
};

type TeamChatSkinProps = {
  messages: TeamChatMessage[];
  topic: string;
  runId: string;
};

const MOOD_EMOJI: Record<string, string> = {
  curious: "\u{1F914}",     // 🤔
  confident: "\u{1F4AA}",   // 💪
  skeptical: "\u{1F928}",   // 🤨
  excited: "\u{1F525}",     // 🔥
  concerned: "\u{26A0}",    // ⚠
  neutral: "",
};

function TeamChatSkin({ messages, topic }: TeamChatSkinProps) {
  const visibleMessages = messages.filter((m) => m.message_type !== "thinking" || m.content === "thinking...");
  const latestThinking = messages.filter((m) => m.message_type === "thinking").pop();
  const isActive = latestThinking && messages[messages.length - 1]?.message_type === "thinking";

  return (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(139,92,246,0.10),rgba(6,10,18,0.97)_62%)] px-4 py-3">
      <div className="mx-auto flex h-full w-full max-w-[780px] flex-col rounded-2xl border border-white/8 bg-[#0d0e14]/95 shadow-[0_20px_60px_rgba(0,0,0,0.6)]">

        {/* Header */}
        <div className="flex items-center gap-3 border-b border-white/6 px-4 py-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-500/15">
            <svg className="h-3.5 w-3.5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 8h2a2 2 0 012 2v6a2 2 0 01-2 2h-2v4l-4-4H9a2 2 0 01-2-2v-6a2 2 0 012-2h8z" />
            </svg>
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[12px] font-semibold text-white/90">Team Discussion</p>
            <p className="truncate text-[10px] text-white/40">{topic || "Agents collaborating"}</p>
          </div>
          <div className="flex items-center gap-1.5">
            {_uniqueSpeakers(messages).map((s) => (
              <div
                key={s.id}
                className="flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-bold"
                style={{ backgroundColor: s.color + "30", color: s.color }}
                title={s.name}
              >
                {s.avatar}
              </div>
            ))}
          </div>
        </div>

        {/* Chat feed */}
        <div className="flex-1 overflow-y-auto px-3 py-2">
          <div className="space-y-1.5">
            {visibleMessages.map((msg) => {
              // Thinking bubble
              if (msg.message_type === "thinking") {
                return (
                  <div key={msg.message_id} className="flex items-center gap-2 py-1">
                    <div
                      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[10px] font-bold"
                      style={{ backgroundColor: msg.speaker_color + "20", color: msg.speaker_color }}
                    >
                      {msg.speaker_avatar}
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-white/30">
                      <span style={{ color: msg.speaker_color }} className="font-medium">{msg.speaker_name}</span>
                      <span className="italic">is thinking</span>
                      <span className="flex gap-0.5">
                        <span className="inline-block h-1 w-1 animate-pulse rounded-full bg-white/30" style={{ animationDelay: "0ms" }} />
                        <span className="inline-block h-1 w-1 animate-pulse rounded-full bg-white/30" style={{ animationDelay: "200ms" }} />
                        <span className="inline-block h-1 w-1 animate-pulse rounded-full bg-white/30" style={{ animationDelay: "400ms" }} />
                      </span>
                    </div>
                  </div>
                );
              }

              // Summary message (Brain wrap-up)
              if (msg.message_type === "summary") {
                return (
                  <div key={msg.message_id} className="my-2 rounded-xl border border-purple-500/20 bg-purple-500/5 px-3 py-2.5">
                    <div className="flex items-center gap-2 text-[10px] text-purple-300/70">
                      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span className="font-semibold uppercase tracking-wider">Decision</span>
                    </div>
                    <p className="mt-1.5 text-[12px] leading-relaxed text-white/80">{msg.content}</p>
                  </div>
                );
              }

              // Regular message
              const moodEmoji = MOOD_EMOJI[msg.mood || "neutral"] || "";
              const isBrain = msg.speaker_id === "brain" || msg.speaker_name === "Maia Brain";

              return (
                <div key={msg.message_id} className="group flex items-start gap-2 py-1 transition-colors hover:bg-white/[0.02] rounded-lg px-1">
                  {/* Avatar */}
                  <div
                    className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold"
                    style={{ backgroundColor: msg.speaker_color + "20", color: msg.speaker_color }}
                  >
                    {isBrain ? "\u{1F9E0}" : msg.speaker_avatar}
                  </div>
                  {/* Content */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-[12px] font-bold" style={{ color: msg.speaker_color }}>
                        {msg.speaker_name}
                      </span>
                      {msg.speaker_role && !isBrain ? (
                        <span className="text-[9px] text-white/25">{msg.speaker_role}</span>
                      ) : null}
                      {moodEmoji ? (
                        <span className="text-[11px]" title={msg.mood}>{moodEmoji}</span>
                      ) : null}
                      <span className="ml-auto text-[9px] text-white/15 opacity-0 transition-opacity group-hover:opacity-100">
                        {_formatTime(msg.timestamp)}
                      </span>
                    </div>
                    <p className={`mt-0.5 whitespace-pre-wrap text-[12px] leading-relaxed ${isBrain ? "text-white/70 italic" : "text-white/80"}`}>
                      {msg.content}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Active typing indicator */}
        {isActive && latestThinking ? (
          <div className="border-t border-white/5 px-4 py-2">
            <div className="flex items-center gap-2 text-[10px] text-white/25">
              <span className="flex gap-0.5">
                <span className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-purple-400/50" style={{ animationDelay: "0ms" }} />
                <span className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-purple-400/50" style={{ animationDelay: "150ms" }} />
                <span className="inline-block h-1.5 w-1.5 animate-bounce rounded-full bg-purple-400/50" style={{ animationDelay: "300ms" }} />
              </span>
              <span>
                <span style={{ color: latestThinking.speaker_color }}>{latestThinking.speaker_name}</span>
                {" is composing a response..."}
              </span>
            </div>
          </div>
        ) : (
          <div className="border-t border-white/5 px-4 py-1.5">
            <div className="flex items-center justify-between text-[9px] text-white/20">
              <span>{messages.filter((m) => m.message_type === "message" || m.message_type === "summary").length} messages</span>
              <span>{_uniqueSpeakers(messages).length} participants</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _uniqueSpeakers(messages: TeamChatMessage[]): Array<{ id: string; name: string; avatar: string; color: string }> {
  const seen = new Map<string, { id: string; name: string; avatar: string; color: string }>();
  for (const m of messages) {
    const id = m.speaker_name;
    if (!seen.has(id)) {
      seen.set(id, { id, name: m.speaker_name, avatar: m.speaker_avatar, color: m.speaker_color });
    }
  }
  return Array.from(seen.values());
}

function _formatTime(ts: number): string {
  try {
    return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

export type { TeamChatMessage };
export { TeamChatSkin };
