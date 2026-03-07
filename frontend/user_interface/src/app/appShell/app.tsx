import { useEffect, useRef, useState } from "react";
import { ChatMain } from "../components/ChatMain";
import { ChatSidebar } from "../components/ChatSidebar";
import { FilesView } from "../components/FilesView";
import { HelpView } from "../components/HelpView";
import { InfoPanel } from "../components/InfoPanel";
import { LeftExecutionRail } from "../components/LeftExecutionRail";
import { ResourcesView } from "../components/ResourcesView";
import { SettingsView } from "../components/SettingsView";
import { TopNav } from "../components/TopNav";
import { WorkspaceOverlayModal, type WorkspaceOverlayTab } from "../components/WorkspaceOverlayModal";
import { NodeFollowUpModal } from "../components/mindmapViewer/NodeFollowUpModal";
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
type WorkspaceModalTab = WorkspaceOverlayTab;
type MindmapNodeFollowUpDraft = {
  nodeId: string;
  title: string;
  text: string;
  pageRef?: string;
  sourceId?: string;
  sourceName?: string;
  defaultPrompt: string;
};

function isWorkspaceModalTab(value: string): value is WorkspaceModalTab {
  return value === "Files" || value === "Resources" || value === "Settings" || value === "Help";
}
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
  const [mindmapNodeFollowUp, setMindmapNodeFollowUp] = useState<MindmapNodeFollowUpDraft | null>(null);
  const [isSendingMindmapFollowUp, setIsSendingMindmapFollowUp] = useState(false);
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
  const pendingSteps = Array.isArray(activeTurn?.nextRecommendedSteps) ? activeTurn.nextRecommendedSteps : [];
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
  const hasEvidenceHtml = String(activeTurn?.info || "").replace(/<[^>]+>/g, " ").trim().length > 0;
  const hasInfoPanelContent =
    Boolean(chatState.citationFocus) || hasMindmapPayload || hasSourceUrl || hasEvidenceHtml;
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

  useEffect(() => {
    if (!isWorkspaceModalTab(layout.activeTab)) {
      return;
    }
    setWorkspaceModalTab(layout.activeTab);
    layout.setActiveTab("Chat");
  }, [layout.activeTab, layout.setActiveTab]);

  const closeWorkspaceModal = () => {
    setWorkspaceModalTab(null);
    if (isWorkspaceModalTab(layout.activeTab)) {
      layout.setActiveTab("Chat");
    }
  };

  const openWorkspaceModal = (tab: WorkspaceModalTab) => {
    setWorkspaceModalTab(tab);
    if (layout.activeTab !== "Chat") {
      layout.setActiveTab("Chat");
    }
  };

  const handleTopNavTabChange = (tab: string) => {
    if (isWorkspaceModalTab(tab)) {
      openWorkspaceModal(tab);
      return;
    }
    layout.setActiveTab("Chat");
  };

  const effectiveTopNavTab = isWorkspaceModalTab(layout.activeTab) ? "Chat" : layout.activeTab;
  const liveWorkspaceModalTab = workspaceModalTab || (isWorkspaceModalTab(layout.activeTab) ? layout.activeTab : null);

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
      <TopNav activeTab={effectiveTopNavTab} onTabChange={handleTopNavTabChange} />
      <div ref={layout.layoutRef} className="flex-1 min-h-0 flex overflow-hidden">
        {layout.activeTab === "Chat" || isWorkspaceModalTab(layout.activeTab) ? (
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
              onOpenWorkspaceTab={openWorkspaceModal}
            />
            <LeftExecutionRail activityEvents={chatState.activityEvents} pendingSteps={pendingSteps} />

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
              clarificationPrompt={chatState.clarificationPrompt}
              onDismissClarificationPrompt={chatState.dismissClarificationPrompt}
              onSubmitClarificationPrompt={chatState.submitClarificationPrompt}
              onCitationClick={(citation) => {
                chatState.setCitationFocus(citation);
                layout.setActiveTab("Chat");
                layout.setIsInfoPanelOpen(true);
              }}
              citationFocus={chatState.citationFocus}
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
                activityEvents={chatState.activityEvents}
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
                  setMindmapNodeFollowUp({
                    nodeId: node.nodeId,
                    title: focusTitle,
                    text: focusText,
                    pageRef: node.pageRef,
                    sourceId: node.sourceId,
                    sourceName: node.sourceName,
                    defaultPrompt,
                  });
                }}
              />
            ) : null}

            {mindmapNodeFollowUp ? (
              <NodeFollowUpModal
                open
                nodeTitle={mindmapNodeFollowUp.title}
                nodeText={mindmapNodeFollowUp.text}
                sourceName={mindmapNodeFollowUp.sourceName}
                defaultPrompt={mindmapNodeFollowUp.defaultPrompt}
                submitting={isSendingMindmapFollowUp}
                onCancel={() => {
                  if (isSendingMindmapFollowUp) {
                    return;
                  }
                  setMindmapNodeFollowUp(null);
                }}
                onSubmit={async (typedPrompt) => {
                  if (!mindmapNodeFollowUp) {
                    return;
                  }
                  const nextPrompt = String(typedPrompt || "").trim() || mindmapNodeFollowUp.defaultPrompt;
                  setIsSendingMindmapFollowUp(true);
                  try {
                    await chatState.handleSendMessage(nextPrompt, undefined, {
                      citationMode: chatState.citationMode,
                      useMindmap: chatState.mindmapEnabled,
                      mindmapSettings: {
                        max_depth: chatState.mindmapMaxDepth,
                        include_reasoning_map: chatState.mindmapIncludeReasoning,
                        map_type: chatState.mindmapMapType,
                      },
                      mindmapFocus: {
                        node_id: mindmapNodeFollowUp.nodeId,
                        title: mindmapNodeFollowUp.title,
                        text: mindmapNodeFollowUp.text,
                        page_ref: mindmapNodeFollowUp.pageRef,
                        source_id: mindmapNodeFollowUp.sourceId,
                        source_name: mindmapNodeFollowUp.sourceName,
                      },
                      agentMode: chatState.composerMode,
                      accessMode: chatState.accessMode,
                    });
                    setMindmapNodeFollowUp(null);
                  } finally {
                    setIsSendingMindmapFollowUp(false);
                  }
                }}
              />
            ) : null}

            {liveWorkspaceModalTab ? (
              <WorkspaceOverlayModal tab={liveWorkspaceModalTab} onClose={closeWorkspaceModal}>
                {renderWorkspaceTab(liveWorkspaceModalTab)}
              </WorkspaceOverlayModal>
            ) : null}
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center bg-white">
            <p className="text-[15px] text-[#86868b]">{layout.activeTab} content coming soon...</p>
          </div>
        )}
      </div>
    </div>
  );
}
