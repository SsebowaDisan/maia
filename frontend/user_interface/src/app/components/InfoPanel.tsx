import { useEffect, useMemo, useState } from "react";
import { Check, ExternalLink, FileText, Link2 } from "lucide-react";
import { toast } from "sonner";
import { buildRawFileUrl } from "../../api/client";
import type { SourceUsageRecord } from "../types";
import { buildCitationDeepLink } from "../utils/citationDeepLink";
import { buildMindmapShareLink } from "../utils/mindmapDeepLink";
import { parseEvidence } from "../utils/infoInsights";
import type { CitationFocus } from "../types";
import { CitationPdfPreview } from "./CitationPdfPreview";
import { MindmapViewer } from "./MindmapViewer";
import { PdfEvidenceMap } from "./PdfEvidenceMap";
import {
  getCitationMatchQualityLabel,
  getCitationStrengthLabel,
  getCitationStrengthLegend,
  getCitationStrengthTier,
  getClaimSignalSummary,
  getDominanceWarning,
  getMaxRetrievedCount,
  getMindmapPayload,
  getNormalizedSourceUsage,
  getTabLabels,
} from "./infoPanelDerived";

interface InfoPanelProps {
  citationFocus?: CitationFocus | null;
  selectedConversationId?: string | null;
  assistantHtml?: string;
  infoHtml?: string;
  infoPanel?: Record<string, unknown>;
  mindmap?: Record<string, unknown>;
  sourceUsage?: SourceUsageRecord[];
  indexId?: number | null;
  onClearCitationFocus?: () => void;
  onSelectCitationFocus?: (citation: CitationFocus) => void;
  onAskMindmapNode?: (payload: {
    nodeId: string;
    title: string;
    text: string;
    pageRef?: string;
    sourceId?: string;
    sourceName?: string;
  }) => void;
  width?: number;
}

export function InfoPanel({
  citationFocus = null,
  selectedConversationId = null,
  assistantHtml = "",
  infoHtml = "",
  infoPanel = {},
  mindmap = {},
  sourceUsage = [],
  indexId = null,
  onClearCitationFocus,
  onSelectCitationFocus,
  onAskMindmapNode,
  width = 340,
}: InfoPanelProps) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const [activeTab, setActiveTab] = useState<"evidence" | "sources" | "mindmap">("evidence");
  const citationRawUrl = useMemo(() => {
    if (!citationFocus?.fileId) return null;
    return buildRawFileUrl(citationFocus.fileId, {
      indexId: typeof indexId === "number" ? indexId : undefined,
    });
  }, [citationFocus, indexId]);

  const citationSourceLower = (citationFocus?.sourceName || "").toLowerCase();
  const citationIsImage = /\.(png|jpe?g|gif|bmp|webp|tiff?)$/i.test(citationSourceLower);
  const citationHasPageHint = Boolean(String(citationFocus?.page || "").trim());
  const citationStrengthTier = useMemo(() => getCitationStrengthTier(citationFocus), [citationFocus]);
  const citationStrengthLabel = useMemo(
    () => getCitationStrengthLabel(citationStrengthTier),
    [citationStrengthTier],
  );
  const citationMatchQualityLabel = useMemo(
    () => getCitationMatchQualityLabel(citationFocus),
    [citationFocus],
  );
  const citationIsPdf =
    Boolean(citationRawUrl) &&
    !citationIsImage &&
    (citationSourceLower.endsWith(".pdf") || citationHasPageHint || !citationSourceLower);
  const evidenceCards = useMemo(() => parseEvidence(infoHtml || ""), [infoHtml]);
  const tabLabels = useMemo(() => getTabLabels(infoPanel), [infoPanel]);
  const mindmapPayload = useMemo(
    () => getMindmapPayload(infoPanel, mindmap),
    [infoPanel, mindmap],
  );
  const normalizedSourceUsage = useMemo(
    () => getNormalizedSourceUsage(infoPanel, sourceUsage),
    [sourceUsage, infoPanel],
  );
  const citationStrengthLegend = useMemo(
    () => getCitationStrengthLegend(infoPanel),
    [infoPanel],
  );
  const dominanceWarning = useMemo(
    () => getDominanceWarning(infoPanel, normalizedSourceUsage),
    [infoPanel, normalizedSourceUsage],
  );
  const maxRetrievedCount = useMemo(
    () => getMaxRetrievedCount(normalizedSourceUsage),
    [normalizedSourceUsage],
  );
  const claimSignalSummary = useMemo(
    () => getClaimSignalSummary(infoPanel),
    [infoPanel],
  );

  useEffect(() => {
    if (citationFocus) {
      setActiveTab("evidence");
    }
  }, [citationFocus]);

  const handleCopyCitationLink = async () => {
    if (!citationFocus) {
      return;
    }
    const deepLink = buildCitationDeepLink({
      citationFocus,
      conversationId: selectedConversationId,
    });
    try {
      await navigator.clipboard.writeText(deepLink);
      setCopyState("copied");
      toast.success("Citation link copied");
      window.setTimeout(() => setCopyState("idle"), 1800);
    } catch {
      setCopyState("failed");
      toast.error("Unable to copy citation link");
      window.setTimeout(() => setCopyState("idle"), 1800);
    }
  };

  return (
    <div
      className="min-h-0 bg-white/80 backdrop-blur-xl border-l border-black/[0.06] flex flex-col overflow-hidden"
      style={{ width: `${Math.round(width)}px` }}
    >
      <div className="px-5 py-4 border-b border-black/[0.06]">
        <h3 className="text-[15px] tracking-tight text-[#1d1d1f]">Information panel</h3>
        <div className="mt-3 inline-flex rounded-lg border border-black/[0.08] bg-white p-0.5">
          <button
            type="button"
            onClick={() => setActiveTab("evidence")}
            className={`px-2.5 py-1 text-[11px] rounded-md transition-colors ${
              activeTab === "evidence" ? "bg-[#1d1d1f] text-white" : "text-[#6e6e73] hover:bg-black/[0.04]"
            }`}
          >
            {tabLabels.evidence}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("sources")}
            className={`px-2.5 py-1 text-[11px] rounded-md transition-colors ${
              activeTab === "sources" ? "bg-[#1d1d1f] text-white" : "text-[#6e6e73] hover:bg-black/[0.04]"
            }`}
          >
            {tabLabels.sources}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("mindmap")}
            className={`px-2.5 py-1 text-[11px] rounded-md transition-colors ${
              activeTab === "mindmap" ? "bg-[#1d1d1f] text-white" : "text-[#6e6e73] hover:bg-black/[0.04]"
            }`}
          >
            {tabLabels.mindmap}
          </button>
        </div>
      </div>

      <div id="html-info-panel" className="flex-1 overflow-y-auto px-5 py-6">
        {activeTab === "evidence" && citationFocus ? (
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
                {citationStrengthLabel ? (
                  <span
                    className="text-[10px] px-2 py-1 rounded-full bg-white border border-black/[0.08] text-[#6e6e73]"
                    title={
                      Number.isFinite(Number(citationFocus?.strengthScore))
                        ? `Strength ${Number(citationFocus?.strengthScore || 0).toFixed(3)}`
                        : "Citation strength"
                    }
                  >
                    {citationStrengthLabel}
                  </span>
                ) : null}
                {citationMatchQualityLabel ? (
                  <span className="text-[10px] px-2 py-1 rounded-full bg-white border border-black/[0.08] text-[#6e6e73]">
                    {citationMatchQualityLabel}
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
                <button
                  type="button"
                  onClick={handleCopyCitationLink}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-black/[0.08] text-[#1d1d1f] text-[10px] hover:bg-black/[0.03] transition-colors"
                  title="Copy deep-link to this citation"
                >
                  {copyState === "copied" ? <Check className="w-3 h-3" /> : <Link2 className="w-3 h-3" />}
                  {copyState === "copied"
                    ? "Copied"
                    : copyState === "failed"
                      ? "Retry"
                      : "Copy link"}
                </button>
              </div>
            </div>

            {citationRawUrl && citationIsPdf ? (
              <>
                <PdfEvidenceMap
                  fileUrl={citationRawUrl}
                  conversationId={selectedConversationId || undefined}
                  fileId={citationFocus.fileId}
                  sourceName={citationFocus.sourceName}
                  citationFocus={citationFocus}
                  assistantHtml={assistantHtml}
                  evidenceCards={evidenceCards}
                  onNavigateCitation={(next) => {
                    if (onSelectCitationFocus) {
                      onSelectCitationFocus(next);
                    }
                  }}
                />
                <CitationPdfPreview
                  key={`${citationFocus?.fileId || "file"}:${citationFocus?.page || "1"}:${String(citationFocus?.extract || "").slice(0, 64)}:${String(citationFocus?.claimText || "").slice(0, 64)}:${JSON.stringify(citationFocus?.highlightBoxes || []).slice(0, 120)}`}
                  fileUrl={citationRawUrl}
                  page={citationFocus.page}
                  highlightText={citationFocus.extract}
                  highlightQuery={citationFocus.claimText}
                  highlightBoxes={citationFocus.highlightBoxes}
                />
              </>
            ) : null}

            {citationRawUrl && citationIsImage ? (
              <div className="w-full h-[220px] rounded-xl border border-black/[0.08] bg-white overflow-hidden flex items-center justify-center">
                <img src={citationRawUrl} alt={citationFocus.sourceName} className="max-w-full max-h-full object-contain" />
              </div>
            ) : null}

            {!citationRawUrl ? (
              <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
                Source preview is unavailable for this citation.
              </div>
            ) : null}

            {onClearCitationFocus ? (
              <button
                type="button"
                onClick={onClearCitationFocus}
                className="mt-2 text-[11px] px-2.5 py-1.5 rounded-lg border border-black/[0.08] text-[#6e6e73] hover:bg-black/[0.03] transition-colors"
              >
                Close preview
              </button>
            ) : null}
          </div>
        ) : null}

        {activeTab === "evidence" && !citationFocus ? (
          <div className="rounded-xl bg-[#f5f5f7] p-4 text-[12px] text-[#6e6e73]">
            Click an inline citation in the response to preview evidence in the source file.
          </div>
        ) : null}

        {activeTab === "sources" ? (
          <div className="space-y-3">
            <div className="rounded-xl border border-black/[0.08] bg-white p-3 text-[12px] text-[#4a4a4f]">
              {citationStrengthLegend}
            </div>
            {dominanceWarning ? (
              <div className="rounded-xl border border-[#eab308]/50 bg-[#fffbeb] p-3 text-[12px] text-[#92400e]">
                {dominanceWarning}
              </div>
            ) : null}
            {claimSignalSummary ? (
              <div className="rounded-xl border border-black/[0.08] bg-white p-3 text-[12px] text-[#4a4a4f]">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-medium text-[#1d1d1f]">Claim signals</p>
                  <span className="text-[10px] text-[#6e6e73] uppercase">
                    {claimSignalSummary.claimsEvaluated} claims
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-2 text-[11px] text-[#6e6e73]">
                  <span>Supported: {claimSignalSummary.supportedClaims}</span>
                  <span>Contradicted: {claimSignalSummary.contradictedClaims}</span>
                  <span>Mixed: {claimSignalSummary.mixedClaims}</span>
                </div>
                {claimSignalSummary.rows.length ? (
                  <div className="mt-2 space-y-1.5">
                    {claimSignalSummary.rows.map((row, index) => (
                      <div key={`${row.claim}:${index}`} className="rounded-lg bg-[#f7f7f9] px-2.5 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[11px] text-[#1d1d1f] truncate" title={row.claim}>
                            {row.claim}
                          </span>
                          <span className="text-[10px] text-[#6e6e73] uppercase">
                            {row.status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            {normalizedSourceUsage.length ? (
              <div className="space-y-2">
                {normalizedSourceUsage.map((row) => {
                  const sharePct = Math.max(
                    row.citation_share * 100,
                    maxRetrievedCount > 0 ? (row.retrieved_count / maxRetrievedCount) * 28 : 0,
                  );
                  return (
                    <div key={`${row.source_id}:${row.source_name}`} className="rounded-xl border border-black/[0.08] bg-white p-3">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-[12px] font-medium text-[#1d1d1f] truncate" title={row.source_name}>
                          {row.source_name}
                        </p>
                        <span className="text-[10px] text-[#6e6e73] uppercase">{row.source_type}</span>
                      </div>
                      <div className="mt-2 h-2 w-full rounded-full bg-[#ececf0] overflow-hidden">
                        <div
                          className="h-full rounded-full bg-[#1d1d1f]"
                          style={{ width: `${Math.max(4, Math.min(100, sharePct)).toFixed(1)}%` }}
                        />
                      </div>
                      <div className="mt-2 flex items-center justify-between text-[11px] text-[#6e6e73]">
                        <span>{row.cited_count} cited</span>
                        <span>{row.retrieved_count} retrieved</span>
                      </div>
                      <div className="mt-1 text-[10px] text-[#8e8e93]">
                        max strength {row.max_strength_score.toFixed(3)} | avg {row.avg_strength_score.toFixed(3)}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="rounded-xl bg-[#f5f5f7] p-4 text-[12px] text-[#6e6e73]">
                Source usage is unavailable for this response.
              </div>
            )}
          </div>
        ) : null}

        {activeTab === "mindmap" ? (
          <MindmapViewer
            payload={mindmapPayload}
            conversationId={selectedConversationId}
            onAskNode={onAskMindmapNode}
            onSaveMap={(payload) => {
              const storageKey = "maia.saved-mindmaps";
              try {
                const existing = JSON.parse(window.localStorage.getItem(storageKey) || "{}") as Record<string, unknown>;
                const convKey = String(selectedConversationId || "global");
                const history = Array.isArray(existing[convKey]) ? (existing[convKey] as unknown[]) : [];
                const next = [...history.slice(-9), { saved_at: new Date().toISOString(), map: payload }];
                existing[convKey] = next;
                window.localStorage.setItem(storageKey, JSON.stringify(existing));
                toast.success("Mind-map saved");
              } catch {
                toast.error("Unable to save mind-map");
              }
            }}
            onShareMap={(payload) =>
              buildMindmapShareLink({
                map: payload as unknown as Record<string, unknown>,
                conversationId: selectedConversationId,
              })
            }
          />
        ) : null}
      </div>
    </div>
  );
}
