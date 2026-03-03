import { useEffect, useMemo, useState } from "react";
import { Check, ExternalLink, FileText, Link2 } from "lucide-react";
import { toast } from "sonner";
import { buildRawFileUrl } from "../../api/client";
import type { SourceUsageRecord } from "../types";
import { buildCitationDeepLink } from "../utils/citationDeepLink";
import { parseEvidence } from "../utils/infoInsights";
import type { CitationFocus } from "../types";
import { CitationPdfPreview } from "./CitationPdfPreview";
import { PdfEvidenceMap } from "./PdfEvidenceMap";

interface InfoPanelProps {
  citationFocus?: CitationFocus | null;
  selectedConversationId?: string | null;
  assistantHtml?: string;
  infoHtml?: string;
  infoPanel?: Record<string, unknown>;
  sourceUsage?: SourceUsageRecord[];
  indexId?: number | null;
  onClearCitationFocus?: () => void;
  onSelectCitationFocus?: (citation: CitationFocus) => void;
  width?: number;
}

export function InfoPanel({
  citationFocus = null,
  selectedConversationId = null,
  assistantHtml = "",
  infoHtml = "",
  infoPanel = {},
  sourceUsage = [],
  indexId = null,
  onClearCitationFocus,
  onSelectCitationFocus,
  width = 340,
}: InfoPanelProps) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const [activeTab, setActiveTab] = useState<"evidence" | "sources">("evidence");
  const citationRawUrl = useMemo(() => {
    if (!citationFocus?.fileId) return null;
    return buildRawFileUrl(citationFocus.fileId, {
      indexId: typeof indexId === "number" ? indexId : undefined,
    });
  }, [citationFocus, indexId]);

  const citationSourceLower = (citationFocus?.sourceName || "").toLowerCase();
  const citationIsImage = /\.(png|jpe?g|gif|bmp|webp|tiff?)$/i.test(citationSourceLower);
  const citationHasPageHint = Boolean(String(citationFocus?.page || "").trim());
  const citationIsPdf =
    Boolean(citationRawUrl) &&
    !citationIsImage &&
    (citationSourceLower.endsWith(".pdf") || citationHasPageHint || !citationSourceLower);
  const evidenceCards = useMemo(() => parseEvidence(infoHtml || ""), [infoHtml]);
  const tabLabels = useMemo(() => {
    const panel = infoPanel && typeof infoPanel === "object" ? infoPanel : {};
    const labels = (panel as { tab_labels?: Record<string, unknown> }).tab_labels;
    const data = labels && typeof labels === "object" ? labels : {};
    return {
      evidence: String(data.evidence || "Evidence"),
      sources: String(data.sources || "Sources"),
    };
  }, [infoPanel]);
  const normalizedSourceUsage = useMemo(() => {
    const panel = infoPanel && typeof infoPanel === "object" ? infoPanel : {};
    const fromPanel = (panel as { source_usage?: unknown }).source_usage;
    const rows = sourceUsage.length
      ? sourceUsage
      : Array.isArray(fromPanel)
        ? fromPanel
        : [];
    return rows
      .map((row) => {
        if (!row || typeof row !== "object") {
          return null;
        }
        const record = row as Record<string, unknown>;
        const retrieved = Math.max(0, Number(record.retrieved_count || 0));
        const cited = Math.max(0, Number(record.cited_count || 0));
        const share = Math.max(0, Math.min(1, Number(record.citation_share || 0)));
        const maxStrength = Number(record.max_strength_score || 0);
        const avgStrength = Number(record.avg_strength_score || 0);
        return {
          source_id: String(record.source_id || ""),
          source_name: String(record.source_name || "Indexed source"),
          source_type: String(record.source_type || "file"),
          retrieved_count: Number.isFinite(retrieved) ? retrieved : 0,
          cited_count: Number.isFinite(cited) ? cited : 0,
          citation_share: Number.isFinite(share) ? share : 0,
          max_strength_score: Number.isFinite(maxStrength) ? maxStrength : 0,
          avg_strength_score: Number.isFinite(avgStrength) ? avgStrength : 0,
        };
      })
      .filter((row): row is SourceUsageRecord => Boolean(row))
      .sort((a, b) => {
        if (b.cited_count !== a.cited_count) {
          return b.cited_count - a.cited_count;
        }
        if (b.retrieved_count !== a.retrieved_count) {
          return b.retrieved_count - a.retrieved_count;
        }
        return a.source_name.localeCompare(b.source_name);
      });
  }, [sourceUsage, infoPanel]);
  const citationStrengthLegend = useMemo(() => {
    const panel = infoPanel && typeof infoPanel === "object" ? infoPanel : {};
    const value = (panel as { citation_strength_legend?: unknown }).citation_strength_legend;
    const text = String(value || "").trim();
    if (text) {
      return text;
    }
    return "Citation numbers are strength-ordered: lower number means stronger supporting evidence.";
  }, [infoPanel]);
  const dominanceWarning = useMemo(() => {
    const panel = infoPanel && typeof infoPanel === "object" ? infoPanel : {};
    const warning = String((panel as { source_dominance_warning?: unknown }).source_dominance_warning || "").trim();
    if (warning) {
      return warning;
    }
    const maxShare = normalizedSourceUsage.reduce(
      (max, row) => (row.citation_share > max ? row.citation_share : max),
      0,
    );
    return maxShare > 0.6
      ? "This answer depends heavily on one source; consider reviewing other documents for broader context."
      : "";
  }, [infoPanel, normalizedSourceUsage]);
  const maxRetrievedCount = useMemo(
    () =>
      normalizedSourceUsage.reduce(
        (max, row) => (row.retrieved_count > max ? row.retrieved_count : max),
        0,
      ),
    [normalizedSourceUsage],
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
                  key={`${citationFocus?.fileId || "file"}:${citationFocus?.page || "1"}:${String(citationFocus?.extract || "").slice(0, 64)}:${JSON.stringify(citationFocus?.highlightBoxes || []).slice(0, 120)}`}
                  fileUrl={citationRawUrl}
                  page={citationFocus.page}
                  highlightText={citationFocus.extract}
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
                        max strength {row.max_strength_score.toFixed(3)} · avg {row.avg_strength_score.toFixed(3)}
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
      </div>
    </div>
  );
}
