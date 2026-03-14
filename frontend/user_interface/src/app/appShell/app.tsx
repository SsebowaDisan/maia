import { useEffect, useMemo, useRef, useState } from "react";
import { ChatMain } from "../components/ChatMain";
import { ChatSidebar } from "../components/ChatSidebar";
import { InfoPanel } from "../components/InfoPanel";
import { WorkspaceOverlayModal } from "../components/WorkspaceOverlayModal";
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
import {
  hasHttpUrl,
  isWorkspaceModalTab,
  renderWorkspaceTabContent,
  type WorkspaceModalTab,
  webSummaryHasUrl,
} from "./workspaceHelpers";
import { useConversationChat } from "./useConversationChat";
import { useFileLibrary } from "./useFileLibrary";
import { useLayoutState } from "./useLayoutState";
import { useProjectState } from "./useProjectState";
import { RoutePlaceholderPage } from "./RoutePlaceholderPage";
import { resolveAppRouteShell } from "./routeShells";
import { AgentBuilderPage } from "../pages/AgentBuilderPage";
import { AgentDetailPage } from "../pages/AgentDetailPage";
import { ConnectorMarketplacePage } from "../pages/ConnectorMarketplacePage";
import { ConnectorsPage } from "../pages/ConnectorsPage";
import { DeveloperDocsPage } from "../pages/DeveloperDocsPage";
import { DeveloperPortalPage } from "../pages/DeveloperPortalPage";
import { MarketplaceAgentDetailPage } from "../pages/MarketplaceAgentDetailPage";
import { MarketplacePage } from "../pages/MarketplacePage";
import { OperationsDashboardPage } from "../pages/OperationsDashboardPage";
import { WorkflowBuilderPage } from "../pages/WorkflowBuilderPage";
import { WorkspacePage } from "../pages/WorkspacePage";
type MindmapNodeFollowUpDraft = {
  nodeId: string;
  title: string;
  text: string;
  pageRef?: string;
  sourceId?: string;
  sourceName?: string;
  defaultPrompt: string;
};
export default function App() {
  const [pathname, setPathname] = useState(() => window.location.pathname || "/");
  const deepLinkHandledRef = useRef(false);
  const mindmapLinkHandledRef = useRef(false);
  const lastAutoOpenCitationKeyRef = useRef("");
  const [sharedMindmap, setSharedMindmap] = useState<Record<string, unknown> | null>(null);
  const [workspaceModalTab, setWorkspaceModalTab] = useState<WorkspaceModalTab | null>(null);
  const [mindmapNodeFollowUp, setMindmapNodeFollowUp] = useState<MindmapNodeFollowUpDraft | null>(null);
  const [isSendingMindmapFollowUp, setIsSendingMindmapFollowUp] = useState(false);
  const routeShell = useMemo(() => resolveAppRouteShell(pathname), [pathname]);
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

  const liveWorkspaceModalTab = workspaceModalTab || (isWorkspaceModalTab(layout.activeTab) ? layout.activeTab : null);

  useEffect(() => {
    const handleNavigation = () => setPathname(window.location.pathname || "/");
    window.addEventListener("popstate", handleNavigation);
    return () => window.removeEventListener("popstate", handleNavigation);
  }, []);

  if (routeShell.kind === "page") {
    if (routeShell.key === "marketplace") {
      return <MarketplacePage />;
    }
    if (routeShell.key === "marketplace_agent_detail") {
      return <MarketplaceAgentDetailPage agentId={String(routeShell.params?.agentId || "")} />;
    }
    if (routeShell.key === "workspace") {
      return <WorkspacePage />;
    }
    if (routeShell.key === "connectors") {
      return <ConnectorsPage />;
    }
    if (routeShell.key === "connector_marketplace") {
      return <ConnectorMarketplacePage />;
    }
    if (routeShell.key === "developer") {
      return <DeveloperPortalPage />;
    }
    if (routeShell.key === "developer_docs") {
      return <DeveloperDocsPage />;
    }
    if (routeShell.key === "agent_builder") {
      return <AgentBuilderPage />;
    }
    if (routeShell.key === "agent_detail") {
      return <AgentDetailPage agentId={String(routeShell.params?.agentId || "")} />;
    }
    if (routeShell.key === "operations") {
      return <OperationsDashboardPage />;
    }
    if (routeShell.key === "workflow_builder") {
      return <WorkflowBuilderPage />;
    }
  }

  if (routeShell.kind === "placeholder") {
    return (
      <RoutePlaceholderPage
        title={routeShell.title}
        description={routeShell.description}
        path={routeShell.path}
      />
    );
  }

  return (
    <div className="size-full bg-[#eef1f5] overflow-hidden">
      <div ref={layout.layoutRef} className="flex h-full min-h-0 gap-1 overflow-hidden px-1 py-2">
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
                attachments={activeTurn?.attachments || []}
                assistantHtml={activeTurn?.assistant || ""}
                infoHtml={activeTurn?.info || ""}
                infoPanel={activeTurn?.infoPanel || {}}
                mindmap={effectiveMindmapPayload}
                activityEvents={chatState.activityEvents}
                activityRunId={activeTurn?.activityRunId || null}
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
                  setIsSendingMindmapFollowUp(false);
                  setMindmapNodeFollowUp(null);
                }}
                onSubmit={async (typedPrompt) => {
                  const focusDraft = mindmapNodeFollowUp;
                  if (!focusDraft) {
                    return;
                  }
                  const nextPrompt = String(typedPrompt || "").trim() || focusDraft.defaultPrompt;
                  setIsSendingMindmapFollowUp(true);
                  setMindmapNodeFollowUp(null);
                  layout.setActiveTab("Chat");
                  layout.setIsInfoPanelOpen(true);
                  return chatState
                    .handleSendMessage(nextPrompt, undefined, {
                      citationMode: chatState.citationMode,
                      useMindmap: chatState.mindmapEnabled,
                      mindmapSettings: {
                        max_depth: chatState.mindmapMaxDepth,
                        include_reasoning_map: chatState.mindmapIncludeReasoning,
                        map_type: chatState.mindmapMapType,
                      },
                      mindmapFocus: {
                        node_id: focusDraft.nodeId,
                        title: focusDraft.title,
                        text: focusDraft.text,
                        page_ref: focusDraft.pageRef,
                        source_id: focusDraft.sourceId,
                        source_name: focusDraft.sourceName,
                      },
                      agentMode: chatState.composerMode,
                      accessMode: chatState.accessMode,
                    })
                    .finally(() => {
                      setIsSendingMindmapFollowUp(false);
                    });
                }}
              />
            ) : null}

            {liveWorkspaceModalTab ? (
              <WorkspaceOverlayModal tab={liveWorkspaceModalTab} onClose={closeWorkspaceModal}>
                {renderWorkspaceTabContent(liveWorkspaceModalTab, fileLibrary)}
              </WorkspaceOverlayModal>
            ) : null}
          </>
        ) : (
          <div className="flex-1 overflow-hidden rounded-[28px] border border-black/[0.06] bg-[#f6f6f7] shadow-[0_14px_40px_rgba(15,23,42,0.06)]">
            <div className="flex h-full items-center justify-center bg-[linear-gradient(180deg,#ffffff_0%,#f8fafc_100%)]">
              <p className="text-[15px] text-[#86868b]">{layout.activeTab} content coming soon...</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
