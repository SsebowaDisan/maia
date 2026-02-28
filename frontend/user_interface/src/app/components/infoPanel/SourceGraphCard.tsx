import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { ArrowUpRight, Filter, RotateCcw, Search } from "lucide-react";
import type {
  ClaimInsight,
  ContradictionFinding,
  ContradictionSeverity,
  SourceGraph,
} from "../../utils/infoInsights";
import { SourceGraphViewport } from "./SourceGraphViewport";

const compact = (text: string, maxLength: number) =>
  text.length <= maxLength ? text : text.slice(0, Math.max(0, maxLength - 1)).trimEnd() + "...";
function SourceGraphCard({
  graph,
  claimInsights,
  contradictions,
  selectedClaimId,
  onSelectClaim,
  onOpenEvidence,
}: {
  graph: SourceGraph;
  claimInsights: ClaimInsight[];
  contradictions: ContradictionFinding[];
  selectedClaimId: string | null;
  onSelectClaim: (claimId: string) => void;
  onOpenEvidence: (claimId: string, evidenceId?: string) => void;
}) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);
  const [edgeFilter, setEdgeFilter] = useState<"all" | "supported" | "weak" | "contradiction">(
    "all",
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [minEdgeWeight, setMinEdgeWeight] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragState, setDragState] = useState<{
    active: boolean;
    startX: number;
    startY: number;
    baseX: number;
    baseY: number;
  } | null>(null);
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    title: string;
    subtitle: string;
  } | null>(null);

  const claimById = useMemo(
    () => new Map(claimInsights.map((claim) => [claim.id, claim])),
    [claimInsights],
  );
  const sourceById = useMemo(
    () => new Map(graph.sourceNodes.map((source) => [source.id, source])),
    [graph.sourceNodes],
  );
  const query = searchQuery.trim().toLowerCase();
  const contradictionRank: Record<ContradictionSeverity, number> = {
    high: 3,
    medium: 2,
    low: 1,
  };
  const contradictionMap = useMemo(() => {
    const result = new Map<string, ContradictionSeverity>();
    for (const item of contradictions) {
      if (!item.claimId || !item.evidenceId) {
        continue;
      }
      const key = `${item.claimId}::${item.evidenceId}`;
      const current = result.get(key);
      if (!current || contradictionRank[item.severity] > contradictionRank[current]) {
        result.set(key, item.severity);
      }
    }
    return result;
  }, [contradictions]);

  const edgeMeta = useMemo(() => {
    return graph.edges.map((edge) => {
      const claim = claimById.get(edge.claimId);
      const contradictionSeverity = edge.evidenceIds.reduce<ContradictionSeverity | null>(
        (highest, evidenceId) => {
          const level = contradictionMap.get(`${edge.claimId}::${evidenceId}`);
          if (!level) {
            return highest;
          }
          if (!highest || contradictionRank[level] > contradictionRank[highest]) {
            return level;
          }
          return highest;
        },
        null,
      );
      const category = contradictionSeverity
        ? "contradiction"
        : claim?.status === "supported"
          ? "supported"
          : "weak";
      return {
        edge,
        category,
        contradictionSeverity,
      };
    });
  }, [graph.edges, claimById, contradictionMap]);

  const filteredEdges = useMemo(() => {
    return edgeMeta.filter((item) => {
      if (item.edge.weight < minEdgeWeight) {
        return false;
      }
      if (edgeFilter === "all") {
        // continue to search filtering
      } else if (item.category !== edgeFilter) {
        return false;
      }
      if (!query) {
        return true;
      }
      const claimText = `${claimById.get(item.edge.claimId)?.text || ""}`.toLowerCase();
      const sourceText = `${sourceById.get(item.edge.sourceId)?.label || ""}`.toLowerCase();
      return claimText.includes(query) || sourceText.includes(query);
    });
  }, [edgeMeta, edgeFilter, minEdgeWeight, query, claimById, sourceById]);

  const visibleEdges = useMemo(() => {
    if (!focusNodeId) {
      return filteredEdges;
    }
    return filteredEdges.filter(
      (item) => item.edge.claimId === focusNodeId || item.edge.sourceId === focusNodeId,
    );
  }, [filteredEdges, focusNodeId]);

  const visibleNodeIds = useMemo(() => {
    const ids = new Set<string>();
    for (const item of visibleEdges) {
      ids.add(item.edge.claimId);
      ids.add(item.edge.sourceId);
    }
    if (focusNodeId) {
      ids.add(focusNodeId);
    }
    return ids;
  }, [visibleEdges, focusNodeId]);
  const connectedClaimIds = new Set(visibleEdges.map((item) => item.edge.claimId));

  if (!graph.claimNodes.length || !graph.sourceNodes.length) {
    return (
      <div className="rounded-xl border border-dashed border-[#d2d2d7] bg-[#fafafa] p-4 text-[12px] text-[#6e6e73]">
        Source graph appears after claims are mapped to indexed evidence.
      </div>
    );
  }

  const width = 420;
  const rows = Math.max(graph.claimNodes.length, graph.sourceNodes.length);
  const height = Math.max(230, rows * 50 + 34);
  const claimX = 110;
  const sourceX = 310;
  const claimPos = new Map(
    graph.claimNodes.map((node, i) => [
      node.id,
      {
        x: claimX,
        y:
          graph.claimNodes.length === 1
            ? height / 2
            : 24 + (i * (height - 48)) / Math.max(graph.claimNodes.length - 1, 1),
      },
    ]),
  );
  const sourcePos = new Map(
    graph.sourceNodes.map((node, i) => [
      node.id,
      {
        x: sourceX,
        y:
          graph.sourceNodes.length === 1
            ? height / 2
            : 24 + (i * (height - 48)) / Math.max(graph.sourceNodes.length - 1, 1),
      },
    ]),
  );

  useEffect(() => {
    if (focusNodeId && !claimById.has(focusNodeId) && !graph.sourceNodes.some((node) => node.id === focusNodeId)) {
      setFocusNodeId(null);
    }
  }, [focusNodeId, claimById, graph.sourceNodes]);

  const updateTooltip = (
    event: ReactMouseEvent<SVGElement | SVGGElement>,
    title: string,
    subtitle: string,
  ) => {
    const container = viewportRef.current;
    if (!container) {
      return;
    }
    const rect = container.getBoundingClientRect();
    setTooltip({
      x: event.clientX - rect.left + 12,
      y: event.clientY - rect.top + 12,
      title,
      subtitle,
    });
  };

  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
    setFocusNodeId(null);
    setEdgeFilter("all");
    setSearchQuery("");
    setMinEdgeWeight(0);
  };

  const selectedClaim = selectedClaimId ? claimById.get(selectedClaimId) || null : null;
  const selectedClaimTopEvidence = selectedClaim?.matchedEvidenceIds?.[0];
  const activeEdgeCount = visibleEdges.length;
  const activeSourceCount = new Set(visibleEdges.map((item) => item.edge.sourceId)).size;
  const strongestEdge = visibleEdges
    .slice()
    .sort((left, right) => right.edge.weight - left.edge.weight)[0];
  const strongestClaim = strongestEdge
    ? claimById.get(strongestEdge.edge.claimId) || null
    : null;
  const strongestSource = strongestEdge
    ? sourceById.get(strongestEdge.edge.sourceId) || null
    : null;
  const toggleFocusNode = (nodeId: string) => {
    setFocusNodeId((previous) => (previous === nodeId ? null : nodeId));
  };
  const clearTooltip = () => setTooltip(null);

  return (
    <div className="rounded-xl border border-black/[0.06] bg-white p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="inline-flex rounded-lg bg-[#f5f5f7] p-1">
          {[
            ["all", "All"],
            ["supported", "Supported"],
            ["weak", "Weak"],
            ["contradiction", "Contradicted"],
          ].map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setEdgeFilter(id as "all" | "supported" | "weak" | "contradiction")}
              className={`px-2 py-1 rounded-md text-[10px] transition-colors ${
                edgeFilter === id
                  ? "bg-white text-[#1d1d1f] shadow-sm"
                  : "text-[#6e6e73] hover:text-[#1d1d1f]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => {
              setEdgeFilter("contradiction");
              setFocusNodeId(null);
            }}
            className="rounded-lg border border-[#d64045]/30 bg-[#fff1f2] px-2 py-1 text-[10px] text-[#b42318] hover:bg-[#ffe7ea]"
          >
            Focus risks
          </button>
          <button
            type="button"
            onClick={resetView}
            className="inline-flex items-center gap-1 rounded-lg border border-black/[0.08] bg-white px-2 py-1 text-[10px] text-[#3a3a3c] hover:bg-[#fafafa]"
          >
            <RotateCcw className="w-3 h-3" />
            Reset
          </button>
        </div>
      </div>

      <div className="mb-2 grid grid-cols-[1fr_120px] gap-2">
        <label className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#8e8e93]" />
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search claims or sources"
            className="w-full rounded-lg border border-black/[0.08] bg-white py-1.5 pl-8 pr-2 text-[11px] text-[#1d1d1f] placeholder:text-[#8e8e93] focus:outline-none focus:ring-2 focus:ring-[#3a3a3f]/20"
          />
        </label>
        <label className="rounded-lg border border-black/[0.08] bg-white px-2 py-1.5">
          <p className="text-[9px] uppercase tracking-wide text-[#8e8e93]">Min strength</p>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={minEdgeWeight}
            onChange={(event) => setMinEdgeWeight(Number(event.target.value))}
            className="w-full accent-[#3a3a3f]"
          />
        </label>
      </div>

      <SourceGraphViewport
        viewportRef={viewportRef}
        width={width}
        height={height}
        claimX={claimX}
        sourceX={sourceX}
        pan={pan}
        zoom={zoom}
        dragState={dragState}
        tooltip={tooltip}
        graph={graph}
        visibleEdges={visibleEdges}
        claimPos={claimPos}
        sourcePos={sourcePos}
        focusNodeId={focusNodeId}
        selectedClaimId={selectedClaimId}
        visibleNodeIds={visibleNodeIds}
        setPan={setPan}
        setZoom={setZoom}
        setDragState={setDragState}
        onToggleFocusNode={toggleFocusNode}
        onSelectClaim={onSelectClaim}
        onOpenEvidence={onOpenEvidence}
        updateTooltip={updateTooltip}
        clearTooltip={clearTooltip}
      />

      <div className="mt-2 flex items-center justify-between text-[10px] text-[#6e6e73]">
        <div className="inline-flex items-center gap-1">
          <Filter className="w-3 h-3" />
          <span>Filter and focus</span>
        </div>
        <span>Drag to pan, scroll to zoom</span>
      </div>

      <div className="mt-2 rounded-lg border border-black/[0.06] bg-[#fafbff] px-3 py-2">
        <p className="text-[10px] uppercase tracking-wide text-[#6e6e73]">Strongest current path</p>
        <p className="mt-1 text-[11px] text-[#1d1d1f]">
          {strongestEdge && strongestClaim && strongestSource
            ? `${compact(strongestClaim.text, 64)} -> ${compact(
                strongestSource.label,
                36,
              )} (${Math.round(strongestEdge.edge.weight * 100)}%)`
            : "No path under current filters."}
        </p>
      </div>

      {selectedClaim ? (
        <div className="mt-2 rounded-lg border border-[#3a3a3f]/20 bg-[#f6f6f8] px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#3a3a3f]">Selected claim</p>
          <p className="mt-1 text-[11px] text-[#1d1d1f]">{compact(selectedClaim.text, 160)}</p>
          <button
            type="button"
            onClick={() => onOpenEvidence(selectedClaim.id, selectedClaimTopEvidence)}
            className="mt-2 inline-flex items-center gap-1 rounded-lg bg-[#1d1d1f] px-2.5 py-1.5 text-[10px] text-white hover:bg-[#3a3a3c]"
          >
            Open Evidence
            <ArrowUpRight className="w-3 h-3" />
          </button>
        </div>
      ) : null}

      <div className="mt-3 grid grid-cols-3 gap-2">
        <div className="rounded-lg border border-black/[0.06] bg-[#f8f9fb] px-2.5 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Claims linked</p>
          <p className="text-[13px] text-[#1d1d1f]">{connectedClaimIds.size}/{graph.claimNodes.length}</p>
        </div>
        <div className="rounded-lg border border-black/[0.06] bg-[#f8f9fb] px-2.5 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Sources</p>
          <p className="text-[13px] text-[#1d1d1f]">{activeSourceCount}</p>
        </div>
        <div className="rounded-lg border border-black/[0.06] bg-[#f8f9fb] px-2.5 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Links</p>
          <p className="text-[13px] text-[#1d1d1f]">{activeEdgeCount}</p>
        </div>
      </div>
    </div>
  );
}
export { SourceGraphCard };
