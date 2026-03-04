import type { CitationFocus, SourceUsageRecord } from "../types";

type InfoPanelData = Record<string, unknown> | null | undefined;

export type ClaimSignalRow = {
  claim: string;
  status: string;
  ref_ids: number[];
};

export type ClaimSignalSummary = {
  claimsEvaluated: number;
  supportedClaims: number;
  contradictedClaims: number;
  mixedClaims: number;
  rows: ClaimSignalRow[];
};

export function getCitationStrengthTier(citationFocus?: CitationFocus | null): number {
  if (!citationFocus) {
    return 0;
  }
  const directTier = Number(citationFocus.strengthTier || 0);
  if (Number.isFinite(directTier) && directTier >= 1) {
    return Math.max(1, Math.min(3, Math.round(directTier)));
  }
  const score = Number(citationFocus.strengthScore || 0);
  if (!Number.isFinite(score) || score <= 0) {
    return 0;
  }
  if (score >= 0.7) return 3;
  if (score >= 0.42) return 2;
  return 1;
}

export function getCitationStrengthLabel(tier: number): string {
  if (tier <= 0) {
    return "";
  }
  if (tier >= 3) {
    return "Strong evidence";
  }
  if (tier >= 2) {
    return "Moderate evidence";
  }
  return "Supporting evidence";
}

export function getCitationMatchQualityLabel(citationFocus?: CitationFocus | null): string {
  const quality = String(citationFocus?.matchQuality || "")
    .trim()
    .toLowerCase();
  if (!quality) return "";
  if (quality === "exact") return "Exact match";
  if (quality === "fuzzy") return "Approximate match";
  return "Estimated match";
}

export function getTabLabels(infoPanel?: InfoPanelData): {
  evidence: string;
  sources: string;
  mindmap: string;
} {
  const panel = infoPanel && typeof infoPanel === "object" ? infoPanel : {};
  const labels = (panel as { tab_labels?: Record<string, unknown> }).tab_labels;
  const data = labels && typeof labels === "object" ? labels : {};
  return {
    evidence: String(data.evidence || "Evidence"),
    sources: String(data.sources || "Sources"),
    mindmap: String(data.mindmap || "Mind-map"),
  };
}

export function getMindmapPayload(
  infoPanel: InfoPanelData,
  mindmap: Record<string, unknown>,
): Record<string, unknown> {
  if (mindmap && typeof mindmap === "object" && Object.keys(mindmap).length > 0) {
    return mindmap;
  }
  const panel = infoPanel && typeof infoPanel === "object" ? infoPanel : {};
  const value = (panel as { mindmap?: unknown }).mindmap;
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

export function getNormalizedSourceUsage(
  infoPanel: InfoPanelData,
  sourceUsage: SourceUsageRecord[],
): SourceUsageRecord[] {
  const panel = infoPanel && typeof infoPanel === "object" ? infoPanel : {};
  const fromPanel = (panel as { source_usage?: unknown }).source_usage;
  const rows = sourceUsage.length ? sourceUsage : Array.isArray(fromPanel) ? fromPanel : [];
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
}

export function getCitationStrengthLegend(infoPanel?: InfoPanelData): string {
  const panel = infoPanel && typeof infoPanel === "object" ? infoPanel : {};
  const value = (panel as { citation_strength_legend?: unknown }).citation_strength_legend;
  const text = String(value || "").trim();
  if (text) {
    return text;
  }
  return "Citation numbers are normalized per answer: each source appears once and numbering starts at 1.";
}

export function getDominanceWarning(
  infoPanel: InfoPanelData,
  sourceRows: SourceUsageRecord[],
): string {
  const panel = infoPanel && typeof infoPanel === "object" ? infoPanel : {};
  const warning = String(
    (panel as { source_dominance_warning?: unknown }).source_dominance_warning || "",
  ).trim();
  if (warning) {
    return warning;
  }
  const maxShare = sourceRows.reduce(
    (max, row) => (row.citation_share > max ? row.citation_share : max),
    0,
  );
  return maxShare > 0.6
    ? "This answer depends heavily on one source; consider reviewing other documents for broader context."
    : "";
}

export function getMaxRetrievedCount(sourceRows: SourceUsageRecord[]): number {
  return sourceRows.reduce(
    (max, row) => (row.retrieved_count > max ? row.retrieved_count : max),
    0,
  );
}

export function getClaimSignalSummary(infoPanel?: InfoPanelData): ClaimSignalSummary | null {
  const panel = infoPanel && typeof infoPanel === "object" ? infoPanel : {};
  const raw = (panel as { claim_signal_summary?: unknown }).claim_signal_summary;
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const record = raw as Record<string, unknown>;
  const rows = Array.isArray(record.rows)
    ? record.rows
        .map((row) => {
          if (!row || typeof row !== "object") {
            return null;
          }
          const item = row as Record<string, unknown>;
          return {
            claim: String(item.claim || "").trim(),
            status: String(item.status || "").trim().toLowerCase(),
            ref_ids: Array.isArray(item.ref_ids)
              ? item.ref_ids
                  .map((entry) => Number(entry))
                  .filter((entry) => Number.isFinite(entry))
              : [],
          };
        })
        .filter((row): row is ClaimSignalRow => Boolean(row && row.claim))
    : [];
  return {
    claimsEvaluated: Math.max(0, Number(record.claims_evaluated || 0)),
    supportedClaims: Math.max(0, Number(record.supported_claims || 0)),
    contradictedClaims: Math.max(0, Number(record.contradicted_claims || 0)),
    mixedClaims: Math.max(0, Number(record.mixed_claims || 0)),
    rows: rows.slice(0, 6),
  };
}
