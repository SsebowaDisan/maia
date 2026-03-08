import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import type { ChatTurn } from "../../types";
import { buildWorkspaceModeOverride } from "./workspaceModeOverride";
import type { ChatMainProps, ComposerAttachment } from "./types";
import {
  attachDocumentById as attachDocumentByIdAction,
  attachGroupById as attachGroupByIdAction,
  attachProjectById as attachProjectByIdAction,
  mapTurnAttachments,
} from "./interactions/attachmentActions";
import { ComposerMode, WEB_SEARCH_SETTING_OVERRIDES } from "./interactions/constants";
import { handleComposerFileChange } from "./interactions/fileUpload";

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

  const attachDocumentById = (fileId: string) => {
    attachDocumentByIdAction({
      fileId,
      availableDocuments,
      setAttachments,
      showActionStatus,
    });
  };

  const attachGroupById = (groupId: string) => {
    attachGroupByIdAction({
      groupId,
      availableGroups,
      availableDocuments,
      setAttachments,
      showActionStatus,
    });
  };

  const attachProjectById = (projectId: string) => {
    attachProjectByIdAction({
      projectId,
      availableProjects,
      setAttachments,
      showActionStatus,
    });
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
    const turnAttachments = attachments
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
    if (editingTurnIndex === null || isSending) {
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
    agentMode === "deep_search" && deepSearchProfile === "web_search" ? "web_search" : agentMode;

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
    await handleComposerFileChange({
      event,
      onCreateFileIngestionJob,
      onUploadFiles,
      setAttachments,
      setIsUploading,
      showActionStatus,
    });
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
    clearAttachments,
    composerMode,
    copyPlainText,
    editingText,
    editingTurnIndex,
    enableAskMode,
    enableAgentMode,
    enableDeepResearch,
    enableWebSearch,
    fileInputRef,
    isUploading,
    latestHighlightSnippets,
    message,
    messageActionStatus,
    onFileChange,
    pasteHighlightsToComposer,
    quoteAssistant,
    removeAttachment,
    retryTurn,
    saveInlineEdit,
    setAttachments,
    setEditingText,
    setMessage,
    showActionStatus,
    submit,
  };
}

export { useChatMainInteractions };
