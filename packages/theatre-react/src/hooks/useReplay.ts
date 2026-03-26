/**
 * useReplay — DVR controls for replaying recorded ACP runs.
 *
 * Feed it a recorded event array and it plays them back with
 * variable speed, pause, scrub, and step controls.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { ACPEvent } from "@maia/acp";

export interface UseReplayOptions {
  /** The full recorded event array. */
  events: ACPEvent[];
  /** Playback speed multiplier (default 1.0). */
  speed?: number;
  /** Auto-play on mount (default false). */
  autoPlay?: boolean;
}

export interface ReplayState {
  /** Events that have been "played" so far. */
  visibleEvents: ACPEvent[];
  /** Current position (0 to events.length). */
  position: number;
  /** Whether playback is running. */
  playing: boolean;
  /** Current speed multiplier. */
  speed: number;
  /** Total events. */
  total: number;
  /** Progress 0–100. */
  progress: number;
  /** Controls. */
  play: () => void;
  pause: () => void;
  reset: () => void;
  setSpeed: (speed: number) => void;
  scrubTo: (position: number) => void;
  stepForward: () => void;
  stepBackward: () => void;
}

export function useReplay(options: UseReplayOptions): ReplayState {
  const { events, speed: initialSpeed = 1.0, autoPlay = false } = options;
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(autoPlay);
  const [speed, setSpeed] = useState(initialSpeed);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const total = events.length;
  const visibleEvents = events.slice(0, position);
  const progress = total > 0 ? (position / total) * 100 : 0;

  // Calculate delay between events based on timestamps
  const getDelay = useCallback(
    (idx: number): number => {
      if (idx <= 0 || idx >= events.length) return 500;
      const prev = new Date(events[idx - 1].timestamp).getTime();
      const curr = new Date(events[idx].timestamp).getTime();
      const realDelay = Math.max(50, curr - prev);
      // Clamp to reasonable range, scale by speed
      return Math.min(2000, realDelay) / speed;
    },
    [events, speed],
  );

  // Playback loop
  useEffect(() => {
    if (!playing || position >= total) {
      if (position >= total) setPlaying(false);
      return;
    }

    const delay = getDelay(position);
    timerRef.current = setTimeout(() => {
      setPosition((p) => p + 1);
    }, delay);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [playing, position, total, getDelay]);

  const play = useCallback(() => {
    if (position >= total) setPosition(0);
    setPlaying(true);
  }, [position, total]);

  const pause = useCallback(() => setPlaying(false), []);
  const reset = useCallback(() => {
    setPlaying(false);
    setPosition(0);
  }, []);

  const scrubTo = useCallback(
    (pos: number) => setPosition(Math.max(0, Math.min(total, pos))),
    [total],
  );

  const stepForward = useCallback(
    () => setPosition((p) => Math.min(total, p + 1)),
    [total],
  );

  const stepBackward = useCallback(
    () => setPosition((p) => Math.max(0, p - 1)),
    [],
  );

  return {
    visibleEvents,
    position,
    playing,
    speed,
    total,
    progress,
    play,
    pause,
    reset,
    setSpeed,
    scrubTo,
    stepForward,
    stepBackward,
  };
}
