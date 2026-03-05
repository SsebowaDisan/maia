import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { ChatMain } from "../components/ChatMain";
import { ChatSidebar } from "../components/ChatSidebar";
import { FilesView } from "../components/FilesView";
import { HelpView } from "../components/HelpView";
import { InfoPanel } from "../components/InfoPanel";
import { ResourcesView } from "../components/ResourcesView";
import { SettingsView } from "../components/SettingsView";
import { TopNav } from "../components/TopNav";
import { getSharedMindmap } from "../../api/client";
import {
  clearCitationDeepLinkInUrl,
  readCitationDeepLinkFromUrl,
} from "../utils/citationDeepLink";
import {
  clearMindmapShareInUrl,
  readMindmapShareFromUrl,
} from "../utils/mindmapDeepLink";
import { getMindmapPayload } from "../components/infoPanelDerived";
import { ResizeHandle } from "./ResizeHandle";
import { useConversationChat } from "./useConversationChat";
import { useFileLibrary } from "./useFileLibrary";
import { useLayoutState } from "./useLayoutState";
import { useProjectState } from "./useProjectState";

type WorkspaceModalTab = "Files" | "Resources" | "Settings" | "Help";

function hasHttpUrl(value: unknown): boolean {
  const text = String(value || "").trim();
  return /^https?:\/\//i.test(text);
}

function webSummaryHasUrl(value: unknown): boolean {
  if (!value || typeof value !== "object") {
    return false;
  }
  const summary = value as {
    evidence?: {
      top_sources?: Array<{ url?: unknown }>;
      items?: Array<{ url?: unknown; evidence?: Array<{ url?: unknown }> }>;
    };
  };
  const topSources = Array.isArray(summary.evidence?.top_sources) ? summary.evidence?.top_sources : [];
  for (const row of topSources) {
    if (hasHttpUrl(row?.url)) {
      return true;
    }
  }
  const items = Array.isArray(summary.evidence?.items) ? summary.evidence?.items : [];
  for (const item of items) {
    if (hasHttpUrl(item?.url)) {
      return true;
    }
    const nested = Array.isArray(item?.evidence) ? item.evidence : [];
    for (const entry of nested) {
      if (hasHttpUrl(entry?.url)) {
        return true;
      }
    }
  }
  return false;
}

export default function App() {
  const deepLinkHandledRef = useRef(false);
  const mindmapLinkHandledRef = useRef(false);
  const lastAutoOpenCitationKeyRef = useRef("");
  const [sharedMindmap, setSharedMindmap] = useState<Record<string, unknown> | null>(null);
  const [workspaceModalTab, setWorkspaceModalTab] = useState<WorkspaceModalTab | null>(null);
  const layout = useLayoutState();
  const projectState = useProjectState();
  const fileLibrary = useFileLibrary();
  const chatState = useConversationChat({
    projects: projectState.projects,
    selectedProjectId: projectState.selectedProjectId,
    setSelectedProjectId: projectState.setSelectedProjectId,
    conversationProjects: projectState.conversationProjects,
    setConversationProjects: projectState.setConversationProjects,
    conversationModes: projectState.conversationModes,
    setConversationModes: projectState.setConversationModes,
    defaultIndexId: fileLibrary.defaultIndexId,
  });

  useEffect(() => {
    const load = async () => {
      try {
        await Promise.all([
          chatState.refreshConversations(),
          fileLibrary.refreshFileCount(),
          fileLibrary.refreshIngestionJobs(),
        ]);
      } catch {
        // Keep UI available even if backend is not ready.
      }
    };
    void load();
  }, [
    chatState.refreshConversations,
    fileLibrary.refreshFileCount,
    fileLibrary.refreshIngestionJobs,
  ]);

  useEffect(() => {
    if (deepLinkHandledRef.current) {
      return;
    }
    const deepLinkPayload = readCitationDeepLinkFromUrl();
    if (!deepLinkPayload) {
      deepLinkHandledRef.current = true;
      return;
    }
    deepLinkHandledRef.current = true;

    const applyDeepLink = async () => {
      if (deepLinkPayload.conversationId) {
        try {
          await chatState.handleSelectConversation(deepLinkPayload.conversationId);
        } catch {
          // Keep preview behavior even if conversation no longer exists.
        }
      }
      chatState.setCitationFocus(deepLinkPayload.citationFocus);
      layout.setActiveTab("Chat");
      layout.setIsInfoPanelOpen(true);
      clearCitationDeepLinkInUrl();
    };
    void applyDeepLink();
  }, [
    chatState.handleSelectConversation,
    chatState.setCitationFocus,
    layout.setActiveTab,
    layout.setIsInfoPanelOpen,
  ]);

  useEffect(() => {
    if (mindmapLinkHandledRef.current) {
      return;
    }
    const shared = readMindmapShareFromUrl();
    if (!shared) {
      mindmapLinkHandledRef.current = true;
      return;
    }
    mindmapLinkHandledRef.current = true;
    const applyShare = async () => {
      let sharedConversationId = shared.conversationId;
      let sharedMap = shared.map || null;
      if (!sharedMap && shared.shareId) {
        try {
          const resolved = await getSharedMindmap(shared.shareId);
          sharedMap =
            resolved.map && typeof resolved.map === "object"
              ? (resolved.map as Record<string, unknown>)
              : null;
          sharedConversationId = resolved.conversation_id || sharedConversationId;
        } catch {
          sharedMap = null;
        }
      }

      if (sharedConversationId) {
        try {
          await chatState.handleSelectConversation(sharedConversationId);
        } catch {
          // Continue rendering shared map even if conversation is unavailable.
        }
      }
      if (sharedMap) {
        setSharedMindmap(sharedMap);
      }
      layout.setActiveTab("Chat");
      layout.setIsInfoPanelOpen(true);
      clearMindmapShareInUrl();
    };
    void applyShare();
  }, [
    chatState.handleSelectConversation,
    layout.setActiveTab,
    layout.setIsInfoPanelOpen,
  ]);

  useEffect(() => {
    const focus = chatState.citationFocus;
    const focusTarget = String(focus?.fileId || focus?.sourceUrl || "").trim();
    const nextKey = focusTarget
      ? `${focusTarget}:${focus?.page || ""}:${String(focus?.extract || "").slice(0, 96)}:${String(focus?.evidenceId || "")}:${String(focus?.sourceName || "").slice(0, 64)}`
      : "";
    if (!nextKey) {
      return;
    }
    if (nextKey === lastAutoOpenCitationKeyRef.current) {
      return;
    }
    lastAutoOpenCitationKeyRef.current = nextKey;
    if (layout.activeTab !== "Chat") {
      layout.setActiveTab("Chat");
    }
    if (!layout.isInfoPanelOpen) {
      layout.setIsInfoPanelOpen(true);
    }
  }, [
    chatState.citationFocus,
    layout.activeTab,
    layout.isInfoPanelOpen,
    layout.setActiveTab,
    layout.setIsInfoPanelOpen,
  ]);

  const selectedSidebarConversationId =
    chatState.selectedConversationId &&
    chatState.visibleConversations.some(
      (conversation) => conversation.id === chatState.selectedConversationId,
    )
      ? chatState.selectedConversationId
      : null;
  const selectedTurn =
    chatState.selectedTurnIndex !== null
      ? chatState.chatTurns[chatState.selectedTurnIndex] || null
      : null;
  const latestTurn = chatState.chatTurns.length
    ? chatState.chatTurns[chatState.chatTurns.length - 1] || null
    : null;
  const activeTurn = selectedTurn || latestTurn;
  const selectedTurnMindmap =
    activeTurn?.mindmap && Object.keys(activeTurn.mindmap || {}).length > 0
      ? activeTurn.mindmap
      : {};
  const effectiveMindmapPayload =
    Object.keys(selectedTurnMindmap || {}).length > 0
      ? selectedTurnMindmap
      : activeTurn
        ? {}
        : sharedMindmap || {};
  const resolvedMindmapPayload = getMindmapPayload(activeTurn?.infoPanel || {}, effectiveMindmapPayload || {});
  const hasMindmapPayload = Array.isArray((resolvedMindmapPayload as { nodes?: unknown[] }).nodes)
    ? ((resolvedMindmapPayload as { nodes?: unknown[] }).nodes as unknown[]).length > 0
    : false;
  const hasSourceUrl =
    (activeTurn?.sourcesUsed || []).some((source) => hasHttpUrl(source?.url)) ||
    webSummaryHasUrl(activeTurn?.webSummary) ||
    /(?:href=['"]https?:\/\/|https?:\/\/)/i.test(String(activeTurn?.info || "")) ||
    /https?:\/\//i.test(String(activeTurn?.user || ""));
  const hasInfoPanelContent = Boolean(chatState.citationFocus) || hasMindmapPayload || hasSourceUrl;
  const isInfoPanelVisible = layout.isInfoPanelOpen && hasInfoPanelContent;
  const toggleInfoPanel = () => {
    if (!hasInfoPanelContent) {
      layout.setIsInfoPanelOpen(false);
      return;
    }
    layout.setIsInfoPanelOpen(!layout.isInfoPanelOpen);
  };

  useEffect(() => {
    if (!workspaceModalTab) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setWorkspaceModalTab(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [workspaceModalTab]);

  const renderWorkspaceTab = (tab: WorkspaceModalTab) => {
    if (tab === "Files") {
      return (
        <FilesView
          citationFocus={null}
          indexId={fileLibrary.defaultIndexId}
          files={fileLibrary.indexedFiles}
          fileGroups={fileLibrary.fileGroups}
          onRefreshFiles={fileLibrary.refreshFileCount}
          onUploadFiles={fileLibrary.handleUploadFiles}
          onCreateFileIngestionJob={fileLibrary.handleCreateFileIngestionJob}
          onCancelFileUpload={fileLibrary.handleCancelFileUpload}
          onUploadUrls={fileLibrary.handleUploadUrlsToLibrary}
          onDeleteFiles={fileLibrary.handleDeleteFiles}
          onMoveFilesToGroup={fileLibrary.handleMoveFilesToGroup}
          onCreateFileGroup={fileLibrary.handleCreateFileGroup}
          onRenameFileGroup={fileLibrary.handleRenameFileGroup}
          onDeleteFileGroup={fileLibrary.handleDeleteFileGroup}
          ingestionJobs={fileLibrary.ingestionJobs}
          onRefreshIngestionJobs={fileLibrary.refreshIngestionJobs}
          uploadStatus={fileLibrary.uploadStatus}
          uploadProgressPercent={fileLibrary.uploadProgressPercent}
          uploadProgressLabel={fileLibrary.uploadProgressLabel}
          isCancelingUpload={fileLibrary.isCancelingUpload}
        />
      );
    }
    if (tab === "Resources") {
      return <ResourcesView />;
    }
    if (tab === "Settings") {
      return <SettingsView />;
    }
    return <HelpView />;
  };

  return (
    <div className="size-full flex flex-col bg-[#f5f5f7] overflow-hidden">
      <TopNav activeTab={layout.activeTab} onTabChange={layout.setActiveTab} />
      <div ref={layout.layoutRef} className="flex-1 min-h-0 flex overflow-hidden">
        {layout.activeTab === "Chat" ? (
          <>
            <ChatSidebar
              isCollapsed={layout.isSidebarCollapsed}
              width={layout.sidebarWidth}
              onToggleCollapse={() => layout.setIsSidebarCollapsed(!layout.isSidebarCollapsed)}
              conversations={chatState.visibleConversations}
              allConversations={chatState.conversations}
              selectedConversationId={selectedSidebarConversationId}
              onSelectConversation={chatState.handleSelectConversation}
              onNewConversation={chatState.handleCreateConversation}
              projects={projectState.projects}
              selectedProjectId={projectState.selectedProjectId}
              onSelectProject={projectState.setSelectedProjectId}
              onCreateProject={projectState.handleCreateProject}
              onRenameProject={projectState.handleRenameProject}
              onDeleteProject={projectState.handleDeleteProject}
              canDeleteProject={projectState.projects.length > 0}
              conversationProjects={projectState.conversationProjects}
              onMoveConversationToProject={projectState.handleMoveConversationToProject}
              onRenameConversation={chatState.handleRenameConversation}
              onDeleteConversation={chatState.handleDeleteConversation}
              onOpenWorkspaceTab={(tab) => setWorkspaceModalTab(tab)}
            />

            {!layout.isSidebarCollapsed ? (
              <ResizeHandle
                side="left"
                active={layout.resizeSide === "left"}
                onMouseDown={(event) => {
                  event.preventDefault();
                  layout.setResizeSide("left");
                }}
              />
            ) : null}

            <ChatMain
              onToggleInfoPanel={toggleInfoPanel}
              isInfoPanelOpen={isInfoPanelVisible}
              chatTurns={chatState.chatTurns}
              selectedTurnIndex={chatState.selectedTurnIndex}
              onSelectTurn={chatState.handleSelectTurn}
              onUpdateUserTurn={chatState.handleUpdateUserTurn}
              onSendMessage={chatState.handleSendMessage}
              onUploadFiles={fileLibrary.handleUploadFilesForChat}
              onCreateFileIngestionJob={fileLibrary.handleCreateFileIngestionJob}
              availableDocuments={fileLibrary.indexedFiles}
              availableGroups={fileLibrary.fileGroups}
              availableProjects={projectState.projects}
              isSending={chatState.isSending}
              citationMode={chatState.citationMode}
              onCitationModeChange={chatState.setCitationMode}
              mindmapEnabled={chatState.mindmapEnabled}
              onMindmapEnabledChange={chatState.setMindmapEnabled}
              mindmapMaxDepth={chatState.mindmapMaxDepth}
              onMindmapMaxDepthChange={chatState.setMindmapMaxDepth}
              mindmapIncludeReasoning={chatState.mindmapIncludeReasoning}
              onMindmapIncludeReasoningChange={chatState.setMindmapIncludeReasoning}
              mindmapMapType={chatState.mindmapMapType}
              onMindmapMapTypeChange={chatState.setMindmapMapType}
              agentMode={chatState.composerMode}
              onAgentModeChange={chatState.handleAgentModeChange}
              accessMode={chatState.accessMode}
              onAccessModeChange={chatState.setAccessMode}
              activityEvents={chatState.activityEvents}
              isActivityStreaming={chatState.isActivityStreaming}
              onCitationClick={(citation) => {
                chatState.setCitationFocus(citation);
                layout.setActiveTab("Chat");
                layout.setIsInfoPanelOpen(true);
              }}
            />

            {isInfoPanelVisible ? (
              <ResizeHandle
                side="right"
                active={layout.resizeSide === "right"}
                onMouseDown={(event) => {
                  event.preventDefault();
                  layout.setResizeSide("right");
                }}
              />
            ) : null}

            {isInfoPanelVisible ? (
              <InfoPanel
                width={layout.infoPanelWidth}
                citationFocus={chatState.citationFocus}
                selectedConversationId={chatState.selectedConversationId}
                userPrompt={activeTurn?.user || ""}
                assistantHtml={activeTurn?.assistant || ""}
                infoHtml={activeTurn?.info || ""}
                infoPanel={activeTurn?.infoPanel || {}}
                mindmap={effectiveMindmapPayload}
                sourcesUsed={activeTurn?.sourcesUsed || []}
                webSummary={activeTurn?.webSummary || {}}
                sourceUsage={activeTurn?.sourceUsage || []}
                indexId={fileLibrary.defaultIndexId}
                onClearCitationFocus={() => chatState.setCitationFocus(null)}
                onSelectCitationFocus={(citation) => chatState.setCitationFocus(citation)}
                onAskMindmapNode={(node) => {
                  const focusText = String(node.text || "").trim();
                  const focusTitle = String(node.title || "").trim();
                  const defaultPrompt = focusTitle
                    ? `What are the most important details about "${focusTitle}"?`
                    : "What are the most important details about this selected topic?";
                  const typedPrompt = window.prompt(
                    "Ask a focused follow-up for this node:",
                    defaultPrompt,
                  );
                  if (typedPrompt === null) {
                    return;
                  }
                  const nextPrompt = typedPrompt.trim() || defaultPrompt;
                  void chatState.handleSendMessage(nextPrompt, undefined, {
                    citationMode: chatState.citationMode,
                    useMindmap: chatState.mindmapEnabled,
                    mindmapSettings: {
                      max_depth: chatState.mindmapMaxDepth,
                      include_reasoning_map: chatState.mindmapIncludeReasoning,
                      map_type: chatState.mindmapMapType,
                    },
                    mindmapFocus: {
                      node_id: node.nodeId,
                      title: focusTitle,
                      text: focusText,
                      page_ref: node.pageRef,
                      source_id: node.sourceId,
                      source_name: node.sourceName,
                    },
                    agentMode: chatState.composerMode,
                    accessMode: chatState.accessMode,
                  });
                }}
              />
            ) : null}

            {workspaceModalTab ? (
              <div
                className="fixed inset-0 z-[160] flex items-center justify-center p-4"
                role="dialog"
                aria-modal="true"
                aria-label={`${workspaceModalTab} panel`}
                onClick={() => setWorkspaceModalTab(null)}
              >
                <div className="absolute inset-0 bg-black/35 backdrop-blur-[1px]" />
                <div
                  className="relative z-[161] flex h-[min(88vh,980px)] w-full max-w-[1280px] min-h-[520px] flex-col overflow-hidden rounded-3xl border border-black/[0.1] bg-white shadow-[0_28px_80px_-34px_rgba(0,0,0,0.55)]"
                  onClick={(event) => event.stopPropagation()}
                >
                  <div className="flex items-center justify-between border-b border-black/[0.08] px-5 py-4">
                    <h2 className="text-[16px] font-semibold tracking-tight text-[#1d1d1f]">
                      {workspaceModalTab}
                    </h2>
                    <button
                      type="button"
                      onClick={() => setWorkspaceModalTab(null)}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/[0.08] text-[#6e6e73] transition-colors hover:bg-[#f5f5f7] hover:text-[#1d1d1f]"
                      aria-label={`Close ${workspaceModalTab}`}
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="min-h-0 flex flex-1 flex-col overflow-hidden">
                    {renderWorkspaceTab(workspaceModalTab)}
                  </div>
                </div>
              </div>
            ) : null}
          </>
        ) : layout.activeTab === "Files" ||
          layout.activeTab === "Resources" ||
          layout.activeTab === "Settings" ||
          layout.activeTab === "Help" ? (
          renderWorkspaceTab(layout.activeTab)
        ) : (
          <div className="flex-1 flex items-center justify-center bg-white">
            <p className="text-[15px] text-[#86868b]">{layout.activeTab} content coming soon...</p>
          </div>
        )}
      </div>
    </div>
  );
}
