import { Suspense, lazy } from "react";
import { AppRouteOverlayModal } from "../../components/AppRouteOverlayModal";
import { ChatMain } from "../../components/ChatMain";
import { ChatSidebar } from "../../components/ChatSidebar";
import { WorkspaceOverlayModal } from "../../components/WorkspaceOverlayModal";
import { NodeFollowUpModal } from "../../components/mindmapViewer/NodeFollowUpModal";
import { MarketplaceHeaderControls, type MarketplacePricingFilter } from "../../components/marketplace/MarketplaceHeaderControls";
import { ResizeHandle } from "../ResizeHandle";
import { renderWorkspaceTabContent, type WorkspaceModalTab } from "../workspaceHelpers";
import { WorkflowBuilderHeaderActions, type MindmapNodeFollowUpDraft, type SidebarOverlayConfig } from "./common";
import { RouteLoadingFallback } from "./RouteLoadingFallback";
import {
  AdminReviewQueuePage,
  ConnectorsPage,
  MarketplacePage,
  MyAgentsPage,
  OperationsDashboardPage,
  WorkflowBuilderPage,
  WorkspacePage,
} from "./lazyPages";

function withOverlaySuspense(node: React.ReactNode) {
  return <Suspense fallback={<RouteLoadingFallback />}>{node}</Suspense>;
}

const InfoPanel = lazy(async () => ({
  default: (await import("../../components/InfoPanel")).InfoPanel,
}));

function renderSidebarOverlayContent(params: {
  sidebarOverlay: SidebarOverlayConfig | null;
  marketplaceQuery: string;
  setMarketplaceQuery: (value: string) => void;
  marketplacePricingFilter: MarketplacePricingFilter;
  setMarketplacePricingFilter: (value: MarketplacePricingFilter) => void;
  marketplaceResultCount: number;
  setMarketplaceResultCount: (value: number) => void;
}) {
  const { sidebarOverlay } = params;
  if (!sidebarOverlay) {
    return null;
  }
  if (sidebarOverlay.key === "admin_review") return withOverlaySuspense(<AdminReviewQueuePage />);
  if (sidebarOverlay.key === "connectors") return withOverlaySuspense(<ConnectorsPage />);
  if (sidebarOverlay.key === "workspace") return withOverlaySuspense(<WorkspacePage />);
  if (sidebarOverlay.key === "my_agents") return withOverlaySuspense(<MyAgentsPage />);
  if (sidebarOverlay.key === "marketplace") {
    return withOverlaySuspense(
      <MarketplacePage
        query={params.marketplaceQuery}
        onQueryChange={params.setMarketplaceQuery}
        pricingFilter={params.marketplacePricingFilter}
        onPricingFilterChange={params.setMarketplacePricingFilter}
        onFilteredCountChange={params.setMarketplaceResultCount}
        hideTopControls
      />
    );
  }
  if (sidebarOverlay.key === "workflow_builder") return withOverlaySuspense(<WorkflowBuilderPage />);
  if (sidebarOverlay.key === "operations") return withOverlaySuspense(<OperationsDashboardPage />);
  return null;
}

type AppChatWorkspaceLayoutProps = {
  density: string;
  layout: any;
  chatState: any;
  projectState: any;
  fileLibrary: any;
  pathname: string;
  sidebarOverlay: SidebarOverlayConfig | null;
  workspaceModalTab: WorkspaceModalTab | null;
  liveWorkspaceModalTab: WorkspaceModalTab | null;
  selectedSidebarConversationId: string | null;
  isInfoPanelVisible: boolean;
  toggleInfoPanel: () => void;
  activeTurn: any;
  effectiveMindmapPayload: Record<string, unknown>;
  marketplaceQuery: string;
  setMarketplaceQuery: (value: string) => void;
  marketplacePricingFilter: MarketplacePricingFilter;
  setMarketplacePricingFilter: (value: MarketplacePricingFilter) => void;
  marketplaceResultCount: number;
  setMarketplaceResultCount: (value: number) => void;
  mindmapNodeFollowUp: MindmapNodeFollowUpDraft | null;
  setMindmapNodeFollowUp: (value: MindmapNodeFollowUpDraft | null) => void;
  isSendingMindmapFollowUp: boolean;
  setIsSendingMindmapFollowUp: (value: boolean) => void;
  closeWorkspaceModal: () => void;
  openWorkspaceModal: (tab: WorkspaceModalTab) => void;
  closeSidebarOverlay: () => void;
  handleSidebarConversationSelect: (conversationId: string) => void;
  handleSidebarAppRoute: (nextPath: string) => void;
  setSidebarOverlay: (value: SidebarOverlayConfig | null) => void;
};

function AppChatWorkspaceLayout(props: AppChatWorkspaceLayoutProps) {
  const renderOverlay = () =>
    renderSidebarOverlayContent({
      sidebarOverlay: props.sidebarOverlay,
      marketplaceQuery: props.marketplaceQuery,
      setMarketplaceQuery: props.setMarketplaceQuery,
      marketplacePricingFilter: props.marketplacePricingFilter,
      setMarketplacePricingFilter: props.setMarketplacePricingFilter,
      marketplaceResultCount: props.marketplaceResultCount,
      setMarketplaceResultCount: props.setMarketplaceResultCount,
    });

  return (
    <div className="size-full bg-[#f6f6f7] overflow-hidden">
      <div
        ref={props.layout.layoutRef}
        className={`flex h-full min-h-0 gap-1 overflow-hidden px-1 ${props.density === "compact" ? "py-1.5" : "py-2"}`}
      >
        {props.layout.activeTab === "Chat" || props.workspaceModalTab ? (
          <>
            <ChatSidebar
              currentPath={props.sidebarOverlay?.path || props.pathname}
              isCollapsed={props.layout.isSidebarCollapsed}
              width={props.layout.sidebarWidth}
              onToggleCollapse={() => props.layout.setIsSidebarCollapsed(!props.layout.isSidebarCollapsed)}
              conversations={props.chatState.visibleConversations}
              allConversations={props.chatState.conversations}
              selectedConversationId={props.selectedSidebarConversationId}
              onSelectConversation={props.handleSidebarConversationSelect}
              onNewConversation={props.chatState.handleCreateConversation}
              projects={props.projectState.projects}
              selectedProjectId={props.projectState.selectedProjectId}
              onSelectProject={props.projectState.setSelectedProjectId}
              onCreateProject={props.projectState.handleCreateProject}
              onRenameProject={props.projectState.handleRenameProject}
              onDeleteProject={props.projectState.handleDeleteProject}
              canDeleteProject={props.projectState.projects.length > 0}
              conversationProjects={props.projectState.conversationProjects}
              onMoveConversationToProject={props.projectState.handleMoveConversationToProject}
              onRenameConversation={props.chatState.handleRenameConversation}
              onDeleteConversation={props.chatState.handleDeleteConversation}
              onOpenWorkspaceTab={props.openWorkspaceModal}
              onNavigateAppRoute={props.handleSidebarAppRoute}
            />

            {!props.layout.isSidebarCollapsed ? (
              <ResizeHandle
                side="left"
                active={props.layout.resizeSide === "left"}
                onMouseDown={(event) => {
                  event.preventDefault();
                  props.layout.setResizeSide("left");
                }}
              />
            ) : null}

            <ChatMain
              onToggleInfoPanel={props.toggleInfoPanel}
              isInfoPanelOpen={props.isInfoPanelVisible}
              chatTurns={props.chatState.chatTurns}
              selectedTurnIndex={props.chatState.selectedTurnIndex}
              onSelectTurn={props.chatState.handleSelectTurn}
              onUpdateUserTurn={props.chatState.handleUpdateUserTurn}
              onSendMessage={props.chatState.handleSendMessage}
              onUploadFiles={props.fileLibrary.handleUploadFilesForChat}
              onCreateFileIngestionJob={props.fileLibrary.handleCreateFileIngestionJob}
              availableDocuments={props.fileLibrary.indexedFiles}
              availableGroups={props.fileLibrary.fileGroups}
              availableProjects={props.projectState.projects}
              isSending={props.chatState.isSending}
              citationMode={props.chatState.citationMode}
              onCitationModeChange={props.chatState.setCitationMode}
              mindmapEnabled={props.chatState.mindmapEnabled}
              onMindmapEnabledChange={props.chatState.setMindmapEnabled}
              mindmapMaxDepth={props.chatState.mindmapMaxDepth}
              onMindmapMaxDepthChange={props.chatState.setMindmapMaxDepth}
              mindmapIncludeReasoning={props.chatState.mindmapIncludeReasoning}
              onMindmapIncludeReasoningChange={props.chatState.setMindmapIncludeReasoning}
              mindmapMapType={props.chatState.mindmapMapType}
              onMindmapMapTypeChange={props.chatState.setMindmapMapType}
              agentMode={props.chatState.composerMode}
              onAgentModeChange={props.chatState.handleAgentModeChange}
              accessMode={props.chatState.accessMode}
              onAccessModeChange={props.chatState.setAccessMode}
              activityEvents={props.chatState.activityEvents}
              isActivityStreaming={props.chatState.isActivityStreaming}
              clarificationPrompt={props.chatState.clarificationPrompt}
              onDismissClarificationPrompt={props.chatState.dismissClarificationPrompt}
              onSubmitClarificationPrompt={props.chatState.submitClarificationPrompt}
              onCitationClick={(citation) => {
                props.chatState.setCitationFocus(citation);
                props.layout.setActiveTab("Chat");
                props.layout.setIsInfoPanelOpen(true);
              }}
              citationFocus={props.chatState.citationFocus}
            />

            {props.isInfoPanelVisible ? (
              <ResizeHandle
                side="right"
                active={props.layout.resizeSide === "right"}
                onMouseDown={(event) => {
                  event.preventDefault();
                  props.layout.setResizeSide("right");
                }}
              />
            ) : null}

            {props.isInfoPanelVisible ? (
              <Suspense fallback={<div style={{ width: `${Math.round(props.layout.infoPanelWidth)}px` }} className="min-h-0 rounded-[28px] border border-black/[0.06] bg-[#f6f6f7] shadow-[0_14px_40px_rgba(15,23,42,0.06)]" />}>
                <InfoPanel
                  width={props.layout.infoPanelWidth}
                  citationFocus={props.chatState.citationFocus}
                  selectedConversationId={props.chatState.selectedConversationId}
                  userPrompt={props.activeTurn?.user || ""}
                  attachments={props.activeTurn?.attachments || []}
                  assistantHtml={props.activeTurn?.assistant || ""}
                  infoHtml={props.activeTurn?.info || ""}
                  infoPanel={props.activeTurn?.infoPanel || {}}
                  mindmap={props.effectiveMindmapPayload}
                  activityEvents={props.chatState.activityEvents}
                  activityRunId={props.activeTurn?.activityRunId || null}
                  sourcesUsed={props.activeTurn?.sourcesUsed || []}
                  webSummary={props.activeTurn?.webSummary || {}}
                  sourceUsage={props.activeTurn?.sourceUsage || []}
                  indexId={props.fileLibrary.defaultIndexId}
                  onClearCitationFocus={() => props.chatState.setCitationFocus(null)}
                  onSelectCitationFocus={(citation) => props.chatState.setCitationFocus(citation)}
                  onAskMindmapNode={(node) => {
                    const focusText = String(node.text || "").trim();
                    const focusTitle = String(node.title || "").trim();
                    const defaultPrompt = focusTitle
                      ? `What are the most important details about "${focusTitle}"?`
                      : "What are the most important details about this selected topic?";
                    props.setMindmapNodeFollowUp({
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
              </Suspense>
            ) : null}

            {props.mindmapNodeFollowUp ? (
              <NodeFollowUpModal
                open
                nodeTitle={props.mindmapNodeFollowUp.title}
                nodeText={props.mindmapNodeFollowUp.text}
                sourceName={props.mindmapNodeFollowUp.sourceName}
                defaultPrompt={props.mindmapNodeFollowUp.defaultPrompt}
                submitting={props.isSendingMindmapFollowUp}
                onCancel={() => {
                  props.setIsSendingMindmapFollowUp(false);
                  props.setMindmapNodeFollowUp(null);
                }}
                onSubmit={async (typedPrompt) => {
                  const focusDraft = props.mindmapNodeFollowUp;
                  if (!focusDraft) {
                    return;
                  }
                  const nextPrompt = String(typedPrompt || "").trim() || focusDraft.defaultPrompt;
                  props.setIsSendingMindmapFollowUp(true);
                  props.setMindmapNodeFollowUp(null);
                  props.layout.setActiveTab("Chat");
                  props.layout.setIsInfoPanelOpen(true);
                  return props.chatState
                    .handleSendMessage(nextPrompt, undefined, {
                      citationMode: props.chatState.citationMode,
                      useMindmap: props.chatState.mindmapEnabled,
                      mindmapSettings: {
                        max_depth: props.chatState.mindmapMaxDepth,
                        include_reasoning_map: props.chatState.mindmapIncludeReasoning,
                        map_type: props.chatState.mindmapMapType,
                      },
                      mindmapFocus: {
                        node_id: focusDraft.nodeId,
                        title: focusDraft.title,
                        text: focusDraft.text,
                        page_ref: focusDraft.pageRef,
                        source_id: focusDraft.sourceId,
                        source_name: focusDraft.sourceName,
                      },
                      agentMode: props.chatState.composerMode,
                      accessMode: props.chatState.accessMode,
                    })
                    .finally(() => {
                      props.setIsSendingMindmapFollowUp(false);
                    });
                }}
              />
            ) : null}

            {props.liveWorkspaceModalTab ? (
              <WorkspaceOverlayModal tab={props.liveWorkspaceModalTab} onClose={props.closeWorkspaceModal}>
                {renderWorkspaceTabContent(props.liveWorkspaceModalTab, props.fileLibrary)}
              </WorkspaceOverlayModal>
            ) : null}

            {props.sidebarOverlay ? (
              <AppRouteOverlayModal
                title={props.sidebarOverlay.title}
                subtitle={props.sidebarOverlay.subtitle}
                headerActions={
                  props.sidebarOverlay.key === "workflow_builder" ? <WorkflowBuilderHeaderActions /> : null
                }
                headerToolbar={
                  props.sidebarOverlay.key === "marketplace" ? (
                    <MarketplaceHeaderControls
                      query={props.marketplaceQuery}
                      onQueryChange={props.setMarketplaceQuery}
                      pricingFilter={props.marketplacePricingFilter}
                      onPricingFilterChange={props.setMarketplacePricingFilter}
                      resultCount={props.marketplaceResultCount}
                      compact
                    />
                  ) : null
                }
                contentClassName={props.sidebarOverlay.key === "workflow_builder" ? "bg-transparent p-0" : ""}
                onClose={props.closeSidebarOverlay}
              >
                {renderOverlay()}
              </AppRouteOverlayModal>
            ) : null}
          </>
        ) : (
          <div className="flex-1 overflow-hidden rounded-[28px] border border-black/[0.06] bg-[#f6f6f7] shadow-[0_14px_40px_rgba(15,23,42,0.06)]">
            <div className="flex h-full items-center justify-center bg-[linear-gradient(180deg,#ffffff_0%,#f8fafc_100%)]">
              <p className="text-[15px] text-[#86868b]">{props.layout.activeTab} content coming soon...</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export { AppChatWorkspaceLayout };
