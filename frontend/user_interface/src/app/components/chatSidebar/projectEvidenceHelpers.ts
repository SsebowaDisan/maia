import {
  type AgentSourceRecord,
  type FileRecord,
  type SourceUsageRecord,
} from "../../../api/client";
import { parseEvidence } from "../../utils/infoInsights";

export type ProjectEvidenceItem = {
  key: string;
  label: string;
  type: "document" | "url";
  href?: string;
  fileIds: string[];
  usageCount: number;
  chatCount: number;
};

export type ProjectEvidenceState = {
  status: "idle" | "loading" | "ready" | "error";
  documents: ProjectEvidenceItem[];
  urls: ProjectEvidenceItem[];
  projectChatCount: number;
  errorMessage: string;
};

export const EMPTY_PROJECT_EVIDENCE: ProjectEvidenceState = {
  status: "idle",
  documents: [],
  urls: [],
  projectChatCount: 0,
  errorMessage: "",
};

type AggregateItem = {
  key: string;
  label: string;
  href?: string;
  fileIds: Set<string>;
  usageCount: number;
  conversationIds: Set<string>;
};

export const HTTP_URL_RE = /^https?:\/\/\S+/i;
export const SOURCE_ALIAS_STORAGE_KEY = "maia.project-source-aliases";
export const PROJECT_SOURCE_BINDINGS_STORAGE_KEY = "maia.project-source-bindings";

export type ProjectSourceBinding = {
  fileIds: string[];
  urls: string[];
};

export function normalizeSourceUrl(rawValue: string): string {
  const value = String(rawValue || "").trim();
  if (!value) {
    return "";
  }
  try {
    const parsed = new URL(value);
    parsed.hash = "";
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return value.replace(/\/$/, "");
  }
}

export function normalizeUrlCandidates(values: Array<unknown>): string {
  for (const candidate of values) {
    const text = String(candidate || "").trim();
    if (!text || !HTTP_URL_RE.test(text)) {
      continue;
    }
    const normalized = normalizeSourceUrl(text);
    if (normalized) {
      return normalized;
    }
  }
  return "";
}

export function normalizeUrlDraftList(rawDraft: string): string[] {
  const seen = new Set<string>();
  const urls: string[] = [];
  const rows = String(rawDraft || "")
    .split(/\r?\n/)
    .map((row) => row.trim())
    .filter(Boolean);
  for (const row of rows) {
    if (!HTTP_URL_RE.test(row)) {
      continue;
    }
    const normalized = normalizeSourceUrl(row);
    if (!normalized || seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    urls.push(normalized);
  }
  return urls;
}

export function getFileRecordUrl(file: FileRecord): string {
  const note = file.note && typeof file.note === "object" ? (file.note as Record<string, unknown>) : {};
  return normalizeUrlCandidates([
    file.name,
    note["url"],
    note["source_url"],
    note["page_url"],
    note["canonical_url"],
    note["original_url"],
  ]);
}

export function toProjectEvidenceItems(
  map: Map<string, AggregateItem>,
  type: "document" | "url",
): ProjectEvidenceItem[] {
  return [...map.values()]
    .map((item) => ({
      key: item.key,
      label: item.label,
      type,
      href: item.href,
      fileIds: [...item.fileIds],
      usageCount: item.usageCount,
      chatCount: item.conversationIds.size,
    }))
    .sort(
      (left, right) =>
        right.usageCount - left.usageCount ||
        right.chatCount - left.chatCount ||
        left.label.localeCompare(right.label),
    );
}

function addAggregateItem(
  map: Map<string, AggregateItem>,
  item: {
    key: string;
    label: string;
    href?: string;
    fileId?: string;
    conversationId?: string;
    usageIncrement?: number;
  },
) {
  const normalizedLabel = String(item.label || "").trim();
  if (!item.key || !normalizedLabel) {
    return;
  }
  const usageIncrement = Math.max(0, Number(item.usageIncrement ?? 1) || 0);
  const existing = map.get(item.key);
  if (existing) {
    existing.usageCount += usageIncrement;
    if (item.conversationId) {
      existing.conversationIds.add(item.conversationId);
    }
    if (item.fileId) {
      existing.fileIds.add(item.fileId);
    }
    if (!existing.href && item.href) {
      existing.href = item.href;
    }
    return;
  }
  map.set(item.key, {
    key: item.key,
    label: normalizedLabel,
    href: item.href,
    fileIds: item.fileId ? new Set([item.fileId]) : new Set(),
    usageCount: usageIncrement,
    conversationIds: item.conversationId ? new Set([item.conversationId]) : new Set(),
  });
}

export function collectFromSourceUsage(
  usageRows: SourceUsageRecord[],
  conversationId: string,
  documents: Map<string, AggregateItem>,
  urls: Map<string, AggregateItem>,
) {
  for (const row of usageRows || []) {
    const sourceName = String(row?.source_name || "").trim();
    const sourceId = String(row?.source_id || "").trim();
    if (!sourceName && !sourceId) {
      continue;
    }
    if (HTTP_URL_RE.test(sourceName)) {
      const normalizedUrl = normalizeSourceUrl(sourceName);
      addAggregateItem(urls, {
        key: `url:${normalizedUrl.toLowerCase()}`,
        label: normalizedUrl,
        href: normalizedUrl,
        fileId: sourceId || undefined,
        conversationId,
      });
      continue;
    }
    const label = sourceName || sourceId;
    const key = sourceId ? `file:${sourceId}` : `doc:${label.toLowerCase()}`;
    addAggregateItem(documents, {
      key,
      label,
      fileId: sourceId || undefined,
      conversationId,
    });
  }
}

export function collectFromSourcesUsed(
  sourceRows: AgentSourceRecord[],
  conversationId: string,
  documents: Map<string, AggregateItem>,
  urls: Map<string, AggregateItem>,
) {
  for (const row of sourceRows || []) {
    const label = String(row?.label || "").trim();
    const url = String(row?.url || "").trim();
    const fileId = String(row?.file_id || "").trim();
    if (url && HTTP_URL_RE.test(url)) {
      const normalizedUrl = normalizeSourceUrl(url);
      addAggregateItem(urls, {
        key: `url:${normalizedUrl.toLowerCase()}`,
        label: normalizedUrl,
        href: normalizedUrl,
        fileId: fileId || undefined,
        conversationId,
      });
      continue;
    }
    const docLabel = label || fileId;
    if (!docLabel) {
      continue;
    }
    const key = fileId ? `file:${fileId}` : `doc:${docLabel.toLowerCase()}`;
    addAggregateItem(documents, {
      key,
      label: docLabel,
      fileId: fileId || undefined,
      conversationId,
    });
  }
}

export function collectFromAttachments(
  attachmentRows: Array<{ name?: string; fileId?: string }>,
  conversationId: string,
  documents: Map<string, AggregateItem>,
) {
  const seen = new Set<string>();
  for (const row of attachmentRows || []) {
    const name = String(row?.name || "").trim();
    const fileId = String(row?.fileId || "").trim();
    const label = name || fileId;
    if (!label) {
      continue;
    }
    const key = fileId ? `file:${fileId}` : `doc:${label.toLowerCase()}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    addAggregateItem(documents, {
      key,
      label,
      fileId: fileId || undefined,
      conversationId,
    });
  }
}

export function addFromFileRecord(
  fileId: string,
  fileRecord: FileRecord | undefined,
  conversationId: string | undefined,
  documents: Map<string, AggregateItem>,
  urls: Map<string, AggregateItem>,
) {
  const resolvedFileId = String(fileId || fileRecord?.id || "").trim();
  if (!resolvedFileId) {
    return;
  }
  const url = fileRecord ? getFileRecordUrl(fileRecord) : "";
  if (url) {
    addAggregateItem(urls, {
      key: `url:${url.toLowerCase()}`,
      label: url,
      href: url,
      fileId: resolvedFileId,
      conversationId,
      usageIncrement: 0,
    });
    return;
  }
  const label = String(fileRecord?.name || resolvedFileId).trim();
  if (!label) {
    return;
  }
  addAggregateItem(documents, {
    key: `file:${resolvedFileId}`,
    label,
    fileId: resolvedFileId,
    conversationId,
    usageIncrement: 0,
  });
}

export function collectFromSelectedPayload(
  rawSelected: unknown,
  conversationId: string,
  filesById: Map<string, FileRecord>,
  documents: Map<string, AggregateItem>,
  urls: Map<string, AggregateItem>,
) {
  if (!rawSelected || typeof rawSelected !== "object") {
    return;
  }
  const selectedRecord = rawSelected as Record<string, unknown>;
  const seen = new Set<string>();
  for (const value of Object.values(selectedRecord)) {
    if (!Array.isArray(value) || value.length < 2) {
      continue;
    }
    const mode = String(value[0] || "").trim().toLowerCase();
    if (mode === "disabled") {
      continue;
    }
    const fileIds = Array.isArray(value[1]) ? value[1] : [];
    for (const fileIdRaw of fileIds) {
      const fileId = String(fileIdRaw || "").trim();
      if (!fileId || seen.has(fileId)) {
        continue;
      }
      seen.add(fileId);
      addFromFileRecord(fileId, filesById.get(fileId), conversationId, documents, urls);
    }
  }
}

export function collectFromInfoEvidence(
  infoHtml: string,
  conversationId: string,
  documents: Map<string, AggregateItem>,
  urls: Map<string, AggregateItem>,
) {
  const html = String(infoHtml || "");
  if (!html || !/details[^>]*class=['"][^'"]*evidence/i.test(html)) {
    return;
  }
  const cards = parseEvidence(html);
  for (const card of cards) {
    const sourceUrl = normalizeUrlCandidates([card.sourceUrl, card.source]);
    const fileId = String(card.fileId || "").trim();
    if (sourceUrl) {
      addAggregateItem(urls, {
        key: `url:${sourceUrl.toLowerCase()}`,
        label: sourceUrl,
        href: sourceUrl,
        fileId: fileId || undefined,
        conversationId,
      });
      continue;
    }
    const label = String(card.source || fileId).trim();
    if (!label) {
      continue;
    }
    addAggregateItem(documents, {
      key: fileId ? `file:${fileId}` : `doc:${label.toLowerCase()}`,
      label,
      fileId: fileId || undefined,
      conversationId,
    });
  }
}

export function collectFromProjectBindings(
  binding: ProjectSourceBinding,
  filesById: Map<string, FileRecord>,
  documents: Map<string, AggregateItem>,
  urls: Map<string, AggregateItem>,
) {
  const fileIds = Array.from(
    new Set((binding.fileIds || []).map((value) => String(value || "").trim()).filter(Boolean)),
  );
  for (const fileId of fileIds) {
    addFromFileRecord(fileId, filesById.get(fileId), undefined, documents, urls);
  }

  const urlsList = Array.from(
    new Set((binding.urls || []).map((value) => normalizeSourceUrl(String(value || ""))).filter(Boolean)),
  );
  for (const url of urlsList) {
    addAggregateItem(urls, {
      key: `url:${url.toLowerCase()}`,
      label: url,
      href: url,
      conversationId: undefined,
      usageIncrement: 0,
    });
  }
}
