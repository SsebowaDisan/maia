export function MindMapEmptyState() {
  return (
    <div className="rounded-[24px] border border-black/[0.06] bg-white p-5 text-[12px] text-[#6e6e73] shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">Research artifact</p>
      <p className="mt-2 text-[16px] font-semibold tracking-[-0.02em] text-[#17171b]">Mind map unavailable</p>
      <p className="mt-1 leading-5">
        No structured knowledge map was produced for this answer. Ask a research or analytical question to generate one.
      </p>
    </div>
  );
}
