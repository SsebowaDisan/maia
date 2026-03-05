import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRightLeft,
  Check,
  ChevronRight,
  Folder,
  FolderOpen,
  FolderPlus,
  Globe,
  HelpCircle,
  Link2,
  Loader2,
  PencilLine,
  Plus,
  Settings,
  Trash2,
  X,
  FileText,
  Library,
} from "lucide-react";
import {
  deleteFiles,
  deleteUrls,
  getConversation,
  listFiles,
  uploadFiles,
  uploadUrls,
  type ConversationSummary,
  type SourceUsageRecord,
  type AgentSourceRecord,
  type FileRecord,
} from "../../api/client";
import { buildConversationTurns } from "../appShell/eventHelpers";
import { parseEvidence } from "../utils/infoInsights";

const LETTER_OR_NUMBER_RE = /^[\p{L}\p{N}]$/u;
const EXTENDED_PICTOGRAPHIC_RE = /^\p{Extended_Pictographic}$/u;

function startsWithIcon(text: string) {
  const chars = Array.from(text);
  if (!chars.length) {
    return false;
  }
  const first = chars[0] || "";
  if (!first || LETTER_OR_NUMBER_RE.test(first)) {
    return false;
  }
  const codePoint = first.codePointAt(0) || 0;
  return EXTENDED_PICTOGRAPHIC_RE.test(first) || codePoint >= 0x2600;
}

function displayConversationName(name: string) {
  const cleaned = String(name || "").trim();
  if (!cleaned) {
    return "New chat";
  }
  return cleaned;
}

function stripChatIcon(name: string) {
  const cleaned = String(name || "").trim();
  const chars = Array.from(cleaned);
  if (chars.length >= 2 && startsWithIcon(cleaned) && chars[1] === " ") {
    return chars.slice(2).join("").trim();
  }
  return cleaned;
}

type ProjectEvidenceItem = {
  key: string;
  label: string;
  type: "document" | "url";
  href?: string;
  fileIds: string[];
  usageCount: number;
  chatCount: number;
};

type ProjectEvidenceState = {
  status: "idle" | "loading" | "ready" | "error";
  documents: ProjectEvidenceItem[];
  urls: ProjectEvidenceItem[];
  projectChatCount: number;
  errorMessage: string;
};

const EMPTY_PROJECT_EVIDENCE: ProjectEvidenceState = {
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

const HTTP_URL_RE = /^https?:\/\/\S+/i;
const SOURCE_ALIAS_STORAGE_KEY = "maia.project-source-aliases";
const PROJECT_SOURCE_BINDINGS_STORAGE_KEY = "maia.project-source-bindings";

type ProjectSourceBinding = {
  fileIds: string[];
  urls: string[];
};

function normalizeSourceUrl(rawValue: string): string {
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

function normalizeUrlCandidates(values: Array<unknown>): string {
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

function normalizeUrlDraftList(rawDraft: string): string[] {
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

function getFileRecordUrl(file: FileRecord): string {
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

function toProjectEvidenceItems(
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

function collectFromSourceUsage(
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

function collectFromSourcesUsed(
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

function collectFromAttachments(
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

function addFromFileRecord(
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

function collectFromSelectedPayload(
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

function collectFromInfoEvidence(
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

function collectFromProjectBindings(
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

interface SidebarProject {
  id: string;
  name: string;
}

interface ChatSidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  conversations: ConversationSummary[];
  allConversations: ConversationSummary[];
  selectedConversationId: string | null;
  onSelectConversation: (conversationId: string) => void;
  onNewConversation: () => void;
  projects: SidebarProject[];
  selectedProjectId: string;
  onSelectProject: (projectId: string) => void;
  onCreateProject: (name: string) => void;
  onRenameProject: (projectId: string, name: string) => void;
  onDeleteProject: (projectId: string) => void;
  canDeleteProject: boolean;
  conversationProjects: Record<string, string>;
  onMoveConversationToProject: (conversationId: string, projectId: string) => void;
  onRenameConversation: (conversationId: string, name: string) => Promise<void>;
  onDeleteConversation: (conversationId: string) => Promise<void>;
  onOpenWorkspaceTab: (tab: "Files" | "Resources" | "Settings" | "Help") => void;
  width?: number;
}

export function ChatSidebar({
  isCollapsed,
  onToggleCollapse,
  conversations,
  allConversations,
  selectedConversationId,
  onSelectConversation,
  onNewConversation,
  projects,
  selectedProjectId,
  onSelectProject,
  onCreateProject,
  onRenameProject,
  onDeleteProject,
  canDeleteProject,
  conversationProjects,
  onMoveConversationToProject,
  onRenameConversation,
  onDeleteConversation,
  onOpenWorkspaceTab,
  width = 300,
}: ChatSidebarProps) {
  const [isAddingProject, setIsAddingProject] = useState(false);
  const [projectDraft, setProjectDraft] = useState("");
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editingProjectDraft, setEditingProjectDraft] = useState("");
  const [movingConversationId, setMovingConversationId] = useState<string | null>(null);
  const [renamingConversationId, setRenamingConversationId] = useState<string | null>(null);
  const [renamingConversationDraft, setRenamingConversationDraft] = useState("");
  const [busyConversationId, setBusyConversationId] = useState<string | null>(null);
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const [openProjectEvidenceId, setOpenProjectEvidenceId] = useState<string | null>(null);
  const [projectEvidenceById, setProjectEvidenceById] = useState<
    Record<string, ProjectEvidenceState>
  >({});
  const [projectUrlDraftById, setProjectUrlDraftById] = useState<Record<string, string>>({});
  const [projectUploadStatusById, setProjectUploadStatusById] = useState<Record<string, string>>(
    {},
  );
  const [projectUploadBusyById, setProjectUploadBusyById] = useState<Record<string, boolean>>({});
  const [sourceAliases, setSourceAliases] = useState<Record<string, string>>(() => {
    if (typeof window === "undefined") {
      return {};
    }
    try {
      const raw = window.localStorage.getItem(SOURCE_ALIAS_STORAGE_KEY);
      if (!raw) {
        return {};
      }
      const parsed = JSON.parse(raw) as Record<string, string>;
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  });
  const [projectSourceBindings, setProjectSourceBindings] = useState<
    Record<string, ProjectSourceBinding>
  >(() => {
    if (typeof window === "undefined") {
      return {};
    }
    try {
      const raw = window.localStorage.getItem(PROJECT_SOURCE_BINDINGS_STORAGE_KEY);
      if (!raw) {
        return {};
      }
      const parsed = JSON.parse(raw) as Record<
        string,
        { fileIds?: unknown; urls?: unknown }
      >;
      if (!parsed || typeof parsed !== "object") {
        return {};
      }
      const normalized: Record<string, ProjectSourceBinding> = {};
      for (const [projectId, value] of Object.entries(parsed)) {
        if (!value || typeof value !== "object") {
          continue;
        }
        normalized[projectId] = {
          fileIds: Array.from(
            new Set(
              (Array.isArray(value.fileIds) ? value.fileIds : [])
                .map((item) => String(item || "").trim())
                .filter(Boolean),
            ),
          ),
          urls: Array.from(
            new Set(
              (Array.isArray(value.urls) ? value.urls : [])
                .map((item) => normalizeSourceUrl(String(item || "")))
                .filter(Boolean),
            ),
          ),
        };
      }
      return normalized;
    } catch {
      return {};
    }
  });
  const [editingEvidenceKey, setEditingEvidenceKey] = useState<string | null>(null);
  const [editingEvidenceDraft, setEditingEvidenceDraft] = useState("");
  const [evidenceActionBusyByKey, setEvidenceActionBusyByKey] = useState<
    Record<string, boolean>
  >({});
  const projectEvidenceRequestRef = useRef(0);
  const fileInputByProjectRef = useRef<Record<string, HTMLInputElement | null>>({});

  const fallbackProjectId = useMemo(() => projects[0]?.id || "", [projects]);

  const selectedProjectConversations = useMemo(
    () =>
      [...conversations].sort(
        (left, right) =>
          new Date(right.date_updated).getTime() - new Date(left.date_updated).getTime(),
      ),
    [conversations],
  );

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(SOURCE_ALIAS_STORAGE_KEY, JSON.stringify(sourceAliases));
  }, [sourceAliases]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(
      PROJECT_SOURCE_BINDINGS_STORAGE_KEY,
      JSON.stringify(projectSourceBindings),
    );
  }, [projectSourceBindings]);

  const setProjectUploadStatus = useCallback((projectId: string, message: string) => {
    setProjectUploadStatusById((prev) => ({
      ...prev,
      [projectId]: message,
    }));
  }, []);

  const setProjectUploadBusy = useCallback((projectId: string, isBusy: boolean) => {
    setProjectUploadBusyById((prev) => ({
      ...prev,
      [projectId]: isBusy,
    }));
  }, []);

  const appendProjectSourceBindings = useCallback(
    (projectId: string, payload: { fileIds?: string[]; urls?: string[] }) => {
      setProjectSourceBindings((prev) => {
        const current = prev[projectId] || { fileIds: [], urls: [] };
        const nextFileIds = Array.from(
          new Set([
            ...current.fileIds,
            ...((payload.fileIds || []).map((item) => String(item || "").trim()).filter(Boolean)),
          ]),
        );
        const nextUrls = Array.from(
          new Set([
            ...current.urls,
            ...((payload.urls || [])
              .map((item) => normalizeSourceUrl(String(item || "")))
              .filter(Boolean)),
          ]),
        );
        return {
          ...prev,
          [projectId]: {
            fileIds: nextFileIds,
            urls: nextUrls,
          },
        };
      });
    },
    [],
  );

  const loadProjectEvidence = useCallback(
    async (projectId: string) => {
      const projectConversations = allConversations.filter(
        (conversation) =>
          (conversationProjects[conversation.id] || fallbackProjectId) === projectId,
      );

      const requestId = projectEvidenceRequestRef.current + 1;
      projectEvidenceRequestRef.current = requestId;
      setProjectEvidenceById((prev) => ({
        ...prev,
        [projectId]: {
          ...(prev[projectId] || EMPTY_PROJECT_EVIDENCE),
          status: "loading",
          errorMessage: "",
          projectChatCount: projectConversations.length,
        },
      }));

      if (!projectConversations.length) {
        setProjectEvidenceById((prev) => ({
          ...prev,
          [projectId]: {
            ...EMPTY_PROJECT_EVIDENCE,
            status: "ready",
            projectChatCount: 0,
          },
        }));
        return;
      }

      const documents = new Map<string, AggregateItem>();
      const urls = new Map<string, AggregateItem>();

      try {
        const fileCatalog = await listFiles({ includeChatTemp: true }).catch(() => ({
          index_id: 0,
          files: [] as FileRecord[],
        }));
        const filesById = new Map<string, FileRecord>();
        for (const file of fileCatalog.files || []) {
          const fileId = String(file.id || "").trim();
          if (!fileId || filesById.has(fileId)) {
            continue;
          }
          filesById.set(fileId, file);
        }

        await Promise.all(
          projectConversations.map(async (conversation) => {
            const detail = await getConversation(conversation.id);
            const { turns } = buildConversationTurns(detail);
            collectFromSelectedPayload(
              (detail.data_source as { selected?: unknown } | undefined)?.selected,
              conversation.id,
              filesById,
              documents,
              urls,
            );
            for (const turn of turns) {
              collectFromAttachments(
                turn.attachments || [],
                conversation.id,
                documents,
              );
              collectFromSourceUsage(
                turn.sourceUsage || [],
                conversation.id,
                documents,
                urls,
              );
              collectFromSourcesUsed(
                turn.sourcesUsed || [],
                conversation.id,
                documents,
                urls,
              );
              collectFromInfoEvidence(
                turn.info || "",
                conversation.id,
                documents,
                urls,
              );
            }
          }),
        );
        collectFromProjectBindings(
          projectSourceBindings[projectId] || { fileIds: [], urls: [] },
          filesById,
          documents,
          urls,
        );
        if (documents.size === 0 && urls.size === 0) {
          for (const file of fileCatalog.files || []) {
            const fileId = String(file.id || "").trim();
            if (!fileId) {
              continue;
            }
            addFromFileRecord(fileId, file, undefined, documents, urls);
          }
        }
        if (projectEvidenceRequestRef.current !== requestId) {
          return;
        }
        setProjectEvidenceById((prev) => ({
          ...prev,
          [projectId]: {
            status: "ready",
            documents: toProjectEvidenceItems(documents, "document"),
            urls: toProjectEvidenceItems(urls, "url"),
            projectChatCount: projectConversations.length,
            errorMessage: "",
          },
        }));
      } catch (error) {
        if (projectEvidenceRequestRef.current !== requestId) {
          return;
        }
        setProjectEvidenceById((prev) => ({
          ...prev,
          [projectId]: {
            ...(prev[projectId] || EMPTY_PROJECT_EVIDENCE),
            status: "error",
            errorMessage: `Unable to load sources: ${String(error)}`,
            projectChatCount: projectConversations.length,
          },
        }));
      }
    },
    [allConversations, conversationProjects, fallbackProjectId, projectSourceBindings],
  );

  const toggleProjectEvidenceCard = useCallback(
    (projectId: string) => {
      const isClosingCurrent = openProjectEvidenceId === projectId;
      setOpenProjectEvidenceId(isClosingCurrent ? null : projectId);
      setEditingEvidenceKey(null);
      setEditingEvidenceDraft("");
      if (!isClosingCurrent) {
        setProjectUploadStatus(projectId, "");
        void loadProjectEvidence(projectId);
      }
    },
    [loadProjectEvidence, openProjectEvidenceId, setProjectUploadStatus],
  );

  const handleProjectFileUpload = useCallback(
    async (projectId: string, files: FileList | null) => {
      if (!files || files.length <= 0) {
        return;
      }
      setProjectUploadBusy(projectId, true);
      setProjectUploadStatus(projectId, "Uploading files...");
      try {
        const response = await uploadFiles(files, {
          scope: "persistent",
          reindex: true,
        });
        const uploadedFileIds = response.items
          .filter((item) => item.status === "success")
          .map((item) => String(item.file_id || "").trim())
          .filter(Boolean);
        if (uploadedFileIds.length > 0) {
          appendProjectSourceBindings(projectId, {
            fileIds: uploadedFileIds,
          });
        }
        const successCount = response.items.filter((item) => item.status === "success").length;
        const failureCount = response.items.length - successCount;
        setProjectUploadStatus(
          projectId,
          failureCount > 0
            ? `Uploaded ${successCount} file(s), ${failureCount} failed.`
            : `Uploaded ${successCount} file(s).`,
        );
        await loadProjectEvidence(projectId);
      } catch (error) {
        setProjectUploadStatus(projectId, `File upload failed: ${String(error)}`);
      } finally {
        setProjectUploadBusy(projectId, false);
      }
    },
    [appendProjectSourceBindings, loadProjectEvidence, setProjectUploadBusy, setProjectUploadStatus],
  );

  const submitProjectUrls = useCallback(
    async (projectId: string) => {
      const draft = String(projectUrlDraftById[projectId] || "").trim();
      if (!draft) {
        return;
      }
      setProjectUploadBusy(projectId, true);
      setProjectUploadStatus(projectId, "Indexing URLs...");
      try {
        const normalizedUrls = normalizeUrlDraftList(draft);
        const response = await uploadUrls(draft, {
          reindex: false,
          web_crawl_depth: 0,
          web_crawl_max_pages: 0,
          web_crawl_same_domain_only: true,
          include_pdfs: true,
          include_images: true,
        });
        const indexedFileIds = response.items
          .filter((item) => item.status === "success")
          .map((item) => String(item.file_id || "").trim())
          .filter(Boolean);
        if (normalizedUrls.length > 0 || indexedFileIds.length > 0) {
          appendProjectSourceBindings(projectId, {
            urls: normalizedUrls,
            fileIds: indexedFileIds,
          });
        }
        const successCount = response.items.filter((item) => item.status === "success").length;
        const failureCount = response.items.length - successCount;
        setProjectUploadStatus(
          projectId,
          failureCount > 0
            ? `Indexed ${successCount} URL source(s), ${failureCount} failed.`
            : `Indexed ${successCount} URL source(s).`,
        );
        setProjectUrlDraftById((prev) => ({
          ...prev,
          [projectId]: "",
        }));
        await loadProjectEvidence(projectId);
      } catch (error) {
        setProjectUploadStatus(projectId, `URL indexing failed: ${String(error)}`);
      } finally {
        setProjectUploadBusy(projectId, false);
      }
    },
    [
      appendProjectSourceBindings,
      loadProjectEvidence,
      projectUrlDraftById,
      setProjectUploadBusy,
      setProjectUploadStatus,
    ],
  );

  const closeEvidenceModal = useCallback(() => {
    setOpenProjectEvidenceId(null);
    setEditingEvidenceKey(null);
    setEditingEvidenceDraft("");
  }, []);

  const getEvidenceDisplayLabel = useCallback(
    (item: ProjectEvidenceItem) => {
      const alias = String(sourceAliases[item.key] || "").trim();
      return alias || item.label;
    },
    [sourceAliases],
  );

  const startRenameEvidenceItem = useCallback(
    (item: ProjectEvidenceItem) => {
      setEditingEvidenceKey(item.key);
      setEditingEvidenceDraft(getEvidenceDisplayLabel(item));
    },
    [getEvidenceDisplayLabel],
  );

  const cancelRenameEvidenceItem = useCallback(() => {
    setEditingEvidenceKey(null);
    setEditingEvidenceDraft("");
  }, []);

  const commitRenameEvidenceItem = useCallback(
    (item: ProjectEvidenceItem) => {
      const nextLabel = editingEvidenceDraft.trim();
      if (!nextLabel) {
        return;
      }
      setSourceAliases((prev) => {
        const currentAlias = String(prev[item.key] || "").trim();
        if (nextLabel === item.label || nextLabel === currentAlias) {
          if (!currentAlias) {
            return prev;
          }
          const next = { ...prev };
          delete next[item.key];
          return next;
        }
        return {
          ...prev,
          [item.key]: nextLabel,
        };
      });
      setEditingEvidenceKey(null);
      setEditingEvidenceDraft("");
    },
    [editingEvidenceDraft],
  );

  const evidenceProject = useMemo(
    () => projects.find((project) => project.id === openProjectEvidenceId) || null,
    [projects, openProjectEvidenceId],
  );
  const evidenceProjectId = evidenceProject?.id || "";
  const evidenceProjectState = evidenceProjectId
    ? projectEvidenceById[evidenceProjectId] || EMPTY_PROJECT_EVIDENCE
    : EMPTY_PROJECT_EVIDENCE;
  const evidenceProjectUploadBusy = evidenceProjectId
    ? Boolean(projectUploadBusyById[evidenceProjectId])
    : false;
  const evidenceProjectUploadStatus = evidenceProjectId
    ? String(projectUploadStatusById[evidenceProjectId] || "")
    : "";
  const evidenceProjectUrlDraft = evidenceProjectId
    ? String(projectUrlDraftById[evidenceProjectId] || "")
    : "";

  const handleDeleteEvidenceItem = useCallback(
    async (item: ProjectEvidenceItem) => {
      if (!evidenceProjectId) {
        return;
      }
      const fileIds = Array.from(new Set((item.fileIds || []).filter(Boolean)));
      const fallbackUrl = String(item.href || item.label || "").trim();
      const canDeleteViaUrl = item.type === "url" && Boolean(fallbackUrl);
      if (!fileIds.length && !canDeleteViaUrl) {
        setProjectUploadStatus(
          evidenceProjectId,
          `Delete unavailable for "${getEvidenceDisplayLabel(item)}".`,
        );
        return;
      }

      const confirmed = window.confirm(
        `Delete "${getEvidenceDisplayLabel(item)}" from indexed sources? This removes it from retrieval.`,
      );
      if (!confirmed) {
        return;
      }

      setEvidenceActionBusyByKey((prev) => ({ ...prev, [item.key]: true }));
      try {
        if (fileIds.length) {
          const response = await deleteFiles(fileIds);
          const deletedCount = response.deleted_ids.length;
          const failedCount = response.failed.length;
          setProjectUploadStatus(
            evidenceProjectId,
            failedCount > 0
              ? `Deleted ${deletedCount} source(s), ${failedCount} failed.`
              : `Deleted ${deletedCount} source(s).`,
          );
        } else {
          const response = await deleteUrls([fallbackUrl]);
          const deletedCount = response.deleted_ids.length;
          const failedCount = response.failed.length;
          if (deletedCount > 0) {
            setProjectUploadStatus(
              evidenceProjectId,
              failedCount > 0
                ? `Deleted ${deletedCount} source(s), ${failedCount} URL(s) failed.`
                : `Deleted ${deletedCount} source(s) from URL.`,
            );
          } else {
            const firstFailure = response.failed[0];
            setProjectUploadStatus(
              evidenceProjectId,
              firstFailure?.message || "No indexed source matched this URL.",
            );
          }
        }
        setSourceAliases((prev) => {
          if (!Object.prototype.hasOwnProperty.call(prev, item.key)) {
            return prev;
          }
          const next = { ...prev };
          delete next[item.key];
          return next;
        });
        setProjectSourceBindings((prev) => {
          const current = prev[evidenceProjectId];
          if (!current) {
            return prev;
          }
          const itemFileIds = new Set((item.fileIds || []).map((value) => String(value || "").trim()).filter(Boolean));
          const fallbackUrl = normalizeSourceUrl(String(item.href || item.label || ""));
          const nextFileIds = current.fileIds.filter((value) => !itemFileIds.has(String(value || "").trim()));
          const nextUrls = fallbackUrl
            ? current.urls.filter((value) => normalizeSourceUrl(String(value || "")) !== fallbackUrl)
            : current.urls;
          if (
            nextFileIds.length === current.fileIds.length &&
            nextUrls.length === current.urls.length
          ) {
            return prev;
          }
          return {
            ...prev,
            [evidenceProjectId]: {
              fileIds: nextFileIds,
              urls: nextUrls,
            },
          };
        });
        await loadProjectEvidence(evidenceProjectId);
      } catch (error) {
        setProjectUploadStatus(
          evidenceProjectId,
          `Delete failed for "${getEvidenceDisplayLabel(item)}": ${String(error)}`,
        );
      } finally {
        setEvidenceActionBusyByKey((prev) => ({ ...prev, [item.key]: false }));
      }
    },
    [evidenceProjectId, getEvidenceDisplayLabel, loadProjectEvidence, setProjectUploadStatus],
  );

  useEffect(() => {
    if (!editingEvidenceKey) {
      return;
    }
    const existsInProject = [
      ...(evidenceProjectState.documents || []),
      ...(evidenceProjectState.urls || []),
    ].some((item) => item.key === editingEvidenceKey);
    if (!existsInProject) {
      setEditingEvidenceKey(null);
      setEditingEvidenceDraft("");
    }
  }, [editingEvidenceKey, evidenceProjectState.documents, evidenceProjectState.urls]);

  useEffect(() => {
    if (!openProjectEvidenceId) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeEvidenceModal();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closeEvidenceModal, openProjectEvidenceId]);

  const submitProject = () => {
    const normalized = projectDraft.trim();
    if (!normalized) {
      return;
    }
    onCreateProject(normalized);
    setProjectDraft("");
    setIsAddingProject(false);
  };

  const startRenameProject = (project: SidebarProject) => {
    setEditingProjectId(project.id);
    setEditingProjectDraft(project.name);
  };

  const commitRenameProject = () => {
    if (!editingProjectId) {
      return;
    }
    const normalized = editingProjectDraft.trim();
    if (!normalized) {
      return;
    }
    onRenameProject(editingProjectId, normalized);
    setEditingProjectId(null);
    setEditingProjectDraft("");
  };

  const cancelRenameProject = () => {
    setEditingProjectId(null);
    setEditingProjectDraft("");
  };

  const requestDeleteProject = (project: SidebarProject) => {
    if (!canDeleteProject) {
      return;
    }
    const deletingLastProject = projects.length <= 1;
    const confirmed = window.confirm(
      deletingLastProject
        ? `Delete project \"${project.name}\"? Maia will create a replacement project automatically.`
        : `Delete project \"${project.name}\"? Conversations in it will be reassigned automatically.`,
    );
    if (confirmed) {
      setProjectSourceBindings((prev) => {
        if (!Object.prototype.hasOwnProperty.call(prev, project.id)) {
          return prev;
        }
        const next = { ...prev };
        delete next[project.id];
        return next;
      });
      onDeleteProject(project.id);
    }
  };

  const startRenameConversation = (conversation: ConversationSummary) => {
    setRenamingConversationId(conversation.id);
    setRenamingConversationDraft(stripChatIcon(conversation.name));
    setMovingConversationId(null);
  };

  const cancelRenameConversation = () => {
    setRenamingConversationId(null);
    setRenamingConversationDraft("");
  };

  const commitRenameConversation = async (conversationId: string) => {
    const normalized = renamingConversationDraft.trim();
    if (!normalized) {
      return;
    }
    setBusyConversationId(conversationId);
    try {
      await onRenameConversation(conversationId, normalized);
      setRenamingConversationId(null);
      setRenamingConversationDraft("");
    } catch (error) {
      console.error(error);
    } finally {
      setBusyConversationId(null);
    }
  };

  const requestDeleteConversation = async (conversation: ConversationSummary) => {
    const confirmed = window.confirm(
      `Delete chat \"${displayConversationName(conversation.name)}\"?`,
    );
    if (!confirmed) {
      return;
    }
    setBusyConversationId(conversation.id);
    try {
      await onDeleteConversation(conversation.id);
      if (movingConversationId === conversation.id) {
        setMovingConversationId(null);
      }
      if (renamingConversationId === conversation.id) {
        cancelRenameConversation();
      }
    } catch (error) {
      console.error(error);
    } finally {
      setBusyConversationId(null);
    }
  };

  if (isCollapsed) {
    return (
      <div className="w-16 min-h-0 bg-[#f6f6f7] border-r border-black/[0.06] flex flex-col items-center py-4">
        <button
          onClick={onToggleCollapse}
          className="p-2 rounded-xl hover:bg-black/5 transition-colors"
          title="Expand sidebar"
        >
          <ChevronRight className="w-5 h-5 text-[#6e6e73]" />
        </button>
      </div>
    );
  }

  return (
    <div
      className="min-h-0 bg-[#f6f6f7] border-r border-black/[0.06] flex flex-col overflow-hidden"
      style={{ width: `${Math.round(width)}px` }}
    >
      <div className="px-4 pt-4 pb-3 border-b border-black/[0.06]">
        <div className="flex items-center justify-between">
          <h2 className="text-[17px] font-medium tracking-tight text-[#1d1d1f]">Projects</h2>
          <button
            onClick={onToggleCollapse}
            className="p-1.5 rounded-lg hover:bg-black/5 transition-colors"
            title="Collapse sidebar"
          >
            <ChevronRight className="w-4 h-4 text-[#6e6e73]" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        <div className="space-y-1">
          {isAddingProject ? (
            <div className="rounded-xl bg-white border border-black/[0.08] px-2 py-2 flex items-center gap-1.5">
              <input
                value={projectDraft}
                onChange={(event) => setProjectDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    submitProject();
                  }
                }}
                placeholder="Project name"
                className="flex-1 h-8 px-2.5 rounded-lg border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] placeholder:text-[#8d8d93] focus:outline-none focus:ring-2 focus:ring-black/10"
              />
              <button
                onClick={submitProject}
                className="h-8 px-2.5 rounded-lg bg-[#1d1d1f] text-white text-[11px] hover:bg-[#343438] transition-colors"
              >
                Add
              </button>
            </div>
          ) : (
            <button
              onClick={() => setIsAddingProject(true)}
              className="w-full h-10 px-2.5 rounded-xl text-left text-[15px] text-[#0a0a0a] hover:bg-[#ececef] transition-colors inline-flex items-center gap-2"
            >
              <FolderPlus className="w-4.5 h-4.5 text-[#1d1d1f]" />
              <span>New project</span>
            </button>
          )}

          {projects.map((project) => {
            const isActive = project.id === selectedProjectId;
            const isEditing = editingProjectId === project.id;
            const isEvidenceOpen = openProjectEvidenceId === project.id;
            return (
              <div key={project.id} className="rounded-xl">
                {isEditing ? (
                  <div className="rounded-xl bg-white border border-black/[0.08] px-2 py-1.5 flex items-center gap-1">
                    <input
                      value={editingProjectDraft}
                      onChange={(event) => setEditingProjectDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          commitRenameProject();
                        }
                        if (event.key === "Escape") {
                          event.preventDefault();
                          cancelRenameProject();
                        }
                      }}
                      className="flex-1 h-8 px-2.5 rounded-md border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] focus:outline-none focus:ring-2 focus:ring-black/10"
                    />
                    <button
                      onClick={commitRenameProject}
                      className="p-1.5 rounded-md text-[#1d1d1f] hover:bg-black/10"
                      title="Save"
                    >
                      <Check className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={cancelRenameProject}
                      className="p-1.5 rounded-md text-[#1d1d1f] hover:bg-black/10"
                      title="Cancel"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : (
                  <div className={`group h-10 px-2.5 rounded-xl inline-flex items-center gap-2 w-full ${isActive ? "bg-[#e7e7ea]" : "hover:bg-[#ececef]"}`}>
                    <button
                      onClick={() => onSelectProject(project.id)}
                      className="flex-1 min-w-0 inline-flex items-center gap-2 text-left"
                    >
                      {isActive ? (
                        <FolderOpen className="w-4.5 h-4.5 text-[#1d1d1f] shrink-0" />
                      ) : (
                        <Folder className="w-4.5 h-4.5 text-[#1d1d1f] shrink-0" />
                      )}
                      <span className="text-[15px] text-[#1d1d1f] truncate">{project.name}</span>
                    </button>
                    <button
                      onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        void toggleProjectEvidenceCard(project.id);
                      }}
                      className={`p-1 rounded-md hover:bg-black/5 hover:text-[#1d1d1f] transition-opacity ${isEvidenceOpen ? "text-[#1d1d1f] opacity-100" : "text-[#6e6e73] opacity-0 group-hover:opacity-100"}`}
                      title="Project sources and uploads"
                    >
                      <FileText className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => startRenameProject(project)}
                      className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Rename project"
                    >
                      <PencilLine className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => requestDeleteProject(project)}
                      disabled={!canDeleteProject}
                      className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-35 disabled:cursor-not-allowed"
                      title={canDeleteProject ? "Delete project" : "Delete unavailable"}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}

                {isActive ? (
                  <div className="pl-8 pr-1 pb-2 pt-1">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[12px] text-[#8d8d93]">Recent</span>
                      <button
                        onClick={onNewConversation}
                        className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f]"
                        title="New chat in this project"
                      >
                        <Plus className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {selectedProjectConversations.length ? (
                      <div className="space-y-1">
                        {selectedProjectConversations.map((conversation) => {
                          const isSelected = conversation.id === selectedConversationId;
                          const isMoving = movingConversationId === conversation.id;
                          const isRenaming = renamingConversationId === conversation.id;
                          const isBusy = busyConversationId === conversation.id;
                          const assignedProjectId =
                            conversationProjects[conversation.id] || fallbackProjectId;

                          return (
                            <div key={conversation.id} className="rounded-lg">
                              {isRenaming ? (
                                <div className="bg-white border border-black/[0.08] rounded-lg px-2 py-1.5 flex items-center gap-1">
                                  <input
                                    value={renamingConversationDraft}
                                    onChange={(event) => setRenamingConversationDraft(event.target.value)}
                                    onKeyDown={(event) => {
                                      if (event.key === "Enter") {
                                        event.preventDefault();
                                        void commitRenameConversation(conversation.id);
                                      }
                                      if (event.key === "Escape") {
                                        event.preventDefault();
                                        cancelRenameConversation();
                                      }
                                    }}
                                    className="flex-1 h-7 px-2 rounded-md border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] focus:outline-none focus:ring-2 focus:ring-black/10"
                                  />
                                  <button
                                    onClick={() => void commitRenameConversation(conversation.id)}
                                    disabled={isBusy}
                                    className="p-1 rounded-md text-[#1d1d1f] hover:bg-black/10 disabled:opacity-40"
                                    title="Save name"
                                  >
                                    <Check className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={cancelRenameConversation}
                                    disabled={isBusy}
                                    className="p-1 rounded-md text-[#1d1d1f] hover:bg-black/10 disabled:opacity-40"
                                    title="Cancel"
                                  >
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                              ) : (
                                <div className={`group rounded-lg px-2 py-1.5 inline-flex items-center gap-1 w-full ${isSelected ? "bg-[#e4e4e8]" : "hover:bg-[#ececef]"}`}>
                                  <button
                                    onClick={() => onSelectConversation(conversation.id)}
                                    className="flex-1 min-w-0 text-left"
                                  >
                                    <p className="text-[14px] text-[#1d1d1f] truncate">{displayConversationName(conversation.name)}</p>
                                  </button>
                                  <button
                                    onClick={() => startRenameConversation(conversation)}
                                    disabled={isBusy}
                                    className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-40"
                                    title="Rename chat"
                                  >
                                    <PencilLine className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={() =>
                                      setMovingConversationId((current) =>
                                        current === conversation.id ? null : conversation.id,
                                      )
                                    }
                                    disabled={isBusy}
                                    className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-40"
                                    title="Move chat"
                                  >
                                    <ArrowRightLeft className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={() => void requestDeleteConversation(conversation)}
                                    disabled={isBusy}
                                    className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-40"
                                    title="Delete chat"
                                  >
                                    <Trash2 className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                              )}

                              {isMoving ? (
                                <div className="mt-1 rounded-lg border border-black/[0.08] bg-white p-1 space-y-1">
                                  {projects.map((targetProject) => {
                                    const isAssigned = targetProject.id === assignedProjectId;
                                    return (
                                      <button
                                        key={targetProject.id}
                                        onClick={() => {
                                          onMoveConversationToProject(
                                            conversation.id,
                                            targetProject.id,
                                          );
                                          setMovingConversationId(null);
                                        }}
                                        className={`w-full text-left px-2 py-1.5 rounded-md text-[12px] transition-colors ${
                                          isAssigned
                                            ? "bg-[#1d1d1f] text-white"
                                            : "text-[#1d1d1f] hover:bg-[#f5f5f7]"
                                        }`}
                                      >
                                        {targetProject.name}
                                      </button>
                                    );
                                  })}
                                </div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="text-[12px] text-[#8d8d93] py-1.5">No chats yet.</p>
                    )}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>

      <div className="px-3 py-3 border-t border-black/[0.06] bg-[#f6f6f7] space-y-2.5">
        <div className="relative">
          <button
            onClick={() => setWorkspaceMenuOpen((open) => !open)}
            className="w-full h-9 px-3 rounded-xl border border-black/[0.08] bg-white text-[12px] text-[#1d1d1f] hover:bg-[#f5f5f7] transition-colors inline-flex items-center justify-center gap-2"
          >
            <Library className="w-4 h-4" />
            <span>Workspace</span>
          </button>

          {workspaceMenuOpen ? (
            <div className="absolute bottom-11 left-0 right-0 rounded-xl border border-black/[0.08] bg-white shadow-lg overflow-hidden z-20">
              {[
                { id: "Files", icon: FileText, label: "Files" },
                { id: "Resources", icon: Library, label: "Resources" },
                { id: "Settings", icon: Settings, label: "Settings" },
                { id: "Help", icon: HelpCircle, label: "Help" },
              ].map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    onOpenWorkspaceTab(item.id as "Files" | "Resources" | "Settings" | "Help");
                    setWorkspaceMenuOpen(false);
                  }}
                  className="w-full px-3 py-2.5 text-left text-[13px] text-[#1d1d1f] hover:bg-[#f5f5f7] transition-colors inline-flex items-center gap-2"
                >
                  <item.icon className="w-4 h-4 text-[#6e6e73]" />
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      {evidenceProject ? (
        <div
          className="fixed inset-0 z-[120] flex items-center justify-center p-5"
          onClick={closeEvidenceModal}
          role="dialog"
          aria-modal="true"
          aria-label={`Project sources for ${evidenceProject.name}`}
        >
          <div className="absolute inset-0 bg-black/35" />
          <div
            className="relative z-[121] w-full max-w-[980px] max-h-[86vh] rounded-2xl border border-black/[0.1] bg-white shadow-[0_24px_60px_rgba(0,0,0,0.28)] flex flex-col overflow-hidden"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="px-5 py-4 border-b border-black/[0.08] flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[16px] font-semibold text-[#1d1d1f] truncate">
                  {evidenceProject.name} sources
                </p>
                <p className="text-[12px] text-[#6e6e73] mt-0.5">
                  Chats in project: {evidenceProjectState.projectChatCount}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => void loadProjectEvidence(evidenceProjectId)}
                  className="h-8 px-3 rounded-lg border border-black/[0.08] text-[12px] text-[#1d1d1f] hover:bg-[#f5f5f7] transition-colors disabled:opacity-50"
                  disabled={evidenceProjectState.status === "loading"}
                  title="Refresh source list"
                >
                  {evidenceProjectState.status === "loading" ? "Refreshing..." : "Refresh"}
                </button>
                <button
                  onClick={closeEvidenceModal}
                  className="h-8 w-8 rounded-lg border border-black/[0.08] text-[#6e6e73] hover:text-[#1d1d1f] hover:bg-[#f5f5f7] transition-colors inline-flex items-center justify-center"
                  title="Close"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-5 space-y-4">
              {evidenceProjectState.status === "loading" ? (
                <div className="inline-flex items-center gap-2 text-[13px] text-[#6e6e73]">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Collecting sources used in this project's chats...</span>
                </div>
              ) : null}

              {evidenceProjectState.status === "error" ? (
                <p className="text-[13px] text-[#d44848]">{evidenceProjectState.errorMessage}</p>
              ) : null}

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <section className="rounded-xl border border-black/[0.08] bg-[#fbfbfc] p-3">
                  <div className="flex items-center justify-between">
                    <div className="inline-flex items-center gap-1.5">
                      <FileText className="w-3.5 h-3.5 text-[#6e6e73]" />
                      <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-[#6e6e73]">
                        Documents
                      </p>
                    </div>
                    <span className="text-[12px] text-[#8d8d93]">
                      {evidenceProjectState.documents.length}
                    </span>
                  </div>
                  {evidenceProjectState.documents.length ? (
                    <div className="mt-2 max-h-[240px] overflow-y-auto space-y-1.5 pr-1">
                      {evidenceProjectState.documents.map((item) => (
                        <div
                          key={item.key}
                          className="group rounded-lg border border-black/[0.05] bg-white px-2.5 py-2 hover:border-black/[0.14] transition-colors"
                        >
                          <div className="flex items-center gap-2 w-full">
                            {editingEvidenceKey === item.key ? (
                              <>
                                <input
                                  value={editingEvidenceDraft}
                                  onChange={(event) => setEditingEvidenceDraft(event.target.value)}
                                  onKeyDown={(event) => {
                                    if (event.key === "Enter") {
                                      event.preventDefault();
                                      commitRenameEvidenceItem(item);
                                    }
                                    if (event.key === "Escape") {
                                      event.preventDefault();
                                      cancelRenameEvidenceItem();
                                    }
                                  }}
                                  className="flex-1 h-7 px-2 rounded-md border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] focus:outline-none focus:ring-2 focus:ring-black/10"
                                />
                                <button
                                  onClick={() => commitRenameEvidenceItem(item)}
                                  className="p-1 rounded-md text-[#1d1d1f] hover:bg-black/5"
                                  title="Save name"
                                >
                                  <Check className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={cancelRenameEvidenceItem}
                                  className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f]"
                                  title="Cancel rename"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </>
                            ) : (
                              <>
                                <div className="inline-flex items-center gap-1.5 min-w-0 flex-1">
                                  <FileText className="w-3.5 h-3.5 shrink-0 text-[#6e6e73]" />
                                  <p
                                    className="text-[12px] text-[#1d1d1f] truncate"
                                    title={getEvidenceDisplayLabel(item)}
                                  >
                                    {getEvidenceDisplayLabel(item)}
                                  </p>
                                </div>
                                <div className="ml-1 inline-flex items-center gap-1 opacity-0 pointer-events-none transition-opacity duration-150 group-hover:opacity-100 group-hover:pointer-events-auto group-focus-within:opacity-100 group-focus-within:pointer-events-auto">
                                  <button
                                    onClick={() => startRenameEvidenceItem(item)}
                                    className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f]"
                                    title="Rename source"
                                  >
                                    <PencilLine className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={() => void handleDeleteEvidenceItem(item)}
                                    disabled={
                                      Boolean(evidenceActionBusyByKey[item.key]) ||
                                      (item.fileIds.length === 0 &&
                                        !(item.type === "url" && String(item.href || item.label || "").trim()))
                                    }
                                    className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] disabled:opacity-45 disabled:cursor-not-allowed"
                                    title={
                                      item.fileIds.length === 0 &&
                                      !(item.type === "url" && String(item.href || item.label || "").trim())
                                        ? "Delete unavailable for this source"
                                        : "Delete source"
                                    }
                                  >
                                    {Boolean(evidenceActionBusyByKey[item.key]) ? (
                                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    ) : (
                                      <Trash2 className="w-3.5 h-3.5" />
                                    )}
                                  </button>
                                </div>
                              </>
                            )}
                          </div>
                          <p className="text-[11px] text-[#8d8d93]">
                            {item.usageCount <= 0 && item.chatCount <= 0
                              ? "available source"
                              : `used ${item.usageCount}x in ${item.chatCount} chat${item.chatCount === 1 ? "" : "s"}`}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-[12px] text-[#8d8d93]">No documents or uploads yet.</p>
                  )}
                </section>

                <section className="rounded-xl border border-black/[0.08] bg-[#fbfbfc] p-3">
                  <div className="flex items-center justify-between">
                    <div className="inline-flex items-center gap-1.5">
                      <Globe className="w-3.5 h-3.5 text-[#6e6e73]" />
                      <p className="text-[12px] font-semibold uppercase tracking-[0.06em] text-[#6e6e73]">
                        URLs
                      </p>
                    </div>
                    <span className="text-[12px] text-[#8d8d93]">
                      {evidenceProjectState.urls.length}
                    </span>
                  </div>
                  {evidenceProjectState.urls.length ? (
                    <div className="mt-2 max-h-[240px] overflow-y-auto space-y-1.5 pr-1">
                      {evidenceProjectState.urls.map((item) => (
                        <div
                          key={item.key}
                          className="group block rounded-lg border border-black/[0.05] bg-white px-2.5 py-2 hover:border-black/[0.14] transition-colors"
                          title={item.href || item.label}
                        >
                          <div className="flex items-center gap-2 w-full">
                            {editingEvidenceKey === item.key ? (
                              <>
                                <input
                                  value={editingEvidenceDraft}
                                  onChange={(event) => setEditingEvidenceDraft(event.target.value)}
                                  onKeyDown={(event) => {
                                    if (event.key === "Enter") {
                                      event.preventDefault();
                                      commitRenameEvidenceItem(item);
                                    }
                                    if (event.key === "Escape") {
                                      event.preventDefault();
                                      cancelRenameEvidenceItem();
                                    }
                                  }}
                                  className="flex-1 h-7 px-2 rounded-md border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] focus:outline-none focus:ring-2 focus:ring-black/10"
                                />
                                <button
                                  onClick={() => commitRenameEvidenceItem(item)}
                                  className="p-1 rounded-md text-[#1d1d1f] hover:bg-black/5"
                                  title="Save name"
                                >
                                  <Check className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={cancelRenameEvidenceItem}
                                  className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f]"
                                  title="Cancel rename"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              </>
                            ) : (
                              <>
                                <a
                                  href={item.href || "#"}
                                  target="_blank"
                                  rel="noreferrer noopener"
                                  className="inline-flex items-center gap-1.5 min-w-0 flex-1"
                                >
                                  <Link2 className="w-3.5 h-3.5 shrink-0 text-[#6e6e73]" />
                                  <p
                                    className="text-[12px] text-[#1d1d1f] truncate"
                                    title={getEvidenceDisplayLabel(item)}
                                  >
                                    {getEvidenceDisplayLabel(item)}
                                  </p>
                                </a>
                                <div className="ml-1 inline-flex items-center gap-1 opacity-0 pointer-events-none transition-opacity duration-150 group-hover:opacity-100 group-hover:pointer-events-auto group-focus-within:opacity-100 group-focus-within:pointer-events-auto">
                                  <button
                                    onClick={() => startRenameEvidenceItem(item)}
                                    className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f]"
                                    title="Rename source"
                                  >
                                    <PencilLine className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={() => void handleDeleteEvidenceItem(item)}
                                    disabled={
                                      Boolean(evidenceActionBusyByKey[item.key]) ||
                                      (item.fileIds.length === 0 &&
                                        !(item.type === "url" && String(item.href || item.label || "").trim()))
                                    }
                                    className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] disabled:opacity-45 disabled:cursor-not-allowed"
                                    title={
                                      item.fileIds.length === 0 &&
                                      !(item.type === "url" && String(item.href || item.label || "").trim())
                                        ? "Delete unavailable for this source"
                                        : "Delete source"
                                    }
                                  >
                                    {Boolean(evidenceActionBusyByKey[item.key]) ? (
                                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    ) : (
                                      <Trash2 className="w-3.5 h-3.5" />
                                    )}
                                  </button>
                                </div>
                              </>
                            )}
                          </div>
                          <p className="text-[11px] text-[#8d8d93]">
                            used {item.usageCount}x in {item.chatCount} chat
                            {item.chatCount === 1 ? "" : "s"}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-[12px] text-[#8d8d93]">No website sources used yet.</p>
                  )}
                </section>
              </div>

              <section className="rounded-xl border border-black/[0.08] bg-[#fbfbfc] p-3 space-y-2.5">
                <p className="text-[12px] font-semibold text-[#1d1d1f]">Upload more sources</p>
                <input
                  ref={(node) => {
                    fileInputByProjectRef.current[evidenceProjectId] = node;
                  }}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(event) => {
                    void handleProjectFileUpload(evidenceProjectId, event.target.files);
                    event.currentTarget.value = "";
                  }}
                />
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => fileInputByProjectRef.current[evidenceProjectId]?.click()}
                    disabled={evidenceProjectUploadBusy}
                    className="h-8 px-3 rounded-lg border border-black/[0.08] text-[12px] text-[#1d1d1f] hover:bg-white transition-colors disabled:opacity-50"
                  >
                    Upload files
                  </button>
                </div>
                <textarea
                  value={evidenceProjectUrlDraft}
                  onChange={(event) =>
                    setProjectUrlDraftById((prev) => ({
                      ...prev,
                      [evidenceProjectId]: event.target.value,
                    }))
                  }
                  rows={3}
                  placeholder="Paste one or more URLs"
                  className="w-full rounded-lg border border-black/[0.08] bg-white px-2.5 py-2 text-[12px] text-[#1d1d1f] placeholder:text-[#8d8d93] focus:outline-none focus:ring-2 focus:ring-black/10"
                />
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => void submitProjectUrls(evidenceProjectId)}
                    disabled={evidenceProjectUploadBusy || !evidenceProjectUrlDraft.trim()}
                    className="h-8 px-3 rounded-lg bg-[#1d1d1f] text-white text-[12px] hover:bg-[#343438] transition-colors disabled:opacity-50"
                  >
                    Index URLs
                  </button>
                </div>
                {evidenceProjectUploadStatus ? (
                  <p className="text-[12px] text-[#6e6e73]">{evidenceProjectUploadStatus}</p>
                ) : null}
                <p className="text-[11px] text-[#8d8d93]">
                  Rename updates the display label in your workspace.
                </p>
                <p className="text-[11px] text-[#8d8d93]">
                  Uploaded sources become available for future chats in this project.
                </p>
              </section>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
