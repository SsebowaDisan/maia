import { edgeColor } from "./WorkGraphEdge";
import { statusColor } from "./WorkGraphNode";

function WorkGraphLegend() {
  const statuses = ["running", "completed", "blocked", "failed"] as const;
  const edgeFamilies = ["hierarchy", "dependency", "evidence", "verification", "handoff"] as const;
  return (
    <div className="mb-2 rounded-xl border border-[#d2d2d7] bg-white/90 px-3 py-2 text-[10px] text-[#6e6e73]">
      <div className="flex flex-wrap items-center gap-3">
        {statuses.map((status) => (
          <span key={status} className="inline-flex items-center gap-1">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: statusColor(status) }} />
            {status}
          </span>
        ))}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-3">
        {edgeFamilies.map((family) => (
          <span key={family} className="inline-flex items-center gap-1">
            <span className="h-[2px] w-3 rounded-full" style={{ backgroundColor: edgeColor(family) }} />
            {family}
          </span>
        ))}
      </div>
    </div>
  );
}

export { WorkGraphLegend };
