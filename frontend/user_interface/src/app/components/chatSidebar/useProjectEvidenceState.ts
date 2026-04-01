import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  getConversation,
  listFiles,
  type ConversationSummary,
  type FileRecord,
} from "../../../api/client";
import { buildConversationTurns } from "../../appShell/eventHelpers";
import {
  EMPTY_PROJECT_EVIDENCE,
  PROJECT_SOURCE_BINDINGS_STORAGE_KEY,
  SOURCE_ALIAS_STORAGE_KEY,
  addFromFileRecord,
  collectFromAttachments,
  collectFromInfoEvidence,
  collectFromProjectBindings,
  collectFromSelectedPayload,
  collectFromSourceUsage,
  collectFromSourcesUsed,
  normalizeSourceUrl,
  toProjectEvidenceItems,
  type ProjectEvidenceItem,
  type ProjectEvidenceState,
  type ProjectSourceBinding,
} from "./projectEvidenceHelpers";
import { useProjectEvidenceUploads } from "./useProjectEvidenceUploads";

type SidebarProject = {
  id: string;
  name: string;
};

type UseProjectEvidenceStateArgs = {
  allConversations: ConversationSummary[];
  conversationProjects: Record<string, string>;
  fallbackProjectId: string;
  projects: SidebarProject[];
  onSelectProject: (projectId: string) => void;
};

export function useProjectEvidenceState({
  allConversations,
  conversationProjects,
  fallbackProjectId,
  projects,
  onSelectProject,
}: UseProjectEvidenceStateArgs) {
  const [openProjectEvidenceId, setOpenProjectEvidenceId] = useState<string | null>(null);
  const [collapsedProjectsById, setCollapsedProjectsById] = useState<Record<string, boolean>>({});
  const [projectEvidenceById, setProjectEvidenceById] = useState<
    Record<string, ProjectEvidenceState>
  >({});
  const [projectUrlDraftById, setProjectUrlDraftById] = useState<Record<string, string>>({});
  const [projectUploadStatusById, setProjectUploadStatusById] = useState<Record<string, string>>({});
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
      const parsed = JSON.parse(raw) as Record<string, { fileIds?: unknown; urls?: unknown }>;
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
  const [evidenceActionBusyByKey, setEvidenceActionBusyByKey] = useState<Record<string, boolean>>({});

  const projectEvidenceRequestRef = useRef(0);
  const fileInputByProjectRef = useRef<Record<string, HTMLInputElement | null>>({});

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
            ...((payload.urls || []).map((item) => normalizeSourceUrl(String(item || ""))).filter(Boolean)),
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
        (conversation) => (conversationProjects[conversation.id] || fallbackProjectId) === projectId,
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

      const documents = new Map<string, {
        key: string;
        label: string;
        href?: string;
        fileIds: Set<string>;
        usageCount: number;
        conversationIds: Set<string>;
      }>();
      const urls = new Map<string, {
        key: string;
        label: string;
        href?: string;
        fileIds: Set<string>;
        usageCount: number;
        conversationIds: Set<string>;
      }>();

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
              collectFromAttachments(turn.attachments || [], conversation.id, documents);
              collectFromSourceUsage(turn.sourceUsage || [], conversation.id, documents, urls);
              collectFromSourcesUsed(turn.sourcesUsed || [], conversation.id, documents, urls);
              collectFromInfoEvidence(turn.info || "", conversation.id, documents, urls);
            }
          }),
        );
        collectFromProjectBindings(
          projectSourceBindings[projectId] || { fileIds: [], urls: [] },
          filesById,
          documents,
          urls,
        );
        if (projectConversations.length > 0 && documents.size === 0 && urls.size === 0) {
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

  const { handleProjectFileUpload, submitProjectUrls } = useProjectEvidenceUploads({
    appendProjectSourceBindings,
    loadProjectEvidence,
    setProjectUploadBusy,
    setProjectUploadStatus,
    projectUrlDraftById,
    setProjectUrlDraftById,
  });

  const closeEvidenceModal = useCallback(() => {
    setOpenProjectEvidenceId(null);
    setEditingEvidenceKey(null);
    setEditingEvidenceDraft("");
  }, []);

  const handleProjectClick = useCallback(
    (projectId: string) => {
      onSelectProject(projectId);
      setCollapsedProjectsById((prev) => {
        if (!prev[projectId]) {
          return prev;
        }
        return {
          ...prev,
          [projectId]: false,
        };
      });
    },
    [onSelectProject],
  );

  const handleProjectDoubleClick = useCallback((projectId: string) => {
    setCollapsedProjectsById((prev) => ({
      ...prev,
      [projectId]: !Boolean(prev[projectId]),
    }));
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
  const evidenceProjectUrlDraft = evidenceProjectId ? String(projectUrlDraftById[evidenceProjectId] || "") : "";

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

  return {
    openProjectEvidenceId,
    collapsedProjectsById,
    projectSourceBindings,
    sourceAliases,
    editingEvidenceKey,
    editingEvidenceDraft,
    evidenceActionBusyByKey,
    evidenceProject,
    evidenceProjectId,
    evidenceProjectState,
    evidenceProjectUploadBusy,
    evidenceProjectUploadStatus,
    evidenceProjectUrlDraft,
    fileInputByProjectRef,
    setProjectSourceBindings,
    setSourceAliases,
    setEvidenceActionBusyByKey,
    setProjectUploadStatus,
    setProjectUrlDraftById,
    setEditingEvidenceDraft,
    loadProjectEvidence,
    toggleProjectEvidenceCard,
    handleProjectFileUpload,
    submitProjectUrls,
    closeEvidenceModal,
    handleProjectClick,
    handleProjectDoubleClick,
    getEvidenceDisplayLabel,
    startRenameEvidenceItem,
    cancelRenameEvidenceItem,
    commitRenameEvidenceItem,
  };
}
