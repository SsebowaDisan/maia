import { useCallback, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import {
  createConversation,
  getConversation,
  listConversations,
  listFiles,
  sendChat,
  uploadFiles,
  uploadUrls,
  type ConversationSummary,
  type UploadResponse,
} from "../api/client";
import { ChatSidebar } from "./components/ChatSidebar";
import { ChatMain } from "./components/ChatMain";
import { InfoPanel } from "./components/InfoPanel";
import { TopNav } from "./components/TopNav";
import { FilesView } from "./components/FilesView";
import { ResourcesView } from "./components/ResourcesView";
import { SettingsView } from "./components/SettingsView";
import { HelpView } from "./components/HelpView";
import type { ChatAttachment, ChatTurn, CitationFocus } from "./types";

const LEFT_PANEL_MIN = 240;
const LEFT_PANEL_MAX = 520;
const RIGHT_PANEL_MIN = 280;
const RIGHT_PANEL_MAX = 560;
const CENTER_PANEL_MIN = 460;

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function readStoredWidth(key: string, fallback: number) {
  if (typeof window === "undefined") {
    return fallback;
  }
  const value = Number(window.localStorage.getItem(key) || "");
  return Number.isFinite(value) ? value : fallback;
}

type ResizeSide = "left" | "right" | null;

function ResizeHandle({
  side,
  active,
  onMouseDown,
}: {
  side: "left" | "right";
  active: boolean;
  onMouseDown: (event: ReactMouseEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={side === "left" ? "Resize left panel" : "Resize right panel"}
      onMouseDown={onMouseDown}
      className={`group relative w-2 shrink-0 cursor-col-resize transition-colors ${
        active ? "bg-[#0b5ad9]/15" : "hover:bg-[#0b5ad9]/10"
      }`}
    >
      <div className="absolute left-1/2 top-1/2 h-12 w-[2px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/10 group-hover:bg-[#0b5ad9]/60" />
    </div>
  );
}

export default function App() {
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const [activeTab, setActiveTab] = useState("Chat");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isInfoPanelOpen, setIsInfoPanelOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(() =>
    readStoredWidth("maia.sidebar-width", 300),
  );
  const [infoPanelWidth, setInfoPanelWidth] = useState(() =>
    readStoredWidth("maia.info-width", 340),
  );
  const [resizeSide, setResizeSide] = useState<ResizeSide>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(
    null,
  );
  const [chatTurns, setChatTurns] = useState<ChatTurn[]>([]);
  const [selectedTurnIndex, setSelectedTurnIndex] = useState<number | null>(null);
  const [infoText, setInfoText] = useState("");
  const [uploadStatus, setUploadStatus] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [fileCount, setFileCount] = useState(0);
  const [defaultIndexId, setDefaultIndexId] = useState<number | null>(null);
  const [citationMode, setCitationMode] = useState("inline");
  const [mindmapEnabled, setMindmapEnabled] = useState(true);
  const [citationFocus, setCitationFocus] = useState<CitationFocus | null>(null);

  const refreshConversations = useCallback(async () => {
    const items = await listConversations();
    setConversations(items);
  }, []);

  const refreshFileCount = useCallback(async () => {
    const filesPayload = await listFiles();
    setFileCount(filesPayload.files.length);
    setDefaultIndexId(filesPayload.index_id);
  }, []);

  useEffect(() => {
    const load = async () => {
      try {
        await Promise.all([refreshConversations(), refreshFileCount()]);
      } catch {
        // Keep UI available even if backend is not ready.
      }
    };
    void load();
  }, [refreshConversations, refreshFileCount]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem("maia.sidebar-width", String(Math.round(sidebarWidth)));
  }, [sidebarWidth]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem("maia.info-width", String(Math.round(infoPanelWidth)));
  }, [infoPanelWidth]);

  useEffect(() => {
    const layout = layoutRef.current;
    if (!layout) {
      return;
    }
    const bounds = layout.getBoundingClientRect();
    const availableWidth = bounds.width;
    const leftMax = Math.max(
      LEFT_PANEL_MIN,
      availableWidth - CENTER_PANEL_MIN - (isInfoPanelOpen ? infoPanelWidth : 0),
    );
    const rightMax = Math.max(
      RIGHT_PANEL_MIN,
      availableWidth - CENTER_PANEL_MIN - (isSidebarCollapsed ? 64 : sidebarWidth),
    );
    const nextLeft = clamp(sidebarWidth, LEFT_PANEL_MIN, Math.min(LEFT_PANEL_MAX, leftMax));
    const nextRight = clamp(infoPanelWidth, RIGHT_PANEL_MIN, Math.min(RIGHT_PANEL_MAX, rightMax));
    if (nextLeft !== sidebarWidth) {
      setSidebarWidth(nextLeft);
    }
    if (nextRight !== infoPanelWidth) {
      setInfoPanelWidth(nextRight);
    }
  }, [isInfoPanelOpen, isSidebarCollapsed, sidebarWidth, infoPanelWidth]);

  useEffect(() => {
    if (!resizeSide) {
      return;
    }

    const onMove = (event: MouseEvent) => {
      const layout = layoutRef.current;
      if (!layout) {
        return;
      }
      const bounds = layout.getBoundingClientRect();
      const availableWidth = bounds.width;
      if (resizeSide === "left" && !isSidebarCollapsed) {
        const maxLeft = Math.max(
          LEFT_PANEL_MIN,
          availableWidth - CENTER_PANEL_MIN - (isInfoPanelOpen ? infoPanelWidth : 0),
        );
        const proposed = event.clientX - bounds.left;
        setSidebarWidth(clamp(proposed, LEFT_PANEL_MIN, Math.min(LEFT_PANEL_MAX, maxLeft)));
      }
      if (resizeSide === "right" && isInfoPanelOpen) {
        const maxRight = Math.max(
          RIGHT_PANEL_MIN,
          availableWidth - CENTER_PANEL_MIN - (isSidebarCollapsed ? 64 : sidebarWidth),
        );
        const proposed = bounds.right - event.clientX;
        setInfoPanelWidth(clamp(proposed, RIGHT_PANEL_MIN, Math.min(RIGHT_PANEL_MAX, maxRight)));
      }
    };

    const onStop = () => setResizeSide(null);
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onStop);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onStop);
    };
  }, [resizeSide, isInfoPanelOpen, isSidebarCollapsed, infoPanelWidth, sidebarWidth]);

  const handleSelectConversation = async (conversationId: string) => {
    setSelectedConversationId(conversationId);
    const detail = await getConversation(conversationId);
    const messages = detail.data_source?.messages || [];
    const retrievalMessages = detail.data_source?.retrieval_messages || [];
    const turns = messages.map((entry, index) => ({
      user: entry[0] || "",
      assistant: entry[1] || "",
      info: retrievalMessages[index] || "",
    }));
    setChatTurns(turns);
    if (turns.length > 0) {
      const lastIdx = turns.length - 1;
      setSelectedTurnIndex(lastIdx);
      setInfoText(turns[lastIdx].info || "");
      return;
    }
    setSelectedTurnIndex(null);
    setInfoText("");
  };

  const handleCreateConversation = async () => {
    const created = await createConversation();
    setSelectedConversationId(created.id);
    setChatTurns([]);
    setSelectedTurnIndex(null);
    setInfoText("");
    await refreshConversations();
  };

  const handleSendMessage = async (
    message: string,
    attachments?: ChatAttachment[],
    options?: {
      citationMode?: string;
      useMindmap?: boolean;
    },
  ) => {
    if (!message.trim()) {
      return;
    }

    const attachedFileIds = (attachments || [])
      .map((item) => item.fileId)
      .filter((item): item is string => Boolean(item));
    const indexSelection =
      attachedFileIds.length > 0 && defaultIndexId !== null
        ? {
            [String(defaultIndexId)]: {
              mode: "select" as const,
              file_ids: attachedFileIds,
            },
          }
        : undefined;

    const pendingTurnIndex = chatTurns.length;
    setIsSending(true);
    setInfoText("");
    setSelectedTurnIndex(pendingTurnIndex);
    setChatTurns((prev) => [
      ...prev,
      {
        user: message,
        assistant: "Thinking ...",
        attachments: attachments && attachments.length > 0 ? attachments : undefined,
        info: "",
      },
    ]);

    try {
      const response = await sendChat(message, selectedConversationId, {
        indexSelection,
        citation: options?.citationMode ?? citationMode,
        useMindmap: options?.useMindmap ?? mindmapEnabled,
      });
      setSelectedConversationId(response.conversation_id);
      setInfoText(response.info || "");
      setChatTurns((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = {
          ...(last || {}),
          user: message,
          assistant: response.answer || "",
          info: response.info || "",
        };
        return next;
      });
      setSelectedTurnIndex(pendingTurnIndex);
      await refreshConversations();
    } catch (error) {
      setChatTurns((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        next[next.length - 1] = {
          ...(last || {}),
          user: message,
          assistant: `Error: ${String(error)}`,
          info: "",
        };
        return next;
      });
    } finally {
      setIsSending(false);
    }
  };

  const handleUploadFiles = async (files: FileList): Promise<UploadResponse> => {
    if (!files.length) {
      throw new Error("No files selected.");
    }

    setUploadStatus("Uploading files...");
    try {
      const response = await uploadFiles(files);
      const successCount = response.items.filter((item) => item.status === "success").length;
      if (response.errors.length > 0) {
        setUploadStatus(`Upload issue: ${response.errors[0]}`);
      } else {
        setUploadStatus(`Indexed ${successCount} file(s).`);
      }
      await refreshFileCount();
      return response;
    } catch (error) {
      setUploadStatus(`Upload failed: ${String(error)}`);
      throw error;
    }
  };

  const handleUploadUrls = async (urlText: string) => {
    if (!urlText.trim()) {
      return;
    }

    setUploadStatus("Indexing URLs...");
    try {
      const response = await uploadUrls(urlText);
      const successCount = response.items.filter((item) => item.status === "success").length;
      if (response.errors.length > 0) {
        setUploadStatus(`URL issue: ${response.errors[0]}`);
      } else {
        setUploadStatus(`Indexed ${successCount} URL source(s).`);
      }
      await refreshFileCount();
    } catch (error) {
      setUploadStatus(`URL indexing failed: ${String(error)}`);
    }
  };

  return (
    <div className="size-full flex flex-col bg-[#f5f5f7] overflow-hidden">
      <TopNav activeTab={activeTab} onTabChange={setActiveTab} />
      <div ref={layoutRef} className="flex-1 min-h-0 flex overflow-hidden">
        {activeTab === "Chat" ? (
          <>
            <ChatSidebar
              isCollapsed={isSidebarCollapsed}
              width={sidebarWidth}
              onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
              conversations={conversations}
              selectedConversationId={selectedConversationId}
              onSelectConversation={handleSelectConversation}
              onNewConversation={handleCreateConversation}
              onUploadFiles={handleUploadFiles}
              onUploadUrls={handleUploadUrls}
              uploadStatus={uploadStatus}
            />

            {!isSidebarCollapsed ? (
              <ResizeHandle
                side="left"
                active={resizeSide === "left"}
                onMouseDown={(event) => {
                  event.preventDefault();
                  setResizeSide("left");
                }}
              />
            ) : null}

            <ChatMain
              onToggleInfoPanel={() => setIsInfoPanelOpen(!isInfoPanelOpen)}
              isInfoPanelOpen={isInfoPanelOpen}
              chatTurns={chatTurns}
              selectedTurnIndex={selectedTurnIndex}
              onSelectTurn={(turnIndex) => {
                setSelectedTurnIndex(turnIndex);
                setInfoText(chatTurns[turnIndex]?.info || "");
              }}
              onSendMessage={handleSendMessage}
              onUploadFiles={handleUploadFiles}
              isSending={isSending}
              citationMode={citationMode}
              onCitationModeChange={setCitationMode}
              mindmapEnabled={mindmapEnabled}
              onMindmapEnabledChange={setMindmapEnabled}
              onCitationClick={(citation) => {
                setCitationFocus(citation);
                setActiveTab("Chat");
                setIsInfoPanelOpen(true);
              }}
            />

            {isInfoPanelOpen ? (
              <ResizeHandle
                side="right"
                active={resizeSide === "right"}
                onMouseDown={(event) => {
                  event.preventDefault();
                  setResizeSide("right");
                }}
              />
            ) : null}

            {isInfoPanelOpen ? (
              <InfoPanel
                width={infoPanelWidth}
                messageCount={chatTurns.length}
                sourceCount={fileCount}
                infoText={infoText}
                answerText={
                  selectedTurnIndex !== null ? chatTurns[selectedTurnIndex]?.assistant || "" : ""
                }
                questionText={
                  selectedTurnIndex !== null ? chatTurns[selectedTurnIndex]?.user || "" : ""
                }
                citationFocus={citationFocus}
                indexId={defaultIndexId}
                onClearCitationFocus={() => setCitationFocus(null)}
              />
            ) : null}
          </>
        ) : activeTab === "Files" ? (
          <FilesView citationFocus={null} indexId={defaultIndexId} />
        ) : activeTab === "Resources" ? (
          <ResourcesView />
        ) : activeTab === "Settings" ? (
          <SettingsView />
        ) : activeTab === "Help" ? (
          <HelpView />
        ) : (
          <div className="flex-1 flex items-center justify-center bg-white">
            <p className="text-[15px] text-[#86868b]">{activeTab} content coming soon...</p>
          </div>
        )}
      </div>
    </div>
  );
}
