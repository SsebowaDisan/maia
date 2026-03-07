type WorkGraphToolbarProps = {
  runId: string | null;
  nodeCount: number;
  edgeCount: number;
  loading: boolean;
  streaming: boolean;
  onFocusActive?: () => void;
};

function WorkGraphToolbar({
  runId,
  nodeCount,
  edgeCount,
  loading,
  streaming,
  onFocusActive,
}: WorkGraphToolbarProps) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3 rounded-xl border border-[#d2d2d7] bg-white px-3 py-2">
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Live Work Graph</p>
        <p className="truncate text-[12px] text-[#1d1d1f]" title={runId || "No active run"}>
          {runId ? `Run ${runId}` : "No active run"}
        </p>
        <p className="text-[11px] text-[#6e6e73]">
          {nodeCount} nodes · {edgeCount} edges
          {loading ? " · loading" : ""}
          {streaming ? " · live" : ""}
        </p>
      </div>
      <button
        type="button"
        onClick={onFocusActive}
        className="rounded-lg border border-black/[0.08] px-2.5 py-1 text-[11px] text-[#1d1d1f] transition hover:bg-[#f5f5f7]"
      >
        Focus active
      </button>
    </div>
  );
}

export { WorkGraphToolbar };

