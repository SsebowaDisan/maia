import { useEffect, useRef, useState } from "react";
import { SkipBack, StepBack, Play, Pause, StepForward, SkipForward } from "lucide-react";
import { sanitizeComputerUseText } from "../../utils/userFacingComputerUse";

type ReplayEvent = {
  event_type?: string;
  tool_id?: string;
  text?: string;
  content?: string;
  [key: string]: unknown;
};

type ReplayControlsProps = {
  runId: string;
  /** Called with the currently-highlighted event each time the cursor moves. */
  onStep?: (event: ReplayEvent, index: number, total: number) => void;
};

export function ReplayControls({ runId, onStep }: ReplayControlsProps) {
  const [events, setEvents] = useState<ReplayEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Load events for this run
  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    fetch(`/api/agent/runs/${runId}/events`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        const evts = Array.isArray(data) ? (data as ReplayEvent[]) : [];
        setEvents(evts);
        setCursor(0);
        setPlaying(false);
      })
      .catch(() => setEvents([]))
      .finally(() => setLoading(false));
  }, [runId]);

  // Notify parent when cursor changes
  useEffect(() => {
    if (events.length === 0) return;
    const idx = Math.min(cursor, events.length - 1);
    onStep?.(events[idx], idx, events.length);
  }, [cursor, events, onStep]);

  // Auto-play interval
  useEffect(() => {
    if (!playing) {
      if (intervalRef.current) clearInterval(intervalRef.current);
      return;
    }
    intervalRef.current = setInterval(() => {
      setCursor((c) => {
        if (c >= events.length - 1) {
          setPlaying(false);
          return c;
        }
        return c + 1;
      });
    }, 600);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing, events.length]);

  if (!runId) return null;

  const total = events.length;
  const currentEvent = events[cursor];

  return (
    <div className="flex flex-col gap-2 px-4 py-3 border-t border-border/50 bg-background">
      {/* Timeline scrubber */}
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-muted-foreground tabular-nums w-8 text-right">
          {total > 0 ? cursor + 1 : 0}
        </span>
        <input
          type="range"
          min={0}
          max={Math.max(total - 1, 0)}
          value={cursor}
          onChange={(e) => {
            setPlaying(false);
            setCursor(Number(e.target.value));
          }}
          disabled={total === 0 || loading}
          className="flex-1 h-1 accent-primary cursor-pointer disabled:opacity-40"
        />
        <span className="text-[10px] text-muted-foreground tabular-nums w-8">
          {total}
        </span>
      </div>

      {/* Transport controls */}
      <div className="flex items-center justify-center gap-1">
        <button
          onClick={() => {
            setPlaying(false);
            setCursor(0);
          }}
          disabled={total === 0 || loading}
          className="p-1.5 rounded hover:bg-accent text-muted-foreground disabled:opacity-30 transition-colors"
          title="Go to start"
        >
          <SkipBack size={13} />
        </button>
        <button
          onClick={() => setCursor((c) => Math.max(0, c - 1))}
          disabled={cursor === 0 || loading}
          className="p-1.5 rounded hover:bg-accent text-muted-foreground disabled:opacity-30 transition-colors"
          title="Step back"
        >
          <StepBack size={13} />
        </button>
        <button
          onClick={() => setPlaying((v) => !v)}
          disabled={total === 0 || loading}
          className="p-2 rounded-full bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-30 transition-colors"
          title={playing ? "Pause" : "Play"}
        >
          {playing ? <Pause size={13} /> : <Play size={13} />}
        </button>
        <button
          onClick={() => setCursor((c) => Math.min(total - 1, c + 1))}
          disabled={cursor >= total - 1 || loading}
          className="p-1.5 rounded hover:bg-accent text-muted-foreground disabled:opacity-30 transition-colors"
          title="Step forward"
        >
          <StepForward size={13} />
        </button>
        <button
          onClick={() => {
            setPlaying(false);
            setCursor(Math.max(0, total - 1));
          }}
          disabled={total === 0 || loading}
          className="p-1.5 rounded hover:bg-accent text-muted-foreground disabled:opacity-30 transition-colors"
          title="Go to end"
        >
          <SkipForward size={13} />
        </button>
      </div>

      {/* Current event label */}
      {currentEvent && (
        <p className="text-[10px] text-muted-foreground text-center truncate">
          {currentEvent.event_type || "event"}
          {currentEvent.tool_id ? ` · ${sanitizeComputerUseText(currentEvent.tool_id)}` : ""}
          {currentEvent.text || currentEvent.content
            ? ` · ${sanitizeComputerUseText(currentEvent.text ?? currentEvent.content).slice(0, 40)}`
            : ""}
        </p>
      )}

      {loading && (
        <p className="text-[10px] text-muted-foreground text-center">Loading events...</p>
      )}
    </div>
  );
}
