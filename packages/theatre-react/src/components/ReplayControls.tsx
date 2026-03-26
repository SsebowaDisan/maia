/**
 * ReplayControls — DVR playback controls for recorded ACP runs.
 * Play/pause, speed, scrub, step forward/backward.
 */
import React from "react";
import type { ReplayState } from "../hooks/useReplay";

export interface ReplayControlsProps {
  replay: ReplayState;
  className?: string;
}

const SPEED_OPTIONS = [0.25, 0.5, 1, 2, 4, 8];

export function ReplayControls({ replay, className = "" }: ReplayControlsProps) {
  return (
    <div className={`flex items-center gap-3 rounded-lg bg-gray-900 px-4 py-2 text-white ${className}`}>
      {/* Play/Pause */}
      <button
        onClick={replay.playing ? replay.pause : replay.play}
        className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 transition-colors hover:bg-white/20"
        title={replay.playing ? "Pause" : "Play"}
      >
        {replay.playing ? (
          <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
            <rect x="6" y="4" width="4" height="16" />
            <rect x="14" y="4" width="4" height="16" />
          </svg>
        ) : (
          <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
            <polygon points="5,3 19,12 5,21" />
          </svg>
        )}
      </button>

      {/* Step backward */}
      <button
        onClick={replay.stepBackward}
        className="text-white/60 transition-colors hover:text-white"
        title="Step back"
      >
        <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
          <polygon points="19,20 9,12 19,4" />
          <rect x="5" y="4" width="2" height="16" />
        </svg>
      </button>

      {/* Step forward */}
      <button
        onClick={replay.stepForward}
        className="text-white/60 transition-colors hover:text-white"
        title="Step forward"
      >
        <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
          <polygon points="5,4 15,12 5,20" />
          <rect x="17" y="4" width="2" height="16" />
        </svg>
      </button>

      {/* Progress bar */}
      <div className="relative flex-1">
        <input
          type="range"
          min={0}
          max={replay.total}
          value={replay.position}
          onChange={(e) => replay.scrubTo(Number(e.target.value))}
          className="h-1 w-full cursor-pointer appearance-none rounded-full bg-white/20 accent-purple-500"
        />
        <div className="mt-0.5 flex justify-between text-[10px] text-white/40">
          <span>{replay.position}</span>
          <span>{replay.total} events</span>
        </div>
      </div>

      {/* Speed selector */}
      <div className="flex items-center gap-1">
        {SPEED_OPTIONS.map((s) => (
          <button
            key={s}
            onClick={() => replay.setSpeed(s)}
            className={`rounded px-1.5 py-0.5 text-[11px] transition-colors ${
              replay.speed === s
                ? "bg-purple-500 text-white"
                : "text-white/50 hover:text-white"
            }`}
          >
            {s}x
          </button>
        ))}
      </div>

      {/* Reset */}
      <button
        onClick={replay.reset}
        className="text-[11px] text-white/40 transition-colors hover:text-white"
        title="Reset"
      >
        Reset
      </button>
    </div>
  );
}
