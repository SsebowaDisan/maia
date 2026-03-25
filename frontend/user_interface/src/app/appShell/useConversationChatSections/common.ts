import { normalizeMindmapMapType, type AgentMode, type ConversationMindmapSettings } from "../conversationChat/constants";
import type { ChatTurn } from "../../types";
import type { SidebarProject } from "../types";
import { DEFAULT_PROJECT_ID } from "../constants";
import type { Dispatch, SetStateAction } from "react";

import { readStoredJson, readStoredText } from "../storage";

type UseConversationChatParams = {
  projects: SidebarProject[];
  selectedProjectId: string;
  setSelectedProjectId: (projectId: string) => void;
  conversationProjects: Record<string, string>;
  setConversationProjects: Dispatch<SetStateAction<Record<string, string>>>;
  conversationModes: Record<string, AgentMode>;
  setConversationModes: Dispatch<SetStateAction<Record<string, AgentMode>>>;
  defaultIndexId: number | null;
};

type CachedConversationSnapshot = {
  turns: ChatTurn[];
  selectedTurnIndex: number | null;
  infoText: string;
  composerMode: AgentMode;
};

function storageScopeForUser(rawUserId: string | null): string {
  const normalized = String(rawUserId || "default").trim().replace(/[^a-zA-Z0-9._-]/g, "_");
  return normalized || "default";
}

function readStoredMindmapSettings(
  key: string,
  fallbackKey: string,
): Record<string, ConversationMindmapSettings> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(key) || window.localStorage.getItem(fallbackKey);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, ConversationMindmapSettings>;
    if (!parsed || typeof parsed !== "object") {
      return {};
    }
    const normalized: Record<string, ConversationMindmapSettings> = {};
    for (const [conversationId, value] of Object.entries(parsed)) {
      if (!value || typeof value !== "object") {
        continue;
      }
      const candidate = value as Partial<ConversationMindmapSettings>;
      normalized[conversationId] = {
        enabled: Boolean(candidate.enabled),
        maxDepth: Math.max(2, Math.min(8, Number(candidate.maxDepth || 4))),
        includeReasoningMap: Boolean(candidate.includeReasoningMap),
        mapType: normalizeMindmapMapType(candidate.mapType),
      };
    }
    return normalized;
  } catch {
    return {};
  }
}

function deriveInitialSelectedTurnIndex(snapshot: CachedConversationSnapshot | null): number | null {
  if (!snapshot?.turns?.length) {
    return null;
  }
  const candidate = Number(snapshot.selectedTurnIndex);
  if (Number.isFinite(candidate) && candidate >= 0 && candidate < snapshot.turns.length) {
    return candidate;
  }
  return snapshot.turns.length - 1;
}

function stripTurnActivityForCache(turns: ChatTurn[]): ChatTurn[] {
  return turns.map((turn) =>
    turn.activityEvents && turn.activityEvents.length > 0
      ? { ...turn, activityEvents: [] }
      : turn,
  );
}

function getActiveProjectId(
  preferredProjectId: string | undefined,
  selectedProjectId: string,
  projects: SidebarProject[],
): string {
  const requestedProjectId = String(preferredProjectId || "").trim();
  if (projects.some((project) => project.id === requestedProjectId)) {
    return requestedProjectId;
  }
  if (projects.some((project) => project.id === selectedProjectId)) {
    return selectedProjectId;
  }
  return projects[0]?.id || DEFAULT_PROJECT_ID;
}

function getCachedConversationSnapshot(
  storageKey: string,
  conversationId: string,
): CachedConversationSnapshot | null {
  const cachedSnapshots = readStoredJson<Record<string, CachedConversationSnapshot>>(storageKey, {});
  return cachedSnapshots[conversationId] || null;
}

function getInitialConversationCache(storageScope: string) {
  const lastConversationStorageKey = `maia.last-conversation-id:${storageScope}`;
  const conversationsCacheStorageKey = `maia.conversations-cache:${storageScope}`;
  const conversationDetailCacheStorageKey = `maia.conversation-detail-cache:${storageScope}`;
  const cachedConversationId = readStoredText(lastConversationStorageKey, "").trim() || null;
  const cachedConversationSnapshots = readStoredJson<Record<string, CachedConversationSnapshot>>(
    conversationDetailCacheStorageKey,
    {},
  );
  return {
    cachedConversationId,
    conversationsCacheStorageKey,
    conversationDetailCacheStorageKey,
    initialCachedSnapshot: cachedConversationId ? cachedConversationSnapshots[cachedConversationId] || null : null,
    lastConversationStorageKey,
  };
}

export {
  deriveInitialSelectedTurnIndex,
  getActiveProjectId,
  getCachedConversationSnapshot,
  getInitialConversationCache,
  readStoredJson,
  readStoredMindmapSettings,
  readStoredText,
  storageScopeForUser,
  stripTurnActivityForCache,
};
export type { CachedConversationSnapshot, UseConversationChatParams };
