import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Maximize2,
  Network,
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
  type ContradictionSeverity,
  type SourceGraph,
} from "../utils/infoInsights";
import { renderRichText } from "../utils/richText";
import { CitationPdfPreview } from "./CitationPdfPreview";

type InfoTab = "evidence" | "claims" | "graph" | "consistency" | "actions";

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
  return "bg-[#f1f3f5] text-[#5a5f69] border-[#dfe3ea]";
}

function contradictionLabel(severity: ContradictionSeverity) {
  if (severity === "high") return "High risk";
  if (severity === "medium") return "Needs review";
  return "Possible";
}

function SourceGraphCard({
  graph,
  selectedClaimId,
  onSelectClaim,
}: {
  graph: SourceGraph;
  selectedClaimId: string | null;
  onSelectClaim: (claimId: string) => void;
}) {
  const connectedClaimIds = new Set(graph.edges.map((edge) => edge.claimId));

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

  return (
    <div className="rounded-xl border border-black/[0.06] bg-white p-3">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" role="img" aria-label="Source relationship graph">
        <rect x={0} y={0} width={width} height={height} rx={14} fill="#f8f9fb" />
        <line x1={claimX} y1={14} x2={claimX} y2={height - 14} stroke="#d7dbe3" strokeDasharray="3 4" />
        <line x1={sourceX} y1={14} x2={sourceX} y2={height - 14} stroke="#d7dbe3" strokeDasharray="3 4" />
        <text x={claimX - 18} y={18} textAnchor="end" fontSize="10" fill="#8a8f98">Claims</text>
        <text x={sourceX + 18} y={18} textAnchor="start" fontSize="10" fill="#8a8f98">Sources</text>
        {graph.edges.map((edge) => {
          const c = claimPos.get(edge.claimId);
          const s = sourcePos.get(edge.sourceId);
          if (!c || !s) return null;
          return (
            <line
              key={edge.id}
              x1={c.x}
              y1={c.y}
              x2={s.x}
              y2={s.y}
              stroke="#7aa9ff"
              strokeWidth={1 + edge.weight * 2.2}
              strokeOpacity={0.42}
            />
          );
        })}
        {graph.claimNodes.map((node) => {
          const p = claimPos.get(node.id);
          if (!p) return null;
          const active = node.id === selectedClaimId;
          return (
            <g key={node.id} onClick={() => onSelectClaim(node.id)} style={{ cursor: "pointer" }}>
              <circle
                cx={p.x}
                cy={p.y}
                r={active ? 8.5 : 7}
                fill={node.status === "supported" ? "#1f8f4c" : node.status === "weak" ? "#9c6a00" : "#c9342e"}
                opacity={connectedClaimIds.has(node.id) ? 0.95 : 0.45}
                stroke={active ? "#0b5ad9" : "none"}
                strokeWidth={active ? 2 : 0}
              />
              <text x={p.x - 12} y={p.y + 3} textAnchor="end" fontSize="10.5" fill="#1d1d1f">
                {compact(node.label, 22)}
              </text>
            </g>
          );
        })}
        {graph.sourceNodes.map((node) => {
          const p = sourcePos.get(node.id);
          if (!p) return null;
          return (
            <g key={node.id}>
              <rect x={p.x - 7} y={p.y - 7} width={14} height={14} rx={4} fill="#0b5ad9" opacity={0.85} />
              <text x={p.x + 12} y={p.y + 3} textAnchor="start" fontSize="10.5" fill="#1d1d1f">
                {compact(node.label, 24)}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <div className="rounded-lg border border-black/[0.06] bg-[#f8f9fb] px-2.5 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Claims linked</p>
          <p className="text-[13px] text-[#1d1d1f]">{connectedClaimIds.size}/{graph.claimNodes.length}</p>
        </div>
        <div className="rounded-lg border border-black/[0.06] bg-[#f8f9fb] px-2.5 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Sources</p>
          <p className="text-[13px] text-[#1d1d1f]">{graph.sourceNodes.length}</p>
        </div>
        <div className="rounded-lg border border-black/[0.06] bg-[#f8f9fb] px-2.5 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Links</p>
          <p className="text-[13px] text-[#1d1d1f]">{graph.edges.length}</p>
        </div>
      </div>
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

  useEffect(() => {
    if (selectedClaimId && !claimInsights.some((claim) => claim.id === selectedClaimId)) {
      setSelectedClaimId(null);
    }
  }, [claimInsights, selectedClaimId]);

  useEffect(() => {
    if (!focusedEvidenceId) return;
    setTab("evidence");
    const timer = window.setTimeout(() => {
      const container = panelScrollRef.current;
      if (!container) return;
      const escapedId =
        typeof CSS !== "undefined" && typeof CSS.escape === "function"
          ? CSS.escape(focusedEvidenceId)
          : focusedEvidenceId.replace(/[^a-zA-Z0-9\-_]/g, "");
      const target = container.querySelector<HTMLElement>(`#${escapedId}`);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 120);
    return () => window.clearTimeout(timer);
  }, [focusedEvidenceId, infoText]);

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

          <div className="bg-[#f5f5f7] rounded-xl p-1.5 grid grid-cols-5 gap-1">
            {[
              ["evidence", "Evidence"],
              ["claims", "Claims"],
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
                <div className="rounded-xl border border-[#0071e3]/20 bg-[#f0f7ff] p-3">
                  <p className="text-[11px] text-[#0066cc] mb-1">Focused Claim</p>
                  <p className="text-[12px] text-[#1d1d1f] leading-relaxed">{selectedClaim.text}</p>
                </div>
              ) : null}
              {filteredEvidence.length ? (
                filteredEvidence.map((card) => (
                  <div
                    key={card.id}
                    id={card.id}
                    className={`rounded-xl bg-white p-3 shadow-sm scroll-mt-4 transition-all ${
                      focusedEvidenceId && card.id === focusedEvidenceId
                        ? "border border-[#0071e3] ring-2 ring-[#0071e3]/20"
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
                    className="mt-2 text-[12px] text-[#1d1d1f] leading-relaxed space-y-2 [&_details]:mb-3 [&_details]:rounded-lg [&_details]:bg-white [&_details]:p-3 [&_summary]:cursor-pointer [&_summary]:font-medium [&_img]:max-w-full [&_img]:rounded-lg [&_a]:text-[#0071e3] hover:[&_a]:underline"
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

          {tab === "graph" ? (
            <div className="space-y-3">
              <div className="rounded-xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f9f9fb] p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Network className="w-4 h-4 text-[#0066cc]" />
                  <p className="text-[12px] text-[#1d1d1f]">Source graph</p>
                </div>
                <p className="text-[11px] text-[#6e6e73] mb-3">
                  Visual map of claim-to-source links from retrieved context.
                </p>
                <SourceGraphCard
                  graph={sourceGraph}
                  selectedClaimId={selectedClaimId}
                  onSelectClaim={(claimId) => {
                    setSelectedClaimId(claimId);
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
                  <Search className="w-3.5 h-3.5 text-[#0066cc]" />
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
