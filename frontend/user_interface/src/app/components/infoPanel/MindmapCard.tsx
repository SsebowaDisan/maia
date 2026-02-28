import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { ArrowUpRight, RotateCcw, Search } from "lucide-react";
import type {
  ClaimInsight,
  ContradictionFinding,
  EvidenceCard,
} from "../../utils/infoInsights";
import { claimStatusLabel } from "./statusHelpers";
import { MindmapViewport } from "./MindmapViewport";

const compact = (text: string, maxLength: number) =>
  text.length <= maxLength ? text : text.slice(0, Math.max(0, maxLength - 1)).trimEnd() + "...";

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
  evidenceCards: EvidenceCard[];
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

      <MindmapViewport
        viewportRef={viewportRef}
        width={width}
        height={height}
        rootX={rootX}
        rootY={rootY}
        pan={pan}
        zoom={zoom}
        dragState={dragState}
        tooltip={tooltip}
        rootLabel={rootLabel}
        filteredClaims={filteredClaims}
        activeClaim={activeClaim}
        activeEvidence={activeEvidence}
        activeRisks={activeRisks}
        claimPositions={claimPositions}
        evidencePositions={evidencePositions}
        riskPositions={riskPositions}
        activeClaimPoint={activeClaimPoint}
        claimTone={claimTone}
        setActiveClaimId={setActiveClaimId}
        setPan={setPan}
        setZoom={setZoom}
        setDragState={setDragState}
        onSelectClaim={onSelectClaim}
        onOpenEvidence={onOpenEvidence}
        updateTooltip={updateTooltip}
        clearTooltip={() => setTooltip(null)}
      />

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
export { MindmapCard };
