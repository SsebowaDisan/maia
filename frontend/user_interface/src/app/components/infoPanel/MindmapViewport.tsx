import type { Dispatch, MouseEvent as ReactMouseEvent, RefObject, SetStateAction } from "react";
import type { ClaimInsight, ContradictionFinding, EvidenceCard } from "../../utils/infoInsights";
import { claimStatusLabel, contradictionLabel } from "./statusHelpers";

type Point = {
  x: number;
  y: number;
};

type MindmapDragState = {
  active: boolean;
  startX: number;
  startY: number;
  baseX: number;
  baseY: number;
};

type MindmapTooltip = {
  x: number;
  y: number;
  title: string;
  subtitle: string;
};

interface MindmapViewportProps {
  viewportRef: RefObject<HTMLDivElement | null>;
  width: number;
  height: number;
  rootX: number;
  rootY: number;
  pan: Point;
  zoom: number;
  dragState: MindmapDragState | null;
  tooltip: MindmapTooltip | null;
  rootLabel: string;
  filteredClaims: ClaimInsight[];
  activeClaim: ClaimInsight | null;
  activeEvidence: EvidenceCard[];
  activeRisks: ContradictionFinding[];
  claimPositions: Map<string, Point>;
  evidencePositions: Map<string, Point>;
  riskPositions: Map<string, Point>;
  activeClaimPoint: Point | null;
  claimTone: (claim: ClaimInsight) => { fill: string; stroke: string; text: string };
  setActiveClaimId: Dispatch<SetStateAction<string | null>>;
  setPan: Dispatch<SetStateAction<Point>>;
  setZoom: Dispatch<SetStateAction<number>>;
  setDragState: Dispatch<SetStateAction<MindmapDragState | null>>;
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

const cleanSourceLabel = (source: string) => compact(source.replace(/^\[\d+\]\s*/, ""), 26);

function MindmapViewport({
  viewportRef,
  width,
  height,
  rootX,
  rootY,
  pan,
  zoom,
  dragState,
  tooltip,
  rootLabel,
  filteredClaims,
  activeClaim,
  activeEvidence,
  activeRisks,
  claimPositions,
  evidencePositions,
  riskPositions,
  activeClaimPoint,
  claimTone,
  setActiveClaimId,
  setPan,
  setZoom,
  setDragState,
  onSelectClaim,
  onOpenEvidence,
  updateTooltip,
  clearTooltip,
}: MindmapViewportProps) {
  return (
    <div
      ref={viewportRef}
      className="relative h-[330px] overflow-hidden rounded-xl border border-black/[0.06] bg-gradient-to-b from-[#f8f8fa] via-[#f5f5f7] to-[#f3f4f6]"
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
        setZoom((current) => Math.min(2, Math.max(0.72, current + direction * 0.08)));
      }}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-full select-none"
        aria-label="Mindmap view"
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
        <defs>
          <linearGradient id="mindmap-root-gradient" x1="0%" x2="100%" y1="0%" y2="100%">
            <stop offset="0%" stopColor="#1d1d1f" />
            <stop offset="100%" stopColor="#3b3b3f" />
          </linearGradient>
        </defs>
        <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
          <rect x={0} y={0} width={width} height={height} rx={18} fill="#f8f9fb" />

          {filteredClaims.map((claim) => {
            const point = claimPositions.get(claim.id);
            if (!point) {
              return null;
            }
            const active = activeClaim?.id === claim.id;
            return (
              <line
                key={`edge-root-${claim.id}`}
                x1={rootX}
                y1={rootY}
                x2={point.x}
                y2={point.y}
                stroke={active ? "#3a3a3f" : "#c7c7cc"}
                strokeWidth={active ? 2.2 : 1.2}
                strokeOpacity={active ? 0.9 : 0.65}
              />
            );
          })}

          {activeClaimPoint
            ? activeEvidence.map((card) => {
                const point = evidencePositions.get(card.id);
                if (!point) {
                  return null;
                }
                return (
                  <line
                    key={`edge-evidence-${card.id}`}
                    x1={activeClaimPoint.x}
                    y1={activeClaimPoint.y}
                    x2={point.x}
                    y2={point.y}
                    stroke="#7a7a80"
                    strokeWidth={1.5}
                    strokeOpacity={0.78}
                  />
                );
              })
            : null}

          {activeClaimPoint
            ? activeRisks.map((risk) => {
                const point = riskPositions.get(risk.id);
                if (!point) {
                  return null;
                }
                return (
                  <line
                    key={`edge-risk-${risk.id}`}
                    x1={activeClaimPoint.x}
                    y1={activeClaimPoint.y}
                    x2={point.x}
                    y2={point.y}
                    stroke="#d64045"
                    strokeWidth={1.4}
                    strokeOpacity={0.82}
                    strokeDasharray="4 3"
                  />
                );
              })
            : null}

          <circle cx={rootX} cy={rootY} r={54} fill="url(#mindmap-root-gradient)" />
          <circle cx={rootX} cy={rootY} r={62} fill="none" stroke="#2f2f34" strokeOpacity={0.15} strokeWidth={8} />
          <text x={rootX} y={rootY - 4} textAnchor="middle" fontSize="11.5" fill="#ffffff">
            Maia map
          </text>
          <text x={rootX} y={rootY + 14} textAnchor="middle" fontSize="9.5" fill="#d1d1d6">
            {compact(rootLabel, 28)}
          </text>

          {filteredClaims.map((claim) => {
            const point = claimPositions.get(claim.id);
            if (!point) {
              return null;
            }
            const tone = claimTone(claim);
            const active = activeClaim?.id === claim.id;
            return (
              <g
                key={`claim-node-${claim.id}`}
                onClick={() => {
                  setActiveClaimId(claim.id);
                  onSelectClaim(claim.id);
                }}
                onMouseMove={(event) =>
                  updateTooltip(
                    event,
                    claimStatusLabel(claim.status),
                    `${Math.round(claim.score * 100)}% support match - click to focus branch`,
                  )
                }
                onMouseLeave={clearTooltip}
                style={{ cursor: "pointer" }}
              >
                <rect
                  x={point.x - 74}
                  y={point.y - 17}
                  width={148}
                  height={34}
                  rx={12}
                  fill={tone.fill}
                  stroke={active ? "#2f2f34" : tone.stroke}
                  strokeWidth={active ? 2 : 1.2}
                  opacity={active ? 1 : 0.9}
                />
                <text x={point.x} y={point.y + 4} textAnchor="middle" fontSize="10.5" fill={tone.text}>
                  {compact(claim.text, 26)}
                </text>
              </g>
            );
          })}

          {activeClaim
            ? activeEvidence.map((card) => {
                const point = evidencePositions.get(card.id);
                if (!point) {
                  return null;
                }
                return (
                  <g
                    key={`evidence-node-${card.id}`}
                    onClick={() => onOpenEvidence(activeClaim.id, card.id)}
                    onMouseMove={(event) =>
                      updateTooltip(
                        event,
                        cleanSourceLabel(card.source),
                        `${card.page ? `page ${card.page}` : "source extract"} - click to open evidence`,
                      )
                    }
                    onMouseLeave={clearTooltip}
                    style={{ cursor: "pointer" }}
                  >
                    <rect
                      x={point.x - 78}
                      y={point.y - 15}
                      width={156}
                      height={30}
                      rx={10}
                      fill="#f3f4f6"
                      stroke="#d1d3d9"
                      strokeWidth={1.2}
                    />
                    <text x={point.x} y={point.y + 4} textAnchor="middle" fontSize="10.5" fill="#2f2f34">
                      {cleanSourceLabel(card.source)}
                    </text>
                  </g>
                );
              })
            : null}

          {activeClaim
            ? activeRisks.map((risk) => {
                const point = riskPositions.get(risk.id);
                if (!point) {
                  return null;
                }
                const severityLabel = contradictionLabel(risk.severity);
                return (
                  <g
                    key={`risk-node-${risk.id}`}
                    onClick={() => onOpenEvidence(activeClaim.id, risk.evidenceId)}
                    onMouseMove={(event) =>
                      updateTooltip(event, severityLabel, `${compact(risk.summary, 52)} - click to inspect evidence`)
                    }
                    onMouseLeave={clearTooltip}
                    style={{ cursor: "pointer" }}
                  >
                    <rect
                      x={point.x - 86}
                      y={point.y - 14}
                      width={172}
                      height={28}
                      rx={10}
                      fill="#fff1f2"
                      stroke="#efb1b5"
                      strokeWidth={1.2}
                    />
                    <text x={point.x} y={point.y + 3.5} textAnchor="middle" fontSize="10.2" fill="#b42318">
                      {compact(risk.summary, 30)}
                    </text>
                  </g>
                );
              })
            : null}
        </g>
      </svg>

      {tooltip ? (
        <div
          className="pointer-events-none absolute z-10 max-w-[220px] rounded-lg border border-black/[0.08] bg-white/95 px-2.5 py-2 shadow-[0_10px_24px_rgba(0,0,0,0.12)] backdrop-blur-md"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          <p className="text-[10px] text-[#1d1d1f]">{tooltip.title}</p>
          <p className="text-[10px] text-[#6e6e73]">{tooltip.subtitle}</p>
        </div>
      ) : null}
    </div>
  );
}

export { MindmapViewport };
