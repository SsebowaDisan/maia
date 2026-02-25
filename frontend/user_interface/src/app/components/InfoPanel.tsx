import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import {
  ArrowUpRight,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  FileText,
  Filter,
  Image as ImageIcon,
  Maximize2,
  Network,
  RotateCcw,
  Search,
  Settings,
  ShieldAlert,
  Sparkles,
  X,
} from "lucide-react";
import { buildRawFileUrl } from "../../api/client";
import type { CitationFocus } from "../types";
import {
  buildClaimInsights,
  buildSourceGraph,
  detectContradictions,
  extractClaims,
  parseEvidence,
  supportRate,
  type ClaimInsight,
  type ContradictionFinding,
  type ContradictionSeverity,
  type SourceGraph,
} from "../utils/infoInsights";
import { renderRichText } from "../utils/richText";
import { CitationPdfPreview } from "./CitationPdfPreview";

type InfoTab = "evidence" | "claims" | "mindmap" | "graph" | "consistency" | "actions";

interface InfoPanelProps {
  messageCount: number;
  sourceCount: number;
  infoText: string;
  answerText?: string;
  questionText?: string;
  citationFocus?: CitationFocus | null;
  indexId?: number | null;
  onClearCitationFocus?: () => void;
  width?: number;
}

const compact = (text: string, maxLength: number) =>
  text.length <= maxLength ? text : `${text.slice(0, Math.max(0, maxLength - 1)).trimEnd()}...`;

function claimStatusStyle(status: ClaimInsight["status"]) {
  if (status === "supported") return "bg-[#e8f6ed] text-[#1f8f4c] border-[#1f8f4c]/20";
  if (status === "weak") return "bg-[#fff7e5] text-[#9c6a00] border-[#9c6a00]/20";
  return "bg-[#fdecec] text-[#c9342e] border-[#c9342e]/20";
}

function claimStatusLabel(status: ClaimInsight["status"]) {
  if (status === "supported") return "Supported";
  if (status === "weak") return "Weak";
  return "Missing";
}

function contradictionStyle(severity: ContradictionSeverity) {
  if (severity === "high") return "bg-[#fdecec] text-[#b42318] border-[#f7c1c1]";
  if (severity === "medium") return "bg-[#fff7e5] text-[#9c6a00] border-[#f0d9a1]";
  return "bg-[#f1f3f5] text-[#5d5d63] border-[#dcdde2]";
}

function contradictionLabel(severity: ContradictionSeverity) {
  if (severity === "high") return "High risk";
  if (severity === "medium") return "Needs review";
  return "Possible";
}

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
          setTooltip(null);
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
                      `Click to open supporting evidence`,
                    )
                  }
                  onMouseLeave={() => setTooltip(null)}
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
                    setFocusNodeId((previous) => (previous === node.id ? null : node.id));
                  }}
                  onMouseMove={(event) =>
                    updateTooltip(
                      event,
                      "Claim",
                      `${Math.round((node.score || 0) * 100)}% match - click to focus`,
                    )
                  }
                  onMouseLeave={() => setTooltip(null)}
                  style={{ cursor: "pointer" }}
                >
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r={active ? 8.5 : 7}
                    fill={
                      node.status === "supported"
                        ? "#1f8f4c"
                        : node.status === "weak"
                          ? "#9c6a00"
                          : "#c9342e"
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
                  onClick={() => setFocusNodeId((previous) => (previous === node.id ? null : node.id))}
                  onMouseMove={(event) =>
                    updateTooltip(
                      event,
                      "Source",
                      `${node.evidenceCount || 0} evidence chunk(s) - click to isolate`,
                    )
                  }
                  onMouseLeave={() => setTooltip(null)}
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

function MindmapCard({
  questionText,
  claimInsights,
  evidenceCards,
  contradictions,
  selectedClaimId,
  onSelectClaim,
  onOpenEvidence,
}: {
  questionText: string;
  claimInsights: ClaimInsight[];
  evidenceCards: ReturnType<typeof parseEvidence>;
  contradictions: ContradictionFinding[];
  selectedClaimId: string | null;
  onSelectClaim: (claimId: string) => void;
  onOpenEvidence: (claimId: string, evidenceId?: string) => void;
}) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [claimFilter, setClaimFilter] = useState<"all" | "supported" | "weak">("all");
  const [branchMode, setBranchMode] = useState<"balanced" | "evidence" | "risk">("balanced");
  const [searchQuery, setSearchQuery] = useState("");
  const [showRisks, setShowRisks] = useState(true);
  const [copyStatus, setCopyStatus] = useState("");
  const [activeClaimId, setActiveClaimId] = useState<string | null>(selectedClaimId);
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

  const contradictionCountByClaim = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of contradictions) {
      if (!item.claimId) {
        continue;
      }
      counts.set(item.claimId, (counts.get(item.claimId) || 0) + 1);
    }
    return counts;
  }, [contradictions]);
  const query = searchQuery.trim().toLowerCase();

  const filteredClaims = useMemo(() => {
    let base =
      claimFilter === "all"
        ? claimInsights
        : claimFilter === "supported"
          ? claimInsights.filter((claim) => claim.status === "supported")
          : claimInsights.filter((claim) => claim.status !== "supported");
    if (query) {
      base = base.filter((claim) => {
        if (claim.text.toLowerCase().includes(query)) {
          return true;
        }
        return claim.matchedEvidenceIds.some((id) =>
          evidenceCards.some((card) => card.id === id && card.source.toLowerCase().includes(query)),
        );
      });
    }
    if (branchMode === "evidence") {
      base = base.slice().sort((left, right) => right.matchedEvidenceIds.length - left.matchedEvidenceIds.length);
    } else if (branchMode === "risk") {
      base = base
        .slice()
        .sort(
          (left, right) =>
            (contradictionCountByClaim.get(right.id) || 0) -
            (contradictionCountByClaim.get(left.id) || 0),
        );
    }
    return base.slice(0, 8);
  }, [claimInsights, claimFilter, query, branchMode, contradictionCountByClaim, evidenceCards]);

  useEffect(() => {
    if (selectedClaimId && filteredClaims.some((claim) => claim.id === selectedClaimId)) {
      setActiveClaimId(selectedClaimId);
    }
  }, [selectedClaimId, filteredClaims]);

  useEffect(() => {
    if (activeClaimId && filteredClaims.some((claim) => claim.id === activeClaimId)) {
      return;
    }
    setActiveClaimId(filteredClaims[0]?.id || null);
  }, [activeClaimId, filteredClaims]);

  const activeClaim = activeClaimId
    ? filteredClaims.find((claim) => claim.id === activeClaimId) || null
    : null;
  const activeEvidence = useMemo(() => {
    if (!activeClaim) {
      return [];
    }
    return evidenceCards
      .filter((card) => activeClaim.matchedEvidenceIds.includes(card.id))
      .slice(0, 5);
  }, [activeClaim, evidenceCards]);
  const activeRisks = useMemo(() => {
    if (!activeClaim || !showRisks || branchMode === "evidence") {
      return [];
    }
    return contradictions
      .filter((finding) => finding.claimId === activeClaim.id)
      .slice(0, 4);
  }, [activeClaim, contradictions, showRisks, branchMode]);

  const recommendation = useMemo(() => {
    if (!activeClaim) {
      return "Select a claim branch to get targeted guidance.";
    }
    if (activeRisks.length > 0) {
      return "Reconcile conflicting values first, then regenerate this branch with strict evidence-only instructions.";
    }
    if (activeClaim.status === "weak" || activeClaim.status === "missing") {
      return "Ask a focused follow-up to pull stronger evidence for this branch.";
    }
    return "Expand this branch into a decision-ready summary with citations and risk notes.";
  }, [activeClaim, activeRisks]);

  const handleCopyFollowUp = async () => {
    if (!activeClaim || !navigator?.clipboard) {
      return;
    }
    const prompt = [
      questionText ? `Original question: ${questionText}` : "",
      `Focus claim: ${activeClaim.text}`,
      `Instruction: ${recommendation}`,
      "Output: concise markdown with citations and assumptions separated.",
    ]
      .filter(Boolean)
      .join("\n\n");
    await navigator.clipboard.writeText(prompt);
    setCopyStatus("Copied follow-up prompt");
    window.setTimeout(() => setCopyStatus(""), 1800);
  };

  if (!filteredClaims.length) {
    return (
      <div className="rounded-xl border border-dashed border-[#d2d2d7] bg-[#fafafa] p-4 text-[12px] text-[#6e6e73]">
        Mindmap appears after the assistant generates analyzable claims.
      </div>
    );
  }

  const width = 760;
  const height = 410;
  const rootX = 250;
  const rootY = 205;
  const claimRadius = branchMode === "evidence" ? 182 : branchMode === "risk" ? 146 : 170;
  const evidenceRadiusX = branchMode === "evidence" ? 284 : 260;
  const evidenceRadiusY = branchMode === "evidence" ? 170 : 150;
  const riskRadiusX = branchMode === "risk" ? 280 : 250;
  const riskRadiusY = branchMode === "risk" ? 190 : 170;
  const radians = (degrees: number) => (degrees * Math.PI) / 180;
  const cleanSourceLabel = (source: string) => compact(source.replace(/^\[\d+\]\s*/, ""), 26);
  const rootLabel = compact(questionText.trim() || "Conversation map", 56);

  const claimPositions = new Map<string, { x: number; y: number }>();
  filteredClaims.forEach((claim, index) => {
    const angle =
      filteredClaims.length === 1
        ? 180
        : 110 + (index * 140) / Math.max(filteredClaims.length - 1, 1);
      claimPositions.set(claim.id, {
      x: rootX + Math.cos(radians(angle)) * claimRadius,
      y: rootY + Math.sin(radians(angle)) * claimRadius,
      });
  });

  const evidencePositions = new Map<string, { x: number; y: number }>();
  activeEvidence.forEach((card, index) => {
    const angle =
      activeEvidence.length === 1
        ? 0
        : -50 + (index * 100) / Math.max(activeEvidence.length - 1, 1);
    evidencePositions.set(card.id, {
      x: rootX + Math.cos(radians(angle)) * evidenceRadiusX,
      y: rootY + Math.sin(radians(angle)) * evidenceRadiusY,
    });
  });

  const riskPositions = new Map<string, { x: number; y: number }>();
  activeRisks.forEach((risk, index) => {
    const angle =
      activeRisks.length === 1
        ? 90
        : 60 + (index * 60) / Math.max(activeRisks.length - 1, 1);
    riskPositions.set(risk.id, {
      x: rootX + Math.cos(radians(angle)) * riskRadiusX,
      y: rootY + Math.sin(radians(angle)) * riskRadiusY,
    });
  });

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
    setClaimFilter("all");
    setBranchMode("balanced");
    setSearchQuery("");
    setShowRisks(true);
    setActiveClaimId(selectedClaimId || filteredClaims[0]?.id || null);
  };

  const claimTone = (claim: ClaimInsight) => {
    if (claim.status === "supported") {
      return { fill: "#e8f6ed", stroke: "#9dd8b2", text: "#1f8f4c" };
    }
    if (claim.status === "weak") {
      return { fill: "#fff8ea", stroke: "#f2d9a4", text: "#9c6a00" };
    }
    return { fill: "#fff1f2", stroke: "#f3b3b7", text: "#b42318" };
  };

  const activeClaimPoint = activeClaim ? claimPositions.get(activeClaim.id) || null : null;

  return (
    <div className="rounded-xl border border-black/[0.06] bg-white p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="inline-flex rounded-lg bg-[#f5f5f7] p-1">
          {[
            ["all", "All claims"],
            ["supported", "Supported"],
            ["weak", "Weak or missing"],
          ].map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setClaimFilter(id as "all" | "supported" | "weak")}
              className={`px-2 py-1 rounded-md text-[10px] transition-colors ${
                claimFilter === id
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
            onClick={() => setShowRisks((current) => !current)}
            className={`rounded-lg border px-2 py-1 text-[10px] transition-colors ${
              showRisks
                ? "border-[#d64045]/30 bg-[#fff1f2] text-[#b42318]"
                : "border-black/[0.08] bg-white text-[#3a3a3c]"
            }`}
          >
            {showRisks ? "Risks on" : "Risks off"}
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

      <div className="mb-2 grid grid-cols-[1fr_auto] gap-2">
        <label className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#8e8e93]" />
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search branch text or source"
            className="w-full rounded-lg border border-black/[0.08] bg-white py-1.5 pl-8 pr-2 text-[11px] text-[#1d1d1f] placeholder:text-[#8e8e93] focus:outline-none focus:ring-2 focus:ring-[#3a3a3f]/20"
          />
        </label>
        <div className="inline-flex rounded-lg border border-black/[0.08] bg-white p-1">
          {[
            ["balanced", "Balanced"],
            ["evidence", "Evidence"],
            ["risk", "Risk"],
          ].map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              onClick={() => setBranchMode(mode as "balanced" | "evidence" | "risk")}
              className={`px-2 py-1 rounded-md text-[10px] transition-colors ${
                branchMode === mode
                  ? "bg-[#1d1d1f] text-white"
                  : "text-[#6e6e73] hover:text-[#1d1d1f]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

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
          setTooltip(null);
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
                  onMouseLeave={() => setTooltip(null)}
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
                      onMouseLeave={() => setTooltip(null)}
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
                        updateTooltip(
                          event,
                          severityLabel,
                          `${compact(risk.summary, 52)} - click to inspect evidence`,
                        )
                      }
                      onMouseLeave={() => setTooltip(null)}
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

      <div className="mt-2 flex items-center justify-between text-[10px] text-[#6e6e73]">
        <span>Drag to pan, scroll to zoom, click nodes to drill down.</span>
        <span>{activeClaim ? claimStatusLabel(activeClaim.status) : "No active claim"}</span>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2">
        <div className="rounded-lg border border-black/[0.06] bg-[#f8f9fb] px-2.5 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Claims</p>
          <p className="text-[13px] text-[#1d1d1f]">{filteredClaims.length}</p>
        </div>
        <div className="rounded-lg border border-black/[0.06] bg-[#f8f9fb] px-2.5 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Evidence links</p>
          <p className="text-[13px] text-[#1d1d1f]">{activeEvidence.length}</p>
        </div>
        <div className="rounded-lg border border-black/[0.06] bg-[#f8f9fb] px-2.5 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Risk flags</p>
          <p className="text-[13px] text-[#1d1d1f]">{activeRisks.length}</p>
        </div>
      </div>

      {activeClaim ? (
        <div className="mt-2 rounded-lg border border-[#3a3a3f]/20 bg-[#f6f6f8] px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#3a3a3f]">Focus lens</p>
          <p className="mt-1 text-[11px] text-[#1d1d1f]">{compact(activeClaim.text, 140)}</p>
          <p className="mt-1.5 text-[10px] text-[#3a3a3c]">{recommendation}</p>
          <div className="mt-2 flex items-center gap-1.5">
            <button
              type="button"
              onClick={handleCopyFollowUp}
              className="inline-flex items-center gap-1 rounded-lg border border-[#3a3a3f]/25 bg-white px-2.5 py-1.5 text-[10px] text-[#2f2f34] hover:bg-[#f3f4f6]"
            >
              Copy Follow-up
            </button>
            {copyStatus ? (
              <span className="text-[10px] text-[#1f8f4c]">{copyStatus}</span>
            ) : null}
          </div>
          <button
            type="button"
            onClick={() => onOpenEvidence(activeClaim.id, activeEvidence[0]?.id)}
            className="mt-2 inline-flex items-center gap-1 rounded-lg bg-[#1d1d1f] px-2.5 py-1.5 text-[10px] text-white hover:bg-[#3a3a3c] disabled:opacity-40 disabled:cursor-not-allowed"
            disabled={!activeEvidence.length}
          >
            Open Top Evidence
            <ArrowUpRight className="w-3 h-3" />
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function InfoPanel({
  messageCount,
  sourceCount,
  infoText,
  answerText = "",
  questionText = "",
  citationFocus = null,
  indexId = null,
  onClearCitationFocus,
  width = 340,
}: InfoPanelProps) {
  const panelScrollRef = useRef<HTMLDivElement | null>(null);
  const renderedInfo = useMemo(() => renderRichText(infoText), [infoText]);
  const evidenceCards = useMemo(() => parseEvidence(infoText), [infoText]);
  const claims = useMemo(() => extractClaims(answerText), [answerText]);
  const claimInsights = useMemo(() => buildClaimInsights(claims, evidenceCards), [claims, evidenceCards]);
  const sourceGraph = useMemo(() => buildSourceGraph(claimInsights, evidenceCards), [claimInsights, evidenceCards]);
  const contradictionFindings = useMemo(
    () => detectContradictions(claimInsights, evidenceCards),
    [claimInsights, evidenceCards],
  );
  const support = useMemo(() => supportRate(claimInsights), [claimInsights]);
  const [tab, setTab] = useState<InfoTab>("evidence");
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null);
  const [graphEvidenceFocusId, setGraphEvidenceFocusId] = useState<string | null>(null);
  const selectedClaim = selectedClaimId ? claimInsights.find((c) => c.id === selectedClaimId) || null : null;
  const filteredEvidence =
    selectedClaim && selectedClaim.matchedEvidenceIds.length
      ? evidenceCards.filter((card) => selectedClaim.matchedEvidenceIds.includes(card.id))
      : evidenceCards;
  const citationRawUrl = useMemo(() => {
    if (!citationFocus?.fileId) return null;
    return buildRawFileUrl(citationFocus.fileId, {
      indexId: typeof indexId === "number" ? indexId : undefined,
    });
  }, [citationFocus, indexId]);
  const citationSourceLower = (citationFocus?.sourceName || "").toLowerCase();
  const citationIsPdf = citationSourceLower.endsWith(".pdf");
  const citationIsImage = /\.(png|jpe?g|gif|bmp|webp|tiff?)$/i.test(citationSourceLower);
  const focusedEvidenceId = (citationFocus?.evidenceId || "").trim();
  const activeFocusedEvidenceId = graphEvidenceFocusId || focusedEvidenceId;

  useEffect(() => {
    if (selectedClaimId && !claimInsights.some((claim) => claim.id === selectedClaimId)) {
      setSelectedClaimId(null);
    }
  }, [claimInsights, selectedClaimId]);

  useEffect(() => {
    if (focusedEvidenceId) {
      setGraphEvidenceFocusId(null);
    }
  }, [focusedEvidenceId]);

  useEffect(() => {
    if (!activeFocusedEvidenceId) return;
    setTab("evidence");
    const timer = window.setTimeout(() => {
      const container = panelScrollRef.current;
      if (!container) return;
      const escapedId =
        typeof CSS !== "undefined" && typeof CSS.escape === "function"
          ? CSS.escape(activeFocusedEvidenceId)
          : activeFocusedEvidenceId.replace(/[^a-zA-Z0-9\-_]/g, "");
      const target = container.querySelector<HTMLElement>(`#${escapedId}`);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 120);
    return () => window.clearTimeout(timer);
  }, [activeFocusedEvidenceId, infoText]);

  const actionPrompts = [
    "Challenge this answer. List weak or missing claims and the evidence needed.",
    "Rewrite with deeper technical detail and practical engineering implications.",
    "Create an executive summary with objective, risks, and recommended actions.",
    "Answer again using only explicitly supported evidence. Separate assumptions.",
    "Reconcile contradictions and keep only verifiable facts with citations.",
  ];

  const handleCopy = async (prompt: string) => {
    if (!navigator?.clipboard) return;
    const combined = questionText ? `Original question: ${questionText}\n\nInstruction: ${prompt}` : prompt;
    await navigator.clipboard.writeText(combined);
  };

  return (
    <div
      className="min-h-0 bg-white/80 backdrop-blur-xl border-l border-black/[0.06] flex flex-col overflow-hidden"
      style={{ width: `${Math.round(width)}px` }}
    >
      <div className="px-5 py-4 border-b border-black/[0.06]">
        <div className="flex items-center justify-between">
          <h3 className="text-[15px] tracking-tight text-[#1d1d1f]">Information panel</h3>
          <div className="flex items-center gap-1">
            <button className="p-1.5 rounded-lg hover:bg-black/5 transition-colors">
              <Maximize2 className="w-4 h-4 text-[#86868b]" />
            </button>
            <button className="p-1.5 rounded-lg hover:bg-black/5 transition-colors">
              <Settings className="w-4 h-4 text-[#86868b]" />
            </button>
          </div>
        </div>
      </div>

      <div id="html-info-panel" ref={panelScrollRef} className="flex-1 overflow-y-auto px-5 py-6">
        <div className="space-y-5">
          {citationFocus ? (
            <div className="rounded-2xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f6f7fa] p-3 shadow-sm">
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-[#f2f2f7] border border-black/[0.06] flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4 text-[#3a3a3c]" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Citation preview</p>
                    <p className="text-[13px] text-[#1d1d1f] truncate" title={citationFocus.sourceName}>
                      {citationFocus.sourceName}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {citationFocus.page ? (
                    <span className="text-[10px] px-2 py-1 rounded-full bg-white border border-black/[0.08] text-[#6e6e73]">
                      page {citationFocus.page}
                    </span>
                  ) : null}
                  {citationRawUrl ? (
                    <a
                      href={citationRawUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#1d1d1f] text-white text-[10px] hover:bg-[#3a3a3c] transition-colors"
                    >
                      <ExternalLink className="w-3 h-3" />
                      Open
                    </a>
                  ) : null}
                  {onClearCitationFocus ? (
                    <button
                      type="button"
                      onClick={onClearCitationFocus}
                      className="p-1.5 rounded-lg text-[#8e8e93] hover:text-[#1d1d1f] hover:bg-black/[0.04] transition-colors"
                      aria-label="Clear citation preview"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  ) : null}
                </div>
              </div>
              {citationRawUrl && citationIsPdf ? (
                <CitationPdfPreview
                  fileUrl={citationRawUrl}
                  page={citationFocus.page}
                  highlightText={citationFocus.extract}
                />
              ) : null}
              {citationRawUrl && citationIsImage ? (
                <div className="w-full h-[220px] rounded-xl border border-black/[0.08] bg-white overflow-hidden flex items-center justify-center">
                  <img src={citationRawUrl} alt={citationFocus.sourceName} className="max-w-full max-h-full object-contain" />
                </div>
              ) : null}
              <div className="mt-2 rounded-xl border border-black/[0.06] bg-white p-2.5">
                <p className="text-[10px] uppercase tracking-wide text-[#8e8e93] mb-1">Extracted evidence</p>
                <p className="text-[12px] leading-relaxed text-[#1d1d1f]">
                  <mark className="bg-[#fff4b7] px-1 rounded">{citationFocus.extract}</mark>
                </p>
              </div>
            </div>
          ) : null}

          <div className="rounded-xl bg-gradient-to-br from-[#f8f9fb] to-[#eef2f7] p-4 border border-black/[0.05]">
            <div className="flex items-start justify-between mb-3">
              <div>
                <p className="text-[12px] text-[#6e6e73] uppercase tracking-wide">Answer Signal</p>
                <p className="text-[22px] leading-tight text-[#1d1d1f]">{support}%</p>
                <p className="text-[12px] text-[#6e6e73]">claims strongly supported</p>
              </div>
              <div className="w-12 h-12 rounded-full bg-white border border-black/[0.06] flex items-center justify-center shadow-sm">
                <Sparkles className="w-5 h-5 text-[#1d1d1f]" />
              </div>
            </div>
            <div className="grid grid-cols-4 gap-2">
              <div className="rounded-lg bg-white p-2 border border-black/[0.05]">
                <p className="text-[11px] text-[#86868b]">Evidence</p>
                <p className="text-[14px] text-[#1d1d1f]">{evidenceCards.length}</p>
              </div>
              <div className="rounded-lg bg-white p-2 border border-black/[0.05]">
                <p className="text-[11px] text-[#86868b]">Claims</p>
                <p className="text-[14px] text-[#1d1d1f]">{claimInsights.length}</p>
              </div>
              <div className="rounded-lg bg-white p-2 border border-black/[0.05]">
                <p className="text-[11px] text-[#86868b]">Graph links</p>
                <p className="text-[14px] text-[#1d1d1f]">{sourceGraph.edges.length}</p>
              </div>
              <div className="rounded-lg bg-white p-2 border border-black/[0.05]">
                <p className="text-[11px] text-[#86868b]">Contrad.</p>
                <p className="text-[14px] text-[#1d1d1f]">{contradictionFindings.length}</p>
              </div>
            </div>
          </div>

          <div className="bg-[#f5f5f7] rounded-xl p-1.5 grid grid-cols-6 gap-1">
            {[
              ["evidence", "Evidence"],
              ["claims", "Claims"],
              ["mindmap", "Mindmap"],
              ["graph", "Graph"],
              ["consistency", "Consistency"],
              ["actions", "Actions"],
            ].map(([id, label]) => (
              <button
                key={id}
                onClick={() => setTab(id as InfoTab)}
                className={`px-2 py-2 rounded-lg text-[11px] transition-colors ${
                  tab === id ? "bg-white text-[#1d1d1f] shadow-sm" : "text-[#6e6e73]"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === "evidence" ? (
            <div className="space-y-3">
              {selectedClaim ? (
                <div className="rounded-xl border border-[#3a3a3f]/20 bg-[#f6f6f8] p-3">
                  <p className="text-[11px] text-[#3a3a3f] mb-1">Focused Claim</p>
                  <p className="text-[12px] text-[#1d1d1f] leading-relaxed">{selectedClaim.text}</p>
                </div>
              ) : null}
              {filteredEvidence.length ? (
                filteredEvidence.map((card) => (
                  <div
                    key={card.id}
                    id={card.id}
                    className={`rounded-xl bg-white p-3 shadow-sm scroll-mt-4 transition-all ${
                      activeFocusedEvidenceId && card.id === activeFocusedEvidenceId
                        ? "border border-[#3a3a3f] ring-2 ring-[#3a3a3f]/20"
                        : "border border-black/[0.06]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div>
                        <p className="text-[12px] text-[#1d1d1f] leading-tight">{card.source}</p>
                        <p className="text-[11px] text-[#86868b]">{card.title}</p>
                      </div>
                      {card.page ? (
                        <span className="text-[10px] px-2 py-1 rounded-full bg-[#f5f5f7] text-[#6e6e73]">
                          page {card.page}
                        </span>
                      ) : null}
                    </div>
                    <p className="text-[12px] text-[#3a3a3c] leading-relaxed">{card.extract}</p>
                    {card.imageSrc ? (
                      <div className="mt-3 rounded-lg overflow-hidden border border-black/[0.06] bg-[#f5f5f7]">
                        <img src={card.imageSrc} alt={card.source} className="w-full h-auto max-h-[180px] object-contain" />
                      </div>
                    ) : null}
                  </div>
                ))
              ) : (
                <div className="rounded-xl bg-[#f5f5f7] p-4 text-[12px] text-[#6e6e73]">
                  No evidence matched this claim yet.
                </div>
              )}
              {renderedInfo ? (
                <details className="rounded-xl bg-[#f5f5f7] p-3">
                  <summary className="cursor-pointer text-[12px] text-[#6e6e73]">Raw retrieval stream</summary>
                  <div
                    className="mt-2 text-[12px] text-[#1d1d1f] leading-relaxed space-y-2 [&_details]:mb-3 [&_details]:rounded-lg [&_details]:bg-white [&_details]:p-3 [&_summary]:cursor-pointer [&_summary]:font-medium [&_img]:max-w-full [&_img]:rounded-lg [&_a]:text-[#3a3a3f] hover:[&_a]:underline"
                    dangerouslySetInnerHTML={{ __html: renderedInfo }}
                  />
                </details>
              ) : null}
            </div>
          ) : null}

          {tab === "claims" ? (
            <div className="space-y-2">
              {claimInsights.length ? (
                claimInsights.map((claim) => (
                  <button
                    key={claim.id}
                    type="button"
                    onClick={() => {
                      setSelectedClaimId(claim.id);
                      setTab("evidence");
                    }}
                    className="w-full text-left rounded-xl bg-white border border-black/[0.06] p-3 hover:bg-[#fafafa] transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <span className={`text-[10px] px-2 py-1 rounded-full border ${claimStatusStyle(claim.status)}`}>
                        {claimStatusLabel(claim.status)}
                      </span>
                      <span className="text-[10px] text-[#86868b]">{Math.round(claim.score * 100)}% match</span>
                    </div>
                    <p className="text-[12px] text-[#1d1d1f] leading-relaxed">{claim.text}</p>
                  </button>
                ))
              ) : (
                <div className="rounded-xl bg-[#f5f5f7] p-4 text-[12px] text-[#6e6e73]">
                  No answer claims to analyze yet.
                </div>
              )}
            </div>
          ) : null}

          {tab === "mindmap" ? (
            <div className="space-y-3">
              <div className="rounded-xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f9f9fb] p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles className="w-4 h-4 text-[#3a3a3f]" />
                  <p className="text-[12px] text-[#1d1d1f]">Mindmap</p>
                </div>
                <p className="text-[11px] text-[#6e6e73] mb-3">
                  Interactive answer map: claims, evidence paths, and contradiction hotspots.
                </p>
                <MindmapCard
                  questionText={questionText}
                  claimInsights={claimInsights}
                  evidenceCards={evidenceCards}
                  contradictions={contradictionFindings}
                  selectedClaimId={selectedClaimId}
                  onSelectClaim={(claimId) => {
                    setSelectedClaimId(claimId);
                  }}
                  onOpenEvidence={(claimId, evidenceId) => {
                    setSelectedClaimId(claimId);
                    setGraphEvidenceFocusId(evidenceId || null);
                    setTab("evidence");
                  }}
                />
              </div>
            </div>
          ) : null}

          {tab === "graph" ? (
            <div className="space-y-3">
              <div className="rounded-xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f9f9fb] p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Network className="w-4 h-4 text-[#3a3a3f]" />
                  <p className="text-[12px] text-[#1d1d1f]">Source graph</p>
                </div>
                <p className="text-[11px] text-[#6e6e73] mb-3">
                  Visual map of claim-to-source links from retrieved context.
                </p>
                <SourceGraphCard
                  graph={sourceGraph}
                  claimInsights={claimInsights}
                  contradictions={contradictionFindings}
                  selectedClaimId={selectedClaimId}
                  onSelectClaim={(claimId) => {
                    setSelectedClaimId(claimId);
                  }}
                  onOpenEvidence={(claimId, evidenceId) => {
                    setSelectedClaimId(claimId);
                    setGraphEvidenceFocusId(evidenceId || null);
                    setTab("evidence");
                  }}
                />
              </div>
            </div>
          ) : null}

          {tab === "consistency" ? (
            <div className="space-y-2">
              {contradictionFindings.length ? (
                contradictionFindings.map((finding) => (
                  <button
                    key={finding.id}
                    type="button"
                    onClick={() => {
                      if (finding.claimId) {
                        setSelectedClaimId(finding.claimId);
                        setTab("evidence");
                      }
                    }}
                    className="w-full text-left rounded-xl bg-white border border-black/[0.06] p-3 hover:bg-[#fafafa] transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <span className={`text-[10px] px-2 py-1 rounded-full border ${contradictionStyle(finding.severity)}`}>
                        {contradictionLabel(finding.severity)}
                      </span>
                      <span className="text-[10px] text-[#86868b]">{Math.round(finding.confidence * 100)}% confidence</span>
                    </div>
                    <p className="text-[12px] text-[#1d1d1f]">{finding.summary}</p>
                    <p className="text-[11px] text-[#6e6e73] mt-1 leading-relaxed">{finding.detail}</p>
                    {finding.source ? (
                      <p className="text-[10px] text-[#86868b] mt-2">Source: {finding.source}</p>
                    ) : null}
                  </button>
                ))
              ) : (
                <div className="rounded-xl border border-[#d2e8d8] bg-[#edf9f1] p-4 text-[12px] text-[#2f7d4d]">
                  No contradictions detected in the current claim-evidence mapping.
                </div>
              )}
            </div>
          ) : null}

          {tab === "actions" ? (
            <div className="space-y-3">
              {actionPrompts.map((prompt) => (
                <div key={prompt} className="rounded-xl bg-white border border-black/[0.06] p-3">
                  <p className="text-[11px] text-[#6e6e73] leading-relaxed mb-2">{prompt}</p>
                  <button
                    type="button"
                    onClick={() => void handleCopy(prompt)}
                    className="text-[11px] px-2.5 py-1.5 rounded-lg bg-[#1d1d1f] text-white hover:bg-[#3a3a3c] transition-colors"
                  >
                    Copy prompt
                  </button>
                </div>
              ))}
              <div className="rounded-xl bg-[#f5f5f7] p-3 space-y-2">
                <div className="flex items-center gap-2 text-[11px] text-[#6e6e73]">
                  <CheckCircle2 className="w-3.5 h-3.5 text-[#1f8f4c]" />
                  <span>Supported claims are traceable to retrieved evidence.</span>
                </div>
                <div className="flex items-center gap-2 text-[11px] text-[#6e6e73]">
                  <AlertTriangle className="w-3.5 h-3.5 text-[#c77a00]" />
                  <span>Weak claims need additional chunks or higher OCR quality.</span>
                </div>
                <div className="flex items-center gap-2 text-[11px] text-[#6e6e73]">
                  <ShieldAlert className="w-3.5 h-3.5 text-[#b42318]" />
                  <span>Contradiction detector flags conflicting values and language.</span>
                </div>
                <div className="flex items-center gap-2 text-[11px] text-[#6e6e73]">
                  <Search className="w-3.5 h-3.5 text-[#3a3a3f]" />
                  <span>Use focused follow-ups to deepen technical sections.</span>
                </div>
                <div className="flex items-center gap-2 text-[11px] text-[#6e6e73]">
                  <ImageIcon className="w-3.5 h-3.5 text-[#6e6e73]" />
                  <span>Visual evidence is being used for PDF/image interpretation.</span>
                </div>
              </div>
            </div>
          ) : null}

          <div className="space-y-3">
            <div className="bg-[#f5f5f7] rounded-xl p-4">
              <div className="flex items-center justify-between">
                <span className="text-[12px] text-[#86868b]">Messages</span>
                <span className="text-[15px] text-[#1d1d1f]">{messageCount}</span>
              </div>
            </div>
            <div className="bg-[#f5f5f7] rounded-xl p-4">
              <div className="flex items-center justify-between">
                <span className="text-[12px] text-[#86868b]">Sources</span>
                <span className="text-[15px] text-[#1d1d1f]">{sourceCount}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
