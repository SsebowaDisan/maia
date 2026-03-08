import { Pause, Play, SkipBack, SkipForward, Timer } from "lucide-react";

type ActivityHeaderProps = {
  streaming: boolean;
  isExporting: boolean;
  runId: string;
  isPlaying: boolean;
  speed: number;
  onExport: () => void;
  onJumpFirst: () => void;
  onTogglePlay: () => void;
  onJumpLast: () => void;
  onCycleSpeed: () => void;
};

function ActivityHeader({
  streaming,
  isExporting,
  runId,
  isPlaying,
  speed,
  onExport,
  onJumpFirst,
  onTogglePlay,
  onJumpLast,
  onCycleSpeed,
}: ActivityHeaderProps) {
  return (
    <div className="mb-3 flex items-start justify-between gap-3">
      <div>
        <p className="text-[11px] tracking-[0.04em] text-[#86868b]">Agent activity</p>
        <p className="text-[16px] font-semibold text-[#1d1d1f]">
          {streaming ? "Live execution feed" : "Replay timeline"}
        </p>
      </div>

      <div className="inline-flex items-center gap-1 rounded-xl border border-black/[0.08] bg-white/90 p-1 backdrop-blur">
        <button
          type="button"
          onClick={onExport}
          disabled={isExporting || !runId}
          className="rounded-lg px-2 py-1.5 text-[11px] text-[#4c4c50] transition hover:bg-[#f3f3f5] disabled:cursor-not-allowed disabled:opacity-50"
          title="Export run JSON"
        >
          {isExporting ? "Exporting..." : "Export"}
        </button>
        <button
          type="button"
          onClick={onJumpFirst}
          className="rounded-lg p-2 text-[#6e6e73] transition hover:bg-[#f3f3f5]"
          title="Jump to first step"
        >
          <SkipBack className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={onTogglePlay}
          disabled={streaming}
          className="rounded-lg p-2 text-[#1d1d1f] transition hover:bg-[#f3f3f5] disabled:cursor-not-allowed disabled:opacity-50"
          title={isPlaying ? "Pause replay" : "Play replay"}
        >
          {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
        </button>
        <button
          type="button"
          onClick={onJumpLast}
          className="rounded-lg p-2 text-[#6e6e73] transition hover:bg-[#f3f3f5]"
          title="Jump to latest step"
        >
          <SkipForward className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={onCycleSpeed}
          disabled={streaming}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-[11px] font-medium text-[#4c4c50] transition hover:bg-[#f3f3f5] disabled:cursor-not-allowed disabled:opacity-50"
          title="Cycle replay speed"
        >
          <Timer className="h-3.5 w-3.5" />
          {speed}x
        </button>
      </div>
    </div>
  );
}

export { ActivityHeader };
