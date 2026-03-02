import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, FileText, Image as ImageIcon, Maximize2, Network, Search, Settings, ShieldAlert, Sparkles, X } from "lucide-react";
import { buildRawFileUrl } from "../../api/client";
import type { CitationFocus } from "../types";
import {
  buildClaimInsights,
  buildSourceGraph,
  detectContradictions,
  extractClaims,
  parseEvidence,
  supportRate,
} from "../utils/infoInsights";
import { renderRichText } from "../utils/richText";
import { CitationPdfPreview } from "./CitationPdfPreview";
import { MindmapCard } from "./infoPanel/MindmapCard";
import { SourceGraphCard } from "./infoPanel/SourceGraphCard";
import { claimStatusLabel, claimStatusStyle, contradictionLabel, contradictionStyle } from "./infoPanel/statusHelpers";

type InfoTab = "evidence" | "claims" | "mindmap" | "graph" | "consistency" | "actions";
const COMPACT_INFO_PANEL_BREAKPOINT = 340;

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
  const isCompactPanel = width <= COMPACT_INFO_PANEL_BREAKPOINT;
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

  const signalCards = [
    { id: "evidence", label: "Evidence", icon: Search, value: evidenceCards.length },
    { id: "claims", label: "Claims", icon: FileText, value: claimInsights.length },
    { id: "graph-links", label: "Graph links", icon: Network, value: sourceGraph.edges.length },
    { id: "contradictions", label: "Contradictions", icon: AlertTriangle, value: contradictionFindings.length },
  ];

  const tabItems: Array<{ id: InfoTab; label: string; icon: typeof Search }> = [
    { id: "evidence", label: "Evidence", icon: Search },
    { id: "claims", label: "Claims", icon: FileText },
    { id: "mindmap", label: "Mindmap", icon: Sparkles },
    { id: "graph", label: "Graph", icon: Network },
    { id: "consistency", label: "Consistency", icon: ShieldAlert },
    { id: "actions", label: "Actions", icon: CheckCircle2 },
  ];

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
              {signalCards.map((card) => {
                const Icon = card.icon;
                return (
                  <div key={card.id} className="rounded-lg bg-white p-2 border border-black/[0.05]">
                    {isCompactPanel ? (
                      <div className="flex justify-center mb-1">
                        <Icon className="w-3.5 h-3.5 text-[#86868b]" aria-hidden="true" />
                        <span className="sr-only">{card.label}</span>
                      </div>
                    ) : (
                      <p className="text-[11px] text-[#86868b]">{card.label}</p>
                    )}
                    <p className={`text-[#1d1d1f] ${isCompactPanel ? "text-[18px] text-center leading-tight" : "text-[14px]"}`}>
                      {card.value}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="bg-[#f5f5f7] rounded-xl p-1.5 grid grid-cols-6 gap-1">
            {tabItems.map((item) => {
              const Icon = item.icon;
              return (
              <button
                key={item.id}
                onClick={() => setTab(item.id)}
                aria-label={item.label}
                title={item.label}
                className={`rounded-lg transition-colors inline-flex items-center justify-center ${
                  isCompactPanel ? "h-9" : "px-2 py-2 text-[11px]"
                } ${
                  tab === item.id ? "bg-white text-[#1d1d1f] shadow-sm" : "text-[#6e6e73]"
                }`}
              >
                {isCompactPanel ? <Icon className="w-4 h-4" aria-hidden="true" /> : item.label}
              </button>
            );
            })}
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

