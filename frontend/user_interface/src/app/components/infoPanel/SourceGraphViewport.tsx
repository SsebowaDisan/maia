import type { Dispatch, MouseEvent as ReactMouseEvent, RefObject, SetStateAction } from "react";
import type { SourceGraph } from "../../utils/infoInsights";

type SourceGraphEdgeMeta = {
  edge: SourceGraph["edges"][number];
  category: "supported" | "weak" | "contradiction";
};

type SourceGraphDragState = {
  active: boolean;
  startX: number;
  startY: number;
  baseX: number;
  baseY: number;
};

type SourceGraphTooltip = {
  x: number;
  y: number;
  title: string;
  subtitle: string;
};

type Point = {
  x: number;
  y: number;
};

interface SourceGraphViewportProps {
  viewportRef: RefObject<HTMLDivElement | null>;
  width: number;
  height: number;
  claimX: number;
  sourceX: number;
  pan: Point;
  zoom: number;
  dragState: SourceGraphDragState | null;
  tooltip: SourceGraphTooltip | null;
  graph: SourceGraph;
  visibleEdges: SourceGraphEdgeMeta[];
  claimPos: Map<string, Point>;
  sourcePos: Map<string, Point>;
  focusNodeId: string | null;
  selectedClaimId: string | null;
  visibleNodeIds: Set<string>;
  setPan: Dispatch<SetStateAction<Point>>;
  setZoom: Dispatch<SetStateAction<number>>;
  setDragState: Dispatch<SetStateAction<SourceGraphDragState | null>>;
  onToggleFocusNode: (nodeId: string) => void;
  onSelectClaim: (claimId: string) => void;
  onOpenEvidence: (claimId: string, evidenceId?: string) => void;
  updateTooltip: (
    event: ReactMouseEvent<SVGElement | SVGGElement>,
    title: string,
    subtitle: string,
  ) => void;
  clearTooltip: () => void;
}

const compact = (text: string, maxLength: number) =>
  text.length <= maxLength ? text : text.slice(0, Math.max(0, maxLength - 1)).trimEnd() + "...";

function SourceGraphViewport({
  viewportRef,
  width,
  height,
  claimX,
  sourceX,
  pan,
  zoom,
  dragState,
  tooltip,
  graph,
  visibleEdges,
  claimPos,
  sourcePos,
  focusNodeId,
  selectedClaimId,
  visibleNodeIds,
  setPan,
  setZoom,
  setDragState,
  onToggleFocusNode,
  onSelectClaim,
  onOpenEvidence,
  updateTooltip,
  clearTooltip,
}: SourceGraphViewportProps) {
  return (
    <div
      ref={viewportRef}
      className="relative h-[318px] overflow-hidden rounded-xl border border-black/[0.06] bg-gradient-to-b from-[#fafafa] to-[#f4f5f8]"
      onMouseMove={(event) => {
        if (!dragState?.active) {
          return;
        }
        setPan({
          x: dragState.baseX + event.clientX - dragState.startX,
          y: dragState.baseY + event.clientY - dragState.startY,
        });
      }}
      onMouseLeave={() => {
        clearTooltip();
        setDragState((previous) => (previous ? { ...previous, active: false } : null));
      }}
      onMouseUp={() => setDragState((previous) => (previous ? { ...previous, active: false } : null))}
      onWheel={(event) => {
        event.preventDefault();
        const direction = event.deltaY > 0 ? -1 : 1;
        setZoom((current) => Math.min(1.9, Math.max(0.75, current + direction * 0.08)));
      }}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-full select-none"
        role="img"
        aria-label="Source relationship graph"
        onMouseDown={(event) => {
          if (event.button !== 0) {
            return;
          }
          setDragState({
            active: true,
            startX: event.clientX,
            startY: event.clientY,
            baseX: pan.x,
            baseY: pan.y,
          });
        }}
        onMouseUp={() => setDragState((previous) => (previous ? { ...previous, active: false } : null))}
      >
        <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
          <rect x={0} y={0} width={width} height={height} rx={14} fill="#f8f9fb" />
          <line x1={claimX} y1={14} x2={claimX} y2={height - 14} stroke="#d8d8de" strokeDasharray="3 4" />
          <line x1={sourceX} y1={14} x2={sourceX} y2={height - 14} stroke="#d8d8de" strokeDasharray="3 4" />
          <text x={claimX - 18} y={18} textAnchor="end" fontSize="10" fill="#8e8e93">
            Claims
          </text>
          <text x={sourceX + 18} y={18} textAnchor="start" fontSize="10" fill="#8e8e93">
            Sources
          </text>
          {visibleEdges.map((item) => {
            const edge = item.edge;
            const c = claimPos.get(edge.claimId);
            const s = sourcePos.get(edge.sourceId);
            if (!c || !s) {
              return null;
            }
            const stroke =
              item.category === "contradiction"
                ? "#d64045"
                : item.category === "supported"
                  ? "#3a3a3f"
                  : "#a1a1a3";
            const dashArray = item.category === "contradiction" ? "4 3" : undefined;
            return (
              <line
                key={edge.id}
                x1={c.x}
                y1={c.y}
                x2={s.x}
                y2={s.y}
                stroke={stroke}
                strokeWidth={1 + edge.weight * 2.2}
                strokeDasharray={dashArray}
                strokeOpacity={focusNodeId ? 0.85 : 0.45}
                onMouseMove={(event) =>
                  updateTooltip(
                    event,
                    item.category === "contradiction"
                      ? "Contradicted link"
                      : item.category === "supported"
                        ? "Supported link"
                        : "Weak link",
                    "Click to open supporting evidence",
                  )
                }
                onMouseLeave={clearTooltip}
                onClick={() => {
                  const evidenceId = edge.evidenceIds[0];
                  onSelectClaim(edge.claimId);
                  onOpenEvidence(edge.claimId, evidenceId);
                }}
                style={{ cursor: "pointer" }}
              />
            );
          })}
          {graph.claimNodes.map((node) => {
            const p = claimPos.get(node.id);
            if (!p) {
              return null;
            }
            const active = node.id === selectedClaimId;
            const visible = visibleNodeIds.has(node.id);
            return (
              <g
                key={node.id}
                onClick={() => {
                  onSelectClaim(node.id);
                  onToggleFocusNode(node.id);
                }}
                onMouseMove={(event) =>
                  updateTooltip(
                    event,
                    "Claim",
                    `${Math.round((node.score || 0) * 100)}% match - click to focus`,
                  )
                }
                onMouseLeave={clearTooltip}
                style={{ cursor: "pointer" }}
              >
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={active ? 8.5 : 7}
                  fill={
                    node.status === "supported" ? "#1f8f4c" : node.status === "weak" ? "#9c6a00" : "#c9342e"
                  }
                  opacity={visible ? 0.96 : 0.22}
                  stroke={active ? "#2f2f34" : "none"}
                  strokeWidth={active ? 2 : 0}
                />
                <text x={p.x - 12} y={p.y + 3} textAnchor="end" fontSize="10.5" fill={visible ? "#1d1d1f" : "#9a9aa0"}>
                  {compact(node.label, 22)}
                </text>
              </g>
            );
          })}
          {graph.sourceNodes.map((node) => {
            const p = sourcePos.get(node.id);
            if (!p) {
              return null;
            }
            const visible = visibleNodeIds.has(node.id);
            const focused = focusNodeId === node.id;
            return (
              <g
                key={node.id}
                onClick={() => onToggleFocusNode(node.id)}
                onMouseMove={(event) =>
                  updateTooltip(event, "Source", `${node.evidenceCount || 0} evidence chunk(s) - click to isolate`)
                }
                onMouseLeave={clearTooltip}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x={p.x - 7}
                  y={p.y - 7}
                  width={14}
                  height={14}
                  rx={4}
                  fill="#2f2f34"
                  opacity={visible ? 0.88 : 0.2}
                  stroke={focused ? "#1d1d1f" : "none"}
                  strokeWidth={focused ? 1.4 : 0}
                />
                <text x={p.x + 12} y={p.y + 3} textAnchor="start" fontSize="10.5" fill={visible ? "#1d1d1f" : "#9a9aa0"}>
                  {compact(node.label, 24)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      {tooltip ? (
        <div
          className="pointer-events-none absolute z-10 max-w-[210px] rounded-lg border border-black/[0.08] bg-white/95 px-2.5 py-2 shadow-[0_10px_24px_rgba(0,0,0,0.12)] backdrop-blur-md"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <p className="text-[10px] text-[#1d1d1f]">{tooltip.title}</p>
          <p className="text-[10px] text-[#6e6e73]">{tooltip.subtitle}</p>
        </div>
      ) : null}
    </div>
  );
}

export { SourceGraphViewport };
