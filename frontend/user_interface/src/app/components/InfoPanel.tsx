import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Globe, FileText, Image as ImageIcon, Database } from "lucide-react";

import type { AgentActivityEvent, AgentSourceRecord, ChatAttachment, CitationFocus, SourceUsageRecord } from "../types";
import { parseEvidence } from "../utils/infoInsights";
import type { EvidenceCard } from "../utils/infoInsights";
import { buildMindmapShareLink } from "../utils/mindmapDeepLink";
import { MindmapArtifactDialog } from "./MindmapArtifactDialog";
import { TeamConversationTab } from "./agentActivityPanel/TeamConversationTab";
import { getMindmapPayload } from "./infoPanelDerived";
import { getTraceSummary } from "./infoPanelDerived";
import { CitationPreviewPanel } from "./infoPanel/CitationPreviewPanel";
import { EvidenceCardsList } from "./infoPanel/EvidenceCardsList";
import { resolveMindmapFocus } from "./infoPanel/mindmapFocus";
import { parseWebReviewSourceMap, resolveWebReviewSource } from "./infoPanel/review/webReviewContent";
import { useResizableViewers } from "./infoPanel/useResizableViewers";
import { useVerificationMemory } from "./infoPanel/useVerificationMemory";
import { resolveCitationOpenUrl, sourceIdForCitation, toCitationFromEvidence } from "./infoPanel/verificationHelpers";
import {
  buildVerificationSources,
  inferPreferredSourceId,
  type VerificationSourceItem,
} from "./infoPanel/verificationModels";
import {
  normalizeEvidenceId,
} from "./infoPanel/urlHelpers";
import { buildMindmapArtifactSummary } from "./mindmapViewer/presentation";
import { toMindmapPayload } from "./mindmapViewer/viewerHelpers";
import { resolvePreferredRunId } from "../utils/runIdSelection";

interface InfoPanelProps {
  citationFocus?: CitationFocus | null;
  selectedConversationId?: string | null;
  userPrompt?: string;
  attachments?: ChatAttachment[];
  assistantHtml?: string;
  infoHtml?: string;
  infoPanel?: Record<string, unknown>;
  mindmap?: Record<string, unknown>;
  activityEvents?: AgentActivityEvent[];
  sourcesUsed?: AgentSourceRecord[];
  webSummary?: Record<string, unknown>;
  sourceUsage?: SourceUsageRecord[];
  activityRunId?: string | null;
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

type RagScopeSourceRow = {
  label: string;
  source_type: string;
  credibility_tier?: string | null;
  url?: string | null;
  file_id?: string | null;
};

type RagScopeSummary = {
  fileCount: number;
  coveredFileCount: number;
  fileIds: string[];
  searchedSourceCount: number;
  searchedSources: RagScopeSourceRow[];
};

type EvidenceConflictSummary = {
  status: string;
  message: string;
  contradictedClaims: number;
  mixedClaims: number;
};

function parseRagScopeSummary(infoPanel: Record<string, unknown>): RagScopeSummary | null {
  const raw = (infoPanel as { selected_scope?: unknown }).selected_scope;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const searchedSources = Array.isArray(record.searched_sources)
    ? record.searched_sources
        .map((row) => {
          if (!row || typeof row !== "object" || Array.isArray(row)) {
            return null;
          }
          const item = row as Record<string, unknown>;
          const label = String(item.label || "").trim();
          if (!label) {
            return null;
          }
          return {
            label,
            source_type: String(item.source_type || "file").trim().toLowerCase() || "file",
            credibility_tier: typeof item.credibility_tier === "string" ? item.credibility_tier : null,
            url: typeof item.url === "string" ? item.url : null,
            file_id: typeof item.file_id === "string" ? item.file_id : null,
          } satisfies RagScopeSourceRow;
        })
        .filter((row): row is RagScopeSourceRow => Boolean(row))
    : [];
  const fileIds = Array.isArray(record.file_ids)
    ? record.file_ids
        .map((value) => String(value || "").trim())
        .filter(Boolean)
    : [];
  return {
    fileCount: Math.max(0, Number(record.file_count || 0)),
    coveredFileCount: Math.max(0, Number(record.covered_file_count || 0)),
    fileIds: fileIds.slice(0, 40),
    searchedSourceCount: Math.max(
      searchedSources.length,
      Math.max(0, Number(record.searched_source_count || 0)),
    ),
    searchedSources,
  };
}

function parseEvidenceConflictSummary(infoPanel: Record<string, unknown>): EvidenceConflictSummary | null {
  const raw = (infoPanel as { evidence_conflict_summary?: unknown }).evidence_conflict_summary;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const message = String(record.message || "").trim();
  if (!message) {
    return null;
  }
  return {
    status: String(record.status || "mixed").trim().toLowerCase() || "mixed",
    message,
    contradictedClaims: Math.max(0, Number(record.contradicted_claims || 0)),
    mixedClaims: Math.max(0, Number(record.mixed_claims || 0)),
  };
}

function sourceIcon(sourceType: string) {
  if (sourceType === "web") {
    return Globe;
  }
  if (sourceType === "image") {
    return ImageIcon;
  }
  if (sourceType === "pdf") {
    return FileText;
  }
  return Database;
}

function credibilityBadgeClass(tier: string | null | undefined) {
  switch ((tier || "").toLowerCase()) {
    case "high":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "platform":
      return "border-blue-200 bg-blue-50 text-blue-700";
    case "low":
      return "border-amber-200 bg-amber-50 text-amber-700";
    default:
      return "border-black/[0.08] bg-white text-[#5b6474]";
  }
}

function credibilityLabel(tier: string | null | undefined) {
  switch ((tier || "").toLowerCase()) {
    case "high":
      return "High credibility";
    case "platform":
      return "Platform source";
    case "low":
      return "Low credibility";
    default:
      return "Medium credibility";
  }
}

function findSourceById(sources: VerificationSourceItem[], sourceId: string): VerificationSourceItem | null {
  const normalized = String(sourceId || "").trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  return sources.find((source) => source.id === normalized) || null;
}

export function InfoPanel({
  citationFocus = null,
  selectedConversationId = null,
  userPrompt = "",
  attachments = [],
  infoHtml = "",
  infoPanel = {},
  mindmap = {},
  activityEvents = [],
  activityRunId = null,
  sourcesUsed = [],
  sourceUsage = [],
  indexId = null,
  onClearCitationFocus,
  onSelectCitationFocus,
  onAskMindmapNode,
  width = 340,
}: InfoPanelProps) {
  const { viewerHeights, renderViewerResizeHandle } = useResizableViewers();
  const { memory, updateMemory } = useVerificationMemory(selectedConversationId);
  const contentViewportRef = useRef<HTMLDivElement | null>(null);
  const citationPanelRef = useRef<HTMLDivElement | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [pdfZoom, setPdfZoom] = useState(1);
  const [isMindmapDialogOpen, setIsMindmapDialogOpen] = useState(false);
  const [citationAutoHeight, setCitationAutoHeight] = useState(0);

  const evidenceCards = useMemo(
    () =>
      parseEvidence(String(infoHtml || ""), {
        infoPanel: infoPanel as Record<string, unknown>,
        userPrompt: String(userPrompt || ""),
        promptAttachments: Array.isArray(attachments) ? attachments : [],
      }),
    [attachments, infoHtml, infoPanel, userPrompt],
  );

  const { sources, evidenceBySource } = useMemo(
    () =>
      buildVerificationSources({
        evidenceCards,
        sourcesUsed,
        sourceUsage,
      }),
    [evidenceCards, sourceUsage, sourcesUsed],
  );

  const preferredSourceId = useMemo(
    () =>
      inferPreferredSourceId({
        citationFocus,
        sources,
        fallback: memory.selectedSourceId,
      }),
    [citationFocus, memory.selectedSourceId, sources],
  );

  useEffect(() => {
    if (!selectedSourceId && preferredSourceId) {
      setSelectedSourceId(preferredSourceId);
      return;
    }
    if (selectedSourceId && !findSourceById(sources, selectedSourceId) && preferredSourceId) {
      setSelectedSourceId(preferredSourceId);
    }
  }, [preferredSourceId, selectedSourceId, sources]);

  useEffect(() => {
    if (memory.reviewZoom > 0) {
      setPdfZoom(memory.reviewZoom);
    }
  }, [memory.reviewZoom]);

  const selectedSource = useMemo(
    () => findSourceById(sources, selectedSourceId) || findSourceById(sources, preferredSourceId),
    [preferredSourceId, selectedSourceId, sources],
  );

  const sourceEvidence = useMemo(() => {
    if (!selectedSource?.id) {
      return evidenceCards;
    }
    return evidenceBySource[selectedSource.id] || [];
  }, [evidenceBySource, evidenceCards, selectedSource?.id]);

  const activeEvidenceId = normalizeEvidenceId(citationFocus?.evidenceId || memory.selectedEvidenceId || "");
  const activeEvidenceIndex = useMemo(() => {
    if (!activeEvidenceId) {
      return evidenceCards.length ? 0 : -1;
    }
    return evidenceCards.findIndex((card) => normalizeEvidenceId(card.id) === activeEvidenceId);
  }, [activeEvidenceId, evidenceCards]);

  const activeEvidenceCard = activeEvidenceIndex >= 0 ? evidenceCards[activeEvidenceIndex] : evidenceCards[0];
  const activeCitation = citationFocus || (activeEvidenceCard ? toCitationFromEvidence(activeEvidenceCard, activeEvidenceIndex >= 0 ? activeEvidenceIndex : 0) : null);
  const activeCitationSourceKey = useMemo(() => sourceIdForCitation(activeCitation), [activeCitation]);

  const preferredCitationPage = useMemo(() => {
    const explicitCitationPage = String(activeCitation?.page || "").trim();
    if (explicitCitationPage) {
      return undefined;
    }
    if (!activeCitationSourceKey) {
      return undefined;
    }
    const remembered = Number(memory.reviewPageBySource[activeCitationSourceKey] || 0);
    if (!Number.isFinite(remembered) || remembered <= 0) {
      return undefined;
    }
    return String(Math.floor(remembered));
  }, [activeCitationSourceKey, memory.reviewPageBySource]);

  const citationOpenState = useMemo(
    () =>
      resolveCitationOpenUrl({
        citation: activeCitation,
        evidenceCards,
        indexId,
      }),
    [activeCitation, evidenceCards, indexId],
  );

  const webReviewSourceMap = useMemo(
    () => parseWebReviewSourceMap(infoPanel as Record<string, unknown>),
    [infoPanel],
  );
  const ragScopeSummary = useMemo(
    () => parseRagScopeSummary(infoPanel as Record<string, unknown>),
    [infoPanel],
  );
  const evidenceConflictSummary = useMemo(
    () => parseEvidenceConflictSummary(infoPanel as Record<string, unknown>),
    [infoPanel],
  );
  const activeWebReviewSource = useMemo(
    () =>
      resolveWebReviewSource({
        sourceMap: webReviewSourceMap,
        sourceId: selectedSource?.id || activeCitationSourceKey || "",
        sourceUrl: citationOpenState.citationWebsiteUrl || selectedSource?.url || activeCitation?.sourceUrl || "",
        sourceTitle: activeCitation?.sourceName || selectedSource?.title || "Website source",
        evidenceCards: sourceEvidence,
      }),
    [
      activeCitation?.sourceName,
      activeCitation?.sourceUrl,
      activeCitationSourceKey,
      citationOpenState.citationWebsiteUrl,
      selectedSource?.id,
      selectedSource?.title,
      selectedSource?.url,
      sourceEvidence,
      webReviewSourceMap,
    ],
  );

  const mindmapPayload = useMemo(() => getMindmapPayload(infoPanel, mindmap), [infoPanel, mindmap]);
  const traceSummary = useMemo(() => getTraceSummary(infoPanel), [infoPanel]);
  const hasMindmapPayload = Array.isArray((mindmapPayload as { nodes?: unknown[] }).nodes)
    ? ((mindmapPayload as { nodes?: unknown[] }).nodes as unknown[]).length > 0
    : false;
  const workspaceGraphPayload = mindmapPayload;
  const typedMindmapPayload = useMemo(
    () => toMindmapPayload(workspaceGraphPayload as Record<string, unknown>),
    [workspaceGraphPayload],
  );
  const conversationRunId = useMemo(
    () => resolvePreferredRunId(activityRunId, activityEvents),
    [activityEvents, activityRunId],
  );
  const showTeamConversation = Boolean(conversationRunId) || activityEvents.length > 0;
  const showEvidenceSurfaces = Boolean(citationFocus);

  useEffect(() => {
    if (!showEvidenceSurfaces || !activeEvidenceId) {
      return;
    }
    const viewportNode = contentViewportRef.current;
    if (!viewportNode) {
      return;
    }
    const frameId = window.requestAnimationFrame(() => {
      const targetNode = viewportNode.querySelector<HTMLElement>(
        `[data-evidence-card-id='${activeEvidenceId}']`,
      );
      if (!targetNode) {
        return;
      }
      targetNode.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [activeEvidenceId, showEvidenceSurfaces]);
  const mindmapSummary = useMemo(
    () => buildMindmapArtifactSummary(typedMindmapPayload),
    [typedMindmapPayload],
  );
  const effectiveCitationViewerHeight = useMemo(() => {
    if (citationAutoHeight > 0) {
      return citationAutoHeight;
    }
    return viewerHeights.citation;
  }, [citationAutoHeight, viewerHeights.citation]);

  const recomputeCitationAutoHeight = useCallback(() => {
    const viewportNode = contentViewportRef.current;
    const citationNode = citationPanelRef.current;
    if (!viewportNode || !citationNode) {
      return;
    }
    const viewportRect = viewportNode.getBoundingClientRect();
    const citationRect = citationNode.getBoundingClientRect();

    // pb-10 (40px) keeps breathing room above the bottom gradient.
    const viewportBottomPadding = 40;
    // CitationPreviewPanel has chrome outside the website/PDF viewer area.
    const previewChromeOffset = 96;
    const availableViewerHeight =
      viewportRect.bottom - citationRect.top - viewportBottomPadding - previewChromeOffset;
    const nextHeight = Math.max(320, Math.min(1000, Math.floor(availableViewerHeight)));
    setCitationAutoHeight((current) => (Math.abs(current - nextHeight) > 1 ? nextHeight : current));
  }, []);

  useEffect(() => {
    if (!activeCitation) {
      setCitationAutoHeight(0);
      return;
    }

    let frameId = 0;
    const scheduleRecompute = () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
      frameId = window.requestAnimationFrame(() => {
        recomputeCitationAutoHeight();
      });
    };

    scheduleRecompute();

    const viewportNode = contentViewportRef.current;
    if (viewportNode) {
      viewportNode.addEventListener("scroll", scheduleRecompute, { passive: true });
    }
    window.addEventListener("resize", scheduleRecompute);

    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(scheduleRecompute);
      if (viewportNode) {
        observer.observe(viewportNode);
      }
      if (citationPanelRef.current) {
        observer.observe(citationPanelRef.current);
      }
    }

    return () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
      if (viewportNode) {
        viewportNode.removeEventListener("scroll", scheduleRecompute);
      }
      window.removeEventListener("resize", scheduleRecompute);
      observer?.disconnect();
    };
  }, [activeCitation, recomputeCitationAutoHeight]);

  const selectEvidence = (card: EvidenceCard, index: number) => {
    const nextCitation = toCitationFromEvidence(card, index);
    const sourceId = sourceIdForCitation(nextCitation);
    if (sourceId) {
      setSelectedSourceId(sourceId);
      updateMemory({ selectedSourceId: sourceId });
    }
    updateMemory({
      selectedEvidenceId: normalizeEvidenceId(card.id) || `evidence-${index + 1}`,
    });
    onSelectCitationFocus?.(nextCitation);
  };

  const selectSource = (sourceId: string) => {
    setSelectedSourceId(sourceId);
    const firstEvidence = (evidenceBySource[sourceId] || [])[0];
    updateMemory({
      selectedSourceId: sourceId,
      selectedEvidenceId: normalizeEvidenceId(firstEvidence?.id || ""),
    });
  };

  const jumpToNeighborEvidence = (offset: number) => {
    if (!evidenceCards.length) {
      return;
    }
    const current = activeEvidenceIndex >= 0 ? activeEvidenceIndex : 0;
    const next = Math.max(0, Math.min(evidenceCards.length - 1, current + offset));
    const target = evidenceCards[next];
    if (!target) {
      return;
    }
    selectEvidence(target, next);
  };

  const handleMindmapFocus = (payload: {
    nodeId: string;
    title: string;
    text: string;
    pageRef?: string;
    sourceId?: string;
    sourceName?: string;
  }) => {
    const resolved = resolveMindmapFocus({
      node: payload,
      sources,
      evidenceBySource,
    });
    if (resolved.sourceId) {
      selectSource(resolved.sourceId);
    }
    if (resolved.evidenceCard) {
      selectEvidence(resolved.evidenceCard, resolved.evidenceIndex);
    }
  };

  const handleSaveMindmap = (payload: Record<string, unknown>) => {
    const storageKey = "maia.saved-mindmaps";
    try {
      const existing = JSON.parse(window.localStorage.getItem(storageKey) || "{}") as Record<string, unknown>;
      const conversationKey = String(selectedConversationId || "global");
      const history = Array.isArray(existing[conversationKey]) ? (existing[conversationKey] as unknown[]) : [];
      existing[conversationKey] = [...history.slice(-9), { saved_at: new Date().toISOString(), map: payload }];
      window.localStorage.setItem(storageKey, JSON.stringify(existing));
      toast.success("Mind-map saved");
    } catch {
      toast.error("Unable to save mind-map");
    }
  };

  const handleShareMindmap = (payload: Record<string, unknown>) =>
    buildMindmapShareLink({
      map: payload,
      conversationId: selectedConversationId,
    });

  return (
    <div
      className="flex min-h-0 flex-col overflow-hidden rounded-[28px] border border-black/[0.06] bg-[#f6f6f7] shadow-[0_14px_40px_rgba(15,23,42,0.06)]"
      style={{ width: `${Math.round(width)}px` }}
    >
      <div className="border-b border-black/[0.06] px-5 py-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
            {showEvidenceSurfaces ? "Evidence" : showTeamConversation ? "Live Team Thread" : "Dialogue"}
          </p>
          <h3 className="mt-1 text-[20px] font-semibold tracking-[-0.02em] text-[#17171b]">
            {showEvidenceSurfaces ? "Sources" : showTeamConversation ? "Team Conversation" : "Conversation"}
          </h3>
        </div>
      </div>

      <div className="relative min-h-0 flex-1">
        <div
          ref={contentViewportRef}
          className={`h-full overflow-y-auto overscroll-none px-5 ${
            showEvidenceSurfaces ? "space-y-4 pb-10 pt-5" : "pb-4 pt-4"
          }`}
        >
          {showTeamConversation ? (
            <div className={showEvidenceSurfaces ? "" : "flex h-full min-h-0 flex-col"}>
              <TeamConversationTab runId={conversationRunId} events={activityEvents} />
            </div>
          ) : null}

          {showEvidenceSurfaces ? (
            <section className="space-y-3 rounded-2xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f6f7fa] p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
                  {mindmapSummary?.presentation.eyebrow || "Research artifact"}
                </p>
                <h4 className="mt-1 text-[16px] font-semibold tracking-[-0.02em] text-[#17171b]">
                  {mindmapSummary?.presentation.label || "Knowledge map"}
                </h4>
                <p className="mt-1 text-[12px] leading-5 text-[#6b6b70]">
                  {mindmapSummary?.presentation.summary ||
                    "Open a dedicated artifact surface to inspect the answer map without crowding the Sources panel."}
                </p>
              </div>
              {hasMindmapPayload ? (
                <button
                  type="button"
                  onClick={() => setIsMindmapDialogOpen(true)}
                  className="shrink-0 rounded-full bg-[#17171b] px-3 py-2 text-[11px] font-semibold text-white transition-colors hover:bg-[#2a2a30]"
                >
                  Open map
                </button>
              ) : null}
            </div>

            {hasMindmapPayload ? (
              <div className="rounded-2xl border border-black/[0.06] bg-white/80 p-3">
                <div className="flex flex-wrap gap-2">
                  {mindmapSummary?.availableMapTypes.map((mapType) => (
                    <span
                      key={mapType}
                      className="rounded-full border border-black/[0.06] bg-white px-2.5 py-1 text-[11px] font-medium text-[#4a4a50]"
                    >
                      {mapType === "context_mindmap"
                        ? "Sources"
                        : mapType === "work_graph"
                          ? "Execution"
                          : mapType === "evidence"
                            ? "Evidence"
                            : "Concept"}
                    </span>
                  ))}
                  {mindmapSummary?.nodeCount ? (
                    <span className="rounded-full border border-black/[0.06] bg-white px-2.5 py-1 text-[11px] font-medium text-[#4a4a50]">
                      {mindmapSummary.nodeCount} nodes
                    </span>
                  ) : null}
                  {mindmapSummary?.sourceCount ? (
                    <span className="rounded-full border border-black/[0.06] bg-white px-2.5 py-1 text-[11px] font-medium text-[#4a4a50]">
                      {mindmapSummary.sourceCount} sources
                    </span>
                  ) : null}
                  {mindmapSummary?.actionCount ? (
                    <span className="rounded-full border border-black/[0.06] bg-white px-2.5 py-1 text-[11px] font-medium text-[#4a4a50]">
                      {mindmapSummary.actionCount} actions
                    </span>
                  ) : null}
                </div>
                <p className="mt-3 text-[12px] leading-5 text-[#6b6b70]">
                  The full map now opens in its own artifact surface so the right panel can stay focused on source preview.
                </p>
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-black/[0.08] bg-white/65 p-4 text-[12px] leading-5 text-[#6e6e73]">
                No mindmap artifact was produced for this answer yet. Research-heavy or comparative questions will populate this surface when the backend emits a structured map.
              </div>
            )}
            </section>
          ) : !showTeamConversation ? (
            <section className="rounded-2xl border border-[#e4e7ec] bg-white px-4 py-3 text-[12px] text-[#667085]">
              Click a citation in the assistant answer to open source evidence in this panel.
            </section>
          ) : null}

          {!showEvidenceSurfaces && ragScopeSummary ? (
            <section className="space-y-3 rounded-2xl border border-[#d2d2d7] bg-white px-4 py-4 shadow-sm">
              {evidenceConflictSummary ? (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-700">
                        Evidence Conflict
                      </p>
                      <p className="mt-1 text-[12px] font-medium text-[#17171b]">
                        {evidenceConflictSummary.message}
                      </p>
                    </div>
                    <div className="text-right text-[11px] text-amber-700">
                      {evidenceConflictSummary.contradictedClaims > 0 ? (
                        <div>{evidenceConflictSummary.contradictedClaims} contradicted claim{evidenceConflictSummary.contradictedClaims === 1 ? "" : "s"}</div>
                      ) : null}
                      {evidenceConflictSummary.mixedClaims > 0 ? (
                        <div>{evidenceConflictSummary.mixedClaims} mixed claim{evidenceConflictSummary.mixedClaims === 1 ? "" : "s"}</div>
                      ) : null}
                    </div>
                  </div>
                </div>
              ) : null}
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
                    RAG Scope
                  </p>
                  <h4 className="mt-1 text-[16px] font-semibold tracking-[-0.02em] text-[#17171b]">
                    Maia sources searched
                  </h4>
                </div>
                <div className="text-right text-[11px] text-[#6b6b70]">
                  {ragScopeSummary.fileCount > 0 ? (
                    <div>{ragScopeSummary.coveredFileCount}/{ragScopeSummary.fileCount} selected files covered</div>
                  ) : (
                    <div>{ragScopeSummary.searchedSourceCount} indexed source{ragScopeSummary.searchedSourceCount === 1 ? "" : "s"}</div>
                  )}
                </div>
              </div>

              {ragScopeSummary.fileIds.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {ragScopeSummary.fileIds.slice(0, 8).map((fileId) => (
                    <span
                      key={fileId}
                      className="rounded-full border border-black/[0.06] bg-[#f8f8fb] px-2.5 py-1 text-[11px] font-medium text-[#4b5563]"
                    >
                      {fileId}
                    </span>
                  ))}
                </div>
              ) : null}

              {ragScopeSummary.searchedSources.length > 0 ? (
                <div className="space-y-2">
                  {ragScopeSummary.searchedSources.map((source) => {
                    const Icon = sourceIcon(source.source_type);
                    return (
                      <div
                        key={`${source.source_type}:${source.file_id || source.url || source.label}`}
                        className="flex items-start gap-3 rounded-xl border border-black/[0.06] bg-[#fbfbfc] px-3 py-2"
                      >
                        <span className="mt-0.5 rounded-full border border-black/[0.06] bg-white p-1.5 text-[#5b6474]">
                          <Icon className="h-3.5 w-3.5" />
                        </span>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <div className="truncate text-[12px] font-medium text-[#17171b]">{source.label}</div>
                            <span
                              className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium ${credibilityBadgeClass(source.credibility_tier)}`}
                            >
                              {credibilityLabel(source.credibility_tier)}
                            </span>
                          </div>
                          <div className="mt-0.5 truncate text-[11px] text-[#6b6b70]">
                            {source.url || source.file_id || source.source_type}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-black/[0.08] bg-[#fbfbfc] px-3 py-3 text-[12px] text-[#6b6b70]">
                  No indexed Maia sources matched this turn yet.
                </div>
              )}
            </section>
          ) : null}

          {showEvidenceSurfaces ? (
            <section className="space-y-3 rounded-2xl border border-[#d2d2d7] bg-white px-4 py-4 shadow-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
                    Evidence
                  </p>
                  <h4 className="mt-1 text-[16px] font-semibold tracking-[-0.02em] text-[#17171b]">
                    Citation evidence
                  </h4>
                </div>
                <div className="text-right text-[11px] text-[#6b6b70]">
                  {activeEvidenceId ? <div>{sourceEvidence.length} evidence card{sourceEvidence.length === 1 ? "" : "s"}</div> : null}
                  {selectedSource?.title || activeCitation?.sourceName ? (
                    <div className="truncate">{selectedSource?.title || activeCitation?.sourceName}</div>
                  ) : null}
                </div>
              </div>

              <EvidenceCardsList
                cards={sourceEvidence}
                selectedEvidenceId={activeEvidenceId}
                onSelectCard={selectEvidence}
              />
            </section>
          ) : null}

          {/* Citation page preview */}
          {showEvidenceSurfaces && activeCitation ? (
            <div ref={citationPanelRef}>
              <CitationPreviewPanel
                citationFocus={activeCitation}
                citationOpenUrl={citationOpenState.citationOpenUrl}
                citationRawUrl={citationOpenState.citationRawUrl}
                citationUsesWebsite={citationOpenState.citationUsesWebsite}
                citationWebsiteUrl={citationOpenState.citationWebsiteUrl}
                citationIsPdf={citationOpenState.citationIsPdf}
                citationIsImage={citationOpenState.citationIsImage}
                citationViewerHeight={effectiveCitationViewerHeight}
                reviewQuery={userPrompt || activeCitation?.claimText || ""}
                preferredPage={preferredCitationPage}
                webReviewSource={activeWebReviewSource}
                hasPreviousEvidence={activeEvidenceIndex > 0}
                hasNextEvidence={activeEvidenceIndex >= 0 && activeEvidenceIndex < evidenceCards.length - 1}
                onPreviousEvidence={() => jumpToNeighborEvidence(-1)}
                onNextEvidence={() => jumpToNeighborEvidence(1)}
                pdfZoom={pdfZoom}
                onPdfZoomChange={(next) => {
                  setPdfZoom(next);
                  updateMemory({ reviewZoom: next });
                }}
                onPdfPageChange={(nextPage) => {
                  if (!activeCitationSourceKey || nextPage <= 0) {
                    return;
                  }
                  const previous = Number(memory.reviewPageBySource[activeCitationSourceKey] || 0);
                  if (previous === nextPage) {
                    return;
                  }
                  updateMemory({
                    reviewPageBySource: {
                      ...memory.reviewPageBySource,
                      [activeCitationSourceKey]: nextPage,
                    },
                  });
                }}
                onClear={onClearCitationFocus}
                renderResizeHandle={() => renderViewerResizeHandle("citation", "citation")}
              />
            </div>
          ) : showEvidenceSurfaces && sources.length > 0 ? (
            <div className="rounded-xl border border-black/[0.06] bg-white p-4 text-center text-[12px] text-[#6e6e73]">
              Click any citation in the answer to preview the source page here.
            </div>
          ) : null}
        </div>
        {showEvidenceSurfaces ? (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-[#f6f6f7] via-[#f6f6f7]/92 to-transparent" />
        ) : null}
      </div>

      {traceSummary ? (
        <div className="shrink-0 border-t border-black/[0.06] bg-[#fbfbfc] px-4 py-3">
          <div className="rounded-2xl border border-black/[0.06] bg-white px-3 py-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
                  Turn Trace
                </p>
                <p className="mt-1 text-[12px] font-medium text-[#17171b]">
                  {traceSummary.kind || "chat"} - {traceSummary.eventCount} events
                </p>
              </div>
              <div className="text-right">
                <p className="text-[10px] uppercase tracking-[0.08em] text-[#8e8e93]">Last event</p>
                <p className="mt-1 text-[11px] font-medium text-[#374151]">
                  {traceSummary.lastEventType || "n/a"}
                </p>
              </div>
            </div>
            <div className="mt-3 rounded-xl bg-[#f8f8fb] px-3 py-2 text-[11px] text-[#6b7280]">
              Trace ID: <span className="font-mono text-[#111827]">{traceSummary.traceId}</span>
            </div>
            {traceSummary.eventTypes.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {traceSummary.eventTypes.map((eventType) => (
                  <span
                    key={eventType}
                    className="rounded-full border border-black/[0.06] bg-white px-2.5 py-1 text-[10px] font-medium text-[#4b5563]"
                  >
                    {eventType}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* Footer — matches sidebar footer and composer pill height (60px) */}
      <div className="shrink-0 border-t border-black/[0.06] bg-[#f6f6f7] px-3 py-3">
        <div className="flex h-9 items-center gap-2 rounded-xl border border-black/[0.08] bg-white px-3 text-[12px] text-[#6e6e73]">
          <span className="truncate">
            {showEvidenceSurfaces
              ? sources.length > 0
                ? `${sources.length} source${sources.length !== 1 ? "s" : ""}`
                : "No sources"
              : showTeamConversation
                ? "Live teammate thread"
                : "No conversation yet"}
          </span>
        </div>
      </div>

      <MindmapArtifactDialog
        open={isMindmapDialogOpen}
        onOpenChange={setIsMindmapDialogOpen}
        payload={workspaceGraphPayload as Record<string, unknown>}
        conversationId={selectedConversationId}
        onAskNode={onAskMindmapNode}
        onFocusNode={handleMindmapFocus}
        onSaveMap={(payload) => handleSaveMindmap(payload as unknown as Record<string, unknown>)}
        onShareMap={(payload) => handleShareMindmap(payload as unknown as Record<string, unknown>)}
      />
    </div>
  );
}
