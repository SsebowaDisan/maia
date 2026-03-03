import { useEffect, useRef, useState } from "react";
import { ChatMain } from "../components/ChatMain";
import { ChatSidebar } from "../components/ChatSidebar";
import { FilesView } from "../components/FilesView";
import { HelpView } from "../components/HelpView";
import { InfoPanel } from "../components/InfoPanel";
import { ResourcesView } from "../components/ResourcesView";
import { SettingsView } from "../components/SettingsView";
import { TopNav } from "../components/TopNav";
import {
  clearCitationDeepLinkInUrl,
  readCitationDeepLinkFromUrl,
} from "../utils/citationDeepLink";
import {
  clearMindmapShareInUrl,
  readMindmapShareFromUrl,
} from "../utils/mindmapDeepLink";
import { ResizeHandle } from "./ResizeHandle";
import { useConversationChat } from "./useConversationChat";
import { useFileLibrary } from "./useFileLibrary";
import { useLayoutState } from "./useLayoutState";
import { useProjectState } from "./useProjectState";

export default function App() {
  const deepLinkHandledRef = useRef(false);
  const mindmapLinkHandledRef = useRef(false);
  const lastAutoOpenCitationKeyRef = useRef("");
  const [sharedMindmap, setSharedMindmap] = useState<Record<string, unknown> | null>(null);
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
      if (shared.conversationId) {
        try {
          await chatState.handleSelectConversation(shared.conversationId);
        } catch {
          // Continue rendering shared map even if conversation is unavailable.
        }
      }
      setSharedMindmap(shared.map);
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
    const nextKey = focus?.fileId
      ? `${focus.fileId}:${focus.page || ""}:${String(focus.extract || "").slice(0, 96)}:${String(focus.evidenceId || "")}:${String(focus.sourceName || "").slice(0, 64)}`
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
              canDeleteProject={projectState.projects.length > 1}
              conversationProjects={projectState.conversationProjects}
              onMoveConversationToProject={projectState.handleMoveConversationToProject}
              onRenameConversation={chatState.handleRenameConversation}
              onDeleteConversation={chatState.handleDeleteConversation}
              onOpenWorkspaceTab={(tab) => layout.setActiveTab(tab)}
              mindmapEnabled={chatState.mindmapEnabled}
              onMindmapEnabledChange={chatState.setMindmapEnabled}
              mindmapMaxDepth={chatState.mindmapMaxDepth}
              onMindmapMaxDepthChange={chatState.setMindmapMaxDepth}
              mindmapIncludeReasoning={chatState.mindmapIncludeReasoning}
              onMindmapIncludeReasoningChange={chatState.setMindmapIncludeReasoning}
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
              onToggleInfoPanel={() => layout.setIsInfoPanelOpen(!layout.isInfoPanelOpen)}
              isInfoPanelOpen={layout.isInfoPanelOpen}
              chatTurns={chatState.chatTurns}
              selectedTurnIndex={chatState.selectedTurnIndex}
              onSelectTurn={chatState.handleSelectTurn}
              onUpdateUserTurn={chatState.handleUpdateUserTurn}
              onSendMessage={chatState.handleSendMessage}
              onUploadFiles={fileLibrary.handleUploadFilesForChat}
              onCreateFileIngestionJob={fileLibrary.handleCreateFileIngestionJob}
              isSending={chatState.isSending}
              citationMode={chatState.citationMode}
              onCitationModeChange={chatState.setCitationMode}
              mindmapEnabled={chatState.mindmapEnabled}
              onMindmapEnabledChange={chatState.setMindmapEnabled}
              mindmapMaxDepth={chatState.mindmapMaxDepth}
              onMindmapMaxDepthChange={chatState.setMindmapMaxDepth}
              mindmapIncludeReasoning={chatState.mindmapIncludeReasoning}
              onMindmapIncludeReasoningChange={chatState.setMindmapIncludeReasoning}
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

            {layout.isInfoPanelOpen ? (
              <ResizeHandle
                side="right"
                active={layout.resizeSide === "right"}
                onMouseDown={(event) => {
                  event.preventDefault();
                  layout.setResizeSide("right");
                }}
              />
            ) : null}

            {layout.isInfoPanelOpen ? (
              <InfoPanel
                width={layout.infoPanelWidth}
                citationFocus={chatState.citationFocus}
                selectedConversationId={chatState.selectedConversationId}
                assistantHtml={selectedTurn?.assistant || ""}
                infoHtml={selectedTurn?.info || ""}
                infoPanel={selectedTurn?.infoPanel || {}}
                mindmap={
                  selectedTurn?.mindmap && Object.keys(selectedTurn.mindmap || {}).length > 0
                    ? selectedTurn.mindmap
                    : sharedMindmap || {}
                }
                sourceUsage={selectedTurn?.sourceUsage || []}
                indexId={fileLibrary.defaultIndexId}
                onClearCitationFocus={() => chatState.setCitationFocus(null)}
                onSelectCitationFocus={(citation) => chatState.setCitationFocus(citation)}
                onAskMindmapNode={(node) => {
                  const focusText = String(node.text || "").trim();
                  const focusTitle = String(node.title || "").trim();
                  const nextPrompt = focusTitle
                    ? `Focus on "${focusTitle}" and answer the follow-up in detail.`
                    : "Focus on the selected mind-map node and answer in detail.";
                  void chatState.handleSendMessage(nextPrompt, undefined, {
                    citationMode: chatState.citationMode,
                    useMindmap: chatState.mindmapEnabled,
                    mindmapSettings: {
                      max_depth: chatState.mindmapMaxDepth,
                      include_reasoning_map: chatState.mindmapIncludeReasoning,
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
          </>
        ) : layout.activeTab === "Files" ? (
          <FilesView
            citationFocus={null}
            indexId={fileLibrary.defaultIndexId}
            files={fileLibrary.indexedFiles}
            fileGroups={fileLibrary.fileGroups}
            onRefreshFiles={fileLibrary.refreshFileCount}
            onUploadFiles={fileLibrary.handleUploadFiles}
            onCreateFileIngestionJob={fileLibrary.handleCreateFileIngestionJob}
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
          />
        ) : layout.activeTab === "Resources" ? (
          <ResourcesView />
        ) : layout.activeTab === "Settings" ? (
          <SettingsView />
        ) : layout.activeTab === "Help" ? (
          <HelpView />
        ) : (
          <div className="flex-1 flex items-center justify-center bg-white">
            <p className="text-[15px] text-[#86868b]">{layout.activeTab} content coming soon...</p>
          </div>
        )}
      </div>
    </div>
  );
}
