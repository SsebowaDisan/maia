import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { getIngestionJob } from "../../../api/client";
import type { ChatAttachment, ChatTurn } from "../../types";
import { formatIngestionJobProgress, formatUploadProgress } from "./ingestionProgress";
import { buildWorkspaceModeOverride } from "./workspaceModeOverride";
import type { ChatMainProps, ComposerAttachment } from "./types";

const CHAT_MAX_FILE_SIZE_BYTES = 512 * 1024 * 1024;
const CHAT_MAX_TOTAL_BYTES = 1024 * 1024 * 1024;
const WEB_SEARCH_SETTING_OVERRIDES: Record<string, unknown> = {
  __deep_search_enabled: true,
  __research_web_only: true,
  __llm_only_keyword_generation: true,
  __llm_only_keyword_generation_strict: true,
  __research_depth_tier: "deep_research",
  __research_web_search_budget: 200,
  __research_max_query_variants: 12,
  __research_results_per_query: 20,
  __research_fused_top_k: 200,
  __research_min_unique_sources: 60,
  __research_max_live_inspections: 12,
  __deep_search_max_source_ids: 200,
};
type ComposerMode = "ask" | "company_agent" | "deep_search" | "web_search";
type UseChatMainInteractionsParams = Pick<
  ChatMainProps,
  | "accessMode"
  | "activityEvents"
  | "agentMode"
  | "chatTurns"
  | "citationMode"
  | "mindmapEnabled"
  | "mindmapMaxDepth"
  | "mindmapIncludeReasoning"
  | "mindmapMapType"
  | "isSending"
  | "onAccessModeChange"
  | "onAgentModeChange"
  | "onSendMessage"
  | "onUpdateUserTurn"
  | "onUploadFiles"
  | "onCreateFileIngestionJob"
  | "availableDocuments"
  | "availableGroups"
  | "availableProjects"
>;

function useChatMainInteractions({
  accessMode,
  activityEvents,
  agentMode,
  chatTurns,
  citationMode,
  mindmapEnabled,
  mindmapMaxDepth,
  mindmapIncludeReasoning,
  mindmapMapType,
  isSending,
  onAccessModeChange,
  onAgentModeChange,
  onSendMessage,
  onUpdateUserTurn,
  onUploadFiles,
  onCreateFileIngestionJob,
  availableDocuments = [],
  availableGroups = [],
  availableProjects = [],
}: UseChatMainInteractionsParams) {
  const [message, setMessage] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [attachments, setAttachments] = useState<ComposerAttachment[]>([]);
  const [agentControlsVisible, setAgentControlsVisible] = useState(false);
  const [deepSearchProfile, setDeepSearchProfile] = useState<"default" | "web_search">("default");
  const [messageActionStatus, setMessageActionStatus] = useState("");
  const [editingTurnIndex, setEditingTurnIndex] = useState<number | null>(null);
  const [editingText, setEditingText] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const statusTimerRef = useRef<number | null>(null);
  const lastClipboardEventRef = useRef<string>("");
  const attachmentsRef = useRef<ComposerAttachment[]>([]);

  const revokeAttachmentUrl = (attachment: ComposerAttachment) => {
    const url = String(attachment.localUrl || "");
    if (url.startsWith("blob:")) {
      URL.revokeObjectURL(url);
    }
  };

  const clearAttachments = () => {
    setAttachments((previous) => {
      previous.forEach(revokeAttachmentUrl);
      return [];
    });
  };

  const showActionStatus = (text: string) => {
    setMessageActionStatus(text);
    if (statusTimerRef.current) {
      window.clearTimeout(statusTimerRef.current);
    }
    statusTimerRef.current = window.setTimeout(() => {
      setMessageActionStatus("");
      statusTimerRef.current = null;
    }, 2500);
  };

  useEffect(
    () => () => {
      if (statusTimerRef.current) {
        window.clearTimeout(statusTimerRef.current);
      }
    },
    [],
  );

  const latestHighlightSnippets = useMemo(() => {
    const snippets: string[] = [];
    for (let index = activityEvents.length - 1; index >= 0; index -= 1) {
      const event = activityEvents[index];
      const copied = event.data?.["copied_snippets"];
      if (Array.isArray(copied)) {
        for (const row of copied) {
          const text = String(row || "").trim();
          if (text && !snippets.includes(text)) {
            snippets.push(text);
          }
          if (snippets.length >= 8) {
            return snippets;
          }
        }
      }
      const clipboardText =
        typeof event.data?.["clipboard_text"] === "string"
          ? event.data["clipboard_text"].trim()
          : "";
      if (clipboardText && !snippets.includes(clipboardText)) {
        snippets.push(clipboardText);
      }
      if (snippets.length >= 8) {
        return snippets;
      }
    }
    return snippets;
  }, [activityEvents]);

  const mapTurnAttachments = (turnAttachments?: ChatAttachment[]) =>
    (turnAttachments || []).map((attachment, idx) => ({
      id: `compose-${Date.now()}-${idx}-${attachment.name}`,
      name: attachment.name,
      status: "indexed" as const,
      fileId: attachment.fileId,
      kind: attachment.fileId ? ("file" as const) : undefined,
      entityId: attachment.fileId || undefined,
    }));

  const removeAttachment = (attachmentId: string) => {
    setAttachments((previous) => {
      const next: ComposerAttachment[] = [];
      previous.forEach((item) => {
        if (item.id === attachmentId) {
          revokeAttachmentUrl(item);
          return;
        }
        next.push(item);
      });
      return next;
    });
  };

  const createDocumentAttachment = (
    file: { id: string; name: string },
    fallbackIdPrefix = "doc",
  ): ComposerAttachment => ({
    id: `${fallbackIdPrefix}-${file.id}-${Date.now()}-${Math.random().toString(16).slice(2, 7)}`,
    name: file.name,
    status: "indexed",
    fileId: file.id,
    kind: "file",
    entityId: file.id,
  });

  const attachDocumentById = (fileId: string) => {
    const target = availableDocuments.find((item) => item.id === fileId);
    if (!target) {
      showActionStatus("Document not found.");
      return;
    }
    let added = false;
    setAttachments((previous) => {
      if (previous.some((item) => item.fileId && item.fileId === target.id)) {
        return previous;
      }
      added = true;
      return [...previous, createDocumentAttachment(target)];
    });
    if (!added) {
      showActionStatus(`"${target.name}" is already attached.`);
      return;
    }
    showActionStatus(`Attached "${target.name}".`);
  };

  const attachGroupById = (groupId: string) => {
    const group = availableGroups.find((item) => item.id === groupId);
    if (!group) {
      showActionStatus("Group not found.");
      return;
    }

    const docsById = new Map(availableDocuments.map((item) => [item.id, item]));
    const groupDocs = Array.from(new Set(group.file_ids || []))
      .map((fileId) => docsById.get(fileId))
      .filter((item): item is NonNullable<typeof item> => Boolean(item));
    if (!groupDocs.length) {
      showActionStatus(`"${group.name}" has no available documents.`);
      return;
    }

    const ATTACH_LIMIT = 40;
    const slicedDocs = groupDocs.slice(0, ATTACH_LIMIT);
    let addedCount = 0;
    setAttachments((previous) => {
      const existingFileIds = new Set(
        previous.map((item) => String(item.fileId || "").trim()).filter(Boolean),
      );
      const next = [...previous];
      for (const doc of slicedDocs) {
        if (existingFileIds.has(doc.id)) {
          continue;
        }
        next.push(createDocumentAttachment(doc, "group-doc"));
        existingFileIds.add(doc.id);
        addedCount += 1;
      }
      return next;
    });

    if (!addedCount) {
      showActionStatus(`All documents from "${group.name}" are already attached.`);
      return;
    }
    const remaining = groupDocs.length - slicedDocs.length;
    if (remaining > 0) {
      showActionStatus(
        `Attached ${addedCount} docs from "${group.name}" (limit ${ATTACH_LIMIT}, ${remaining} not added).`,
      );
      return;
    }
    showActionStatus(`Attached ${addedCount} docs from "${group.name}".`);
  };

  const attachProjectById = (projectId: string) => {
    const project = availableProjects.find((item) => item.id === projectId);
    if (!project) {
      showActionStatus("Project not found.");
      return;
    }
    const projectEntityId = `project:${project.id}`;
    let added = false;
    setAttachments((previous) => {
      if (
        previous.some(
          (item) => item.kind === "project" && String(item.entityId || "").trim() === projectEntityId,
        )
      ) {
        return previous;
      }
      added = true;
      return [
        ...previous,
        {
          id: `project-${project.id}-${Date.now()}`,
          name: `Project: ${project.name}`,
          status: "indexed",
          kind: "project",
          entityId: projectEntityId,
        },
      ];
    });
    if (!added) {
      showActionStatus(`"${project.name}" is already attached.`);
      return;
    }
    showActionStatus(`Attached project "${project.name}".`);
  };

  const submit = async () => {
    const payload = message.trim();
    if (!payload || isSending) {
      return;
    }
    const workspaceModeOverride = buildWorkspaceModeOverride();
    const modeSettingOverrides =
      agentMode === "deep_search" && deepSearchProfile === "web_search"
        ? { ...WEB_SEARCH_SETTING_OVERRIDES, ...workspaceModeOverride }
        : workspaceModeOverride;
    const turnAttachments: ChatAttachment[] = attachments
      .filter((item) => item.status !== "error")
      .map((item) => ({ name: item.name, fileId: item.fileId }));
    setMessage("");
    await onSendMessage(payload, turnAttachments, {
      citationMode,
      useMindmap: mindmapEnabled,
      mindmapSettings: {
        max_depth: mindmapMaxDepth,
        include_reasoning_map: mindmapIncludeReasoning,
        map_type: mindmapMapType,
      },
      settingOverrides: modeSettingOverrides,
      agentMode,
      accessMode,
    });
    clearAttachments();
  };

  const copyPlainText = async (text: string, label: string) => {
    const value = text.trim();
    if (!value) {
      showActionStatus(`Nothing to copy from ${label}.`);
      return false;
    }
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const fallback = document.createElement("textarea");
        fallback.value = value;
        fallback.style.position = "fixed";
        fallback.style.opacity = "0";
        document.body.appendChild(fallback);
        fallback.focus();
        fallback.select();
        document.execCommand("copy");
        document.body.removeChild(fallback);
      }
      showActionStatus(`${label} copied.`);
      return true;
    } catch {
      showActionStatus(`Unable to copy ${label.toLowerCase()}.`);
      return false;
    }
  };

  const beginInlineEdit = (turn: ChatTurn, turnIndex: number) => {
    setEditingTurnIndex(turnIndex);
    setEditingText(turn.user);
    showActionStatus("Editing message inline.");
  };

  const cancelInlineEdit = () => {
    setEditingTurnIndex(null);
    setEditingText("");
  };

  const saveInlineEdit = async () => {
    if (editingTurnIndex === null) {
      return;
    }
    if (isSending) {
      return;
    }
    const value = editingText.trim();
    if (!value) {
      showActionStatus("Message cannot be empty.");
      return;
    }
    const editedTurn = chatTurns[editingTurnIndex];
    onUpdateUserTurn(editingTurnIndex, value);
    setEditingTurnIndex(null);
    setEditingText("");
    showActionStatus("Message updated. Generating response...");
    const modeSettingOverrides =
      agentMode === "deep_search" && deepSearchProfile === "web_search"
        ? WEB_SEARCH_SETTING_OVERRIDES
        : undefined;
    await onSendMessage(value, editedTurn?.attachments, {
      citationMode,
      useMindmap: mindmapEnabled,
      mindmapSettings: {
        max_depth: mindmapMaxDepth,
        include_reasoning_map: mindmapIncludeReasoning,
        map_type: mindmapMapType,
      },
      settingOverrides: modeSettingOverrides,
      agentMode,
      accessMode,
    });
  };

  const retryTurn = (turn: ChatTurn) => {
    setMessage(turn.user);
    setAttachments((previous) => {
      previous.forEach(revokeAttachmentUrl);
      return mapTurnAttachments(turn.attachments);
    });
    showActionStatus("Retry prompt loaded into the command bar.");
  };

  const enableAgentMode = () => {
    setAgentControlsVisible(true);
    setDeepSearchProfile("default");
    onAgentModeChange("company_agent");
    showActionStatus("Agent mode enabled.");
  };

  const enableAskMode = () => {
    setAgentControlsVisible(false);
    setDeepSearchProfile("default");
    onAgentModeChange("ask");
    showActionStatus("Standard mode enabled.");
  };

  const enableDeepResearch = () => {
    setAgentControlsVisible(false);
    setDeepSearchProfile("default");
    onAgentModeChange("deep_search");
    onAccessModeChange("restricted");
    showActionStatus("Deep search mode enabled.");
  };

  const enableWebSearch = () => {
    setAgentControlsVisible(false);
    setDeepSearchProfile("web_search");
    onAgentModeChange("deep_search");
    onAccessModeChange("restricted");
    showActionStatus("Web search mode enabled (target: 200 online sources).");
  };

  const composerMode: ComposerMode =
    agentMode === "deep_search" && deepSearchProfile === "web_search"
      ? "web_search"
      : agentMode;

  const pasteHighlightsToComposer = () => {
    if (!latestHighlightSnippets.length) {
      showActionStatus("No copied highlights available yet.");
      return;
    }
    const block = [
      "Copied highlights:",
      ...latestHighlightSnippets.slice(0, 6).map((snippet) => `- ${snippet}`),
    ].join("\n");
    setMessage((previous) => {
      const current = previous.trim();
      return current ? `${current}\n\n${block}` : block;
    });
    showActionStatus("Highlights pasted into the command bar.");
  };

  const quoteAssistant = (turn: ChatTurn) => {
    const quoteSource = turn.assistant.replace(/\s+/g, " ").trim();
    if (!quoteSource) {
      return;
    }
    const quoted = `> ${quoteSource.slice(0, 350)}`;
    setMessage((previous) => {
      const base = previous.trim();
      return base ? `${base}\n${quoted}` : quoted;
    });
    showActionStatus("Quoted answer loaded into the command bar.");
  };

  const onFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = event.target.files;
    if (!selectedFiles || !selectedFiles.length) {
      return;
    }
    const selectedRows = Array.from(selectedFiles);
    const overSizeFile = selectedRows.find((file) => file.size > CHAT_MAX_FILE_SIZE_BYTES);
    if (overSizeFile) {
      showActionStatus(
        `File "${overSizeFile.name}" is larger than 512 MB and cannot be uploaded.`,
      );
      event.target.value = "";
      return;
    }
    const totalBytes = selectedRows.reduce((total, file) => total + file.size, 0);
    if (totalBytes > CHAT_MAX_TOTAL_BYTES) {
      showActionStatus("Selected files exceed the 1 GB total upload limit.");
      event.target.value = "";
      return;
    }
    const pending = selectedRows.map((file, idx) => ({
      id: `${Date.now()}-${idx}-${file.name}`,
      name: file.name,
      status: "uploading" as const,
      message: "Uploading 0%",
      localUrl: URL.createObjectURL(file),
      mimeType: String(file.type || ""),
      kind: "file" as const,
    }));
    setAttachments((prev) => [...prev, ...pending]);
    const updatePendingMessage = (text: string) => {
      setAttachments((prev) =>
        prev.map((attachment) =>
          pending.some((item) => item.id === attachment.id)
            ? {
                ...attachment,
                status: "uploading",
                message: text,
              }
            : attachment,
        ),
      );
    };

    const applyUploadResult = (result: {
      items: { status: string; file_id?: string; message?: string }[];
      errors: string[];
      file_ids: string[];
    }) => {
      const failedMessages: string[] = [];
      let successCursor = 0;
      setAttachments((prev) =>
        prev.map((attachment) => {
          const pendingIdx = pending.findIndex((item) => item.id === attachment.id);
          if (pendingIdx === -1) {
            return attachment;
          }
          const item = result.items[pendingIdx];
          if (item?.status === "success") {
            const mappedFileId = item.file_id || result.file_ids[successCursor] || undefined;
            successCursor += 1;
            return {
              ...attachment,
              status: "indexed",
              message: undefined,
              fileId: mappedFileId,
              entityId: mappedFileId,
              kind: "file" as const,
            };
          }
          const failureMessage = item?.message || result.errors[0] || "Upload failed.";
          failedMessages.push(failureMessage);
          return {
            ...attachment,
            status: "error",
            message: failureMessage,
          };
        }),
      );
      if (failedMessages.length > 0) {
        const reason = String(failedMessages[0] || "Upload failed.").trim();
        const compact = reason.length > 120 ? `${reason.slice(0, 117)}...` : reason;
        showActionStatus(`Upload failed: ${compact}`);
      } else {
        showActionStatus(
          `Uploaded ${pending.length} file${pending.length === 1 ? "" : "s"} successfully.`,
        );
      }
    };

    const waitForIngestionJob = async (jobId: string) => {
      const startedAt = Date.now();
      const timeoutMs = 20 * 60 * 1000;
      while (true) {
        const job = await getIngestionJob(jobId);
        const status = String(job.status || "").toLowerCase();
        if (status === "completed") {
          return job;
        }
        if (status === "failed" || status === "canceled") {
          const reason = job.errors[0] || job.message || `Ingestion job ${job.status}`;
          throw new Error(reason);
        }
        updatePendingMessage(formatIngestionJobProgress(job));

        if (Date.now() - startedAt > timeoutMs) {
          throw new Error("Ingestion timed out while indexing attachments.");
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
      }
    };
    setIsUploading(true);
    try {
      const shouldQueueAsyncJob = Boolean(onCreateFileIngestionJob);

      if (shouldQueueAsyncJob && onCreateFileIngestionJob) {
        updatePendingMessage("Uploading to server 0%");
        const queued = await onCreateFileIngestionJob(selectedFiles, {
          reindex: true,
          scope: "chat_temp",
          onUploadProgress: (loadedBytes, totalBytesBytes) => {
            updatePendingMessage(
              formatUploadProgress(loadedBytes, totalBytesBytes, "creating indexing job"),
            );
          },
        });
        updatePendingMessage(formatIngestionJobProgress(queued));
        showActionStatus(
          `Attachment job queued: ${queued.id.slice(0, 8)} (${queued.total_items} file${queued.total_items === 1 ? "" : "s"}).`,
        );
        const finalJob = await waitForIngestionJob(queued.id);
        applyUploadResult({
          items: finalJob.items,
          errors: finalJob.errors,
          file_ids: finalJob.file_ids,
        });
      } else {
        const response = await onUploadFiles(selectedFiles, {
          onUploadProgress: (loadedBytes, totalBytesBytes) => {
            updatePendingMessage(
              formatUploadProgress(
                loadedBytes,
                totalBytesBytes,
                "server indexing in progress (no live server metrics)",
              ),
            );
          },
        });
        applyUploadResult({
          items: response.items,
          errors: response.errors,
          file_ids: response.file_ids,
        });
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : String(error || "Upload failed.");
      const compact = errorMessage.length > 120 ? `${errorMessage.slice(0, 117)}...` : errorMessage;
      setAttachments((prev) =>
        prev.map((attachment) =>
          pending.some((item) => item.id === attachment.id)
            ? {
                ...attachment,
                status: "error",
                message: errorMessage,
              }
            : attachment,
        ),
      );
      showActionStatus(`Upload failed: ${compact}`);
    } finally {
      setIsUploading(false);
      event.target.value = "";
    }
  };

  useEffect(() => {
    if (!activityEvents.length) {
      return;
    }
    const latest = activityEvents[activityEvents.length - 1];
    if (!latest?.event_id || latest.event_id === lastClipboardEventRef.current) {
      return;
    }
    if (
      latest.event_type === "highlights_detected" ||
      latest.event_type === "doc_copy_clipboard" ||
      latest.event_type === "browser_copy_selection"
    ) {
      lastClipboardEventRef.current = latest.event_id;
      showActionStatus("Highlights copied. Use + -> Paste highlights.");
    }
  }, [activityEvents]);

  useEffect(() => {
    attachmentsRef.current = attachments;
  }, [attachments]);

  useEffect(
    () => () => {
      attachmentsRef.current.forEach(revokeAttachmentUrl);
    },
    [],
  );

  return {
    agentControlsVisible,
    attachDocumentById,
    attachGroupById,
    attachProjectById,
    attachments,
    beginInlineEdit,
    cancelInlineEdit,
    copyPlainText,
    editingText,
    editingTurnIndex,
    enableAskMode,
    enableAgentMode,
    enableWebSearch,
    enableDeepResearch,
    fileInputRef,
    isUploading,
    latestHighlightSnippets,
    message,
    messageActionStatus,
    composerMode,
    onFileChange,
    pasteHighlightsToComposer,
    quoteAssistant,
    removeAttachment,
    saveInlineEdit,
    clearAttachments,
    setAttachments,
    setEditingText,
    setMessage,
    showActionStatus,
    submit,
    retryTurn,
  };
}

export { useChatMainInteractions };
