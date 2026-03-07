import { useEffect, useMemo, useState } from "react";

type EvidenceMode = "exact" | "context";
type VerificationTab = "sources" | "review" | "evidence" | "trail" | "compare";

type VerificationMemory = {
  selectedSourceId: string;
  selectedEvidenceId: string;
  evidenceMode: EvidenceMode;
  verificationTab: VerificationTab;
  reviewZoom: number;
};

const STORAGE_KEY = "maia.info-panel.verification-memory.v1";

function normalizeConversationId(value: unknown): string {
  return String(value || "").trim() || "global";
}

function sanitizeMemory(raw: unknown): VerificationMemory {
  const value = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const evidenceMode = String(value.evidenceMode || "").trim().toLowerCase() === "context" ? "context" : "exact";
  const verificationTabRaw = String(value.verificationTab || "").trim().toLowerCase();
  const verificationTab: VerificationTab =
    verificationTabRaw === "sources" ||
    verificationTabRaw === "review" ||
    verificationTabRaw === "evidence" ||
    verificationTabRaw === "trail" ||
    verificationTabRaw === "compare"
      ? verificationTabRaw
      : "review";
  const reviewZoomRaw = Number(value.reviewZoom || 1);
  const reviewZoom = Number.isFinite(reviewZoomRaw) ? Math.max(0.75, Math.min(2.25, reviewZoomRaw)) : 1;
  return {
    selectedSourceId: String(value.selectedSourceId || "").trim().toLowerCase(),
    selectedEvidenceId: String(value.selectedEvidenceId || "").trim().toLowerCase(),
    evidenceMode,
    verificationTab,
    reviewZoom,
  };
}

function readAllMemory(): Record<string, VerificationMemory> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}") as Record<string, unknown>;
    const next: Record<string, VerificationMemory> = {};
    for (const [conversationId, raw] of Object.entries(parsed)) {
      next[conversationId] = sanitizeMemory(raw);
    }
    return next;
  } catch {
    return {};
  }
}

function writeMemory(conversationId: string, memory: VerificationMemory): void {
  if (typeof window === "undefined") {
    return;
  }
  const all = readAllMemory();
  all[conversationId] = memory;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
}

function useVerificationMemory(conversationId?: string | null) {
  const conversationKey = normalizeConversationId(conversationId);
  const [memory, setMemory] = useState<VerificationMemory>(() => sanitizeMemory({}));

  useEffect(() => {
    const next = readAllMemory()[conversationKey];
    setMemory(next ? sanitizeMemory(next) : sanitizeMemory({}));
  }, [conversationKey]);

  useEffect(() => {
    writeMemory(conversationKey, memory);
  }, [conversationKey, memory]);

  return useMemo(
    () => ({
      memory,
      updateMemory: (patch: Partial<VerificationMemory>) => {
        setMemory((previous) => sanitizeMemory({ ...previous, ...patch }));
      },
    }),
    [memory],
  );
}

export type { EvidenceMode, VerificationTab, VerificationMemory };
export { useVerificationMemory };
