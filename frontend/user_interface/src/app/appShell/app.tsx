import { useEffect } from "react";
import { ChatMain } from "../components/ChatMain";
import { ChatSidebar } from "../components/ChatSidebar";
import { FilesView } from "../components/FilesView";
import { HelpView } from "../components/HelpView";
import { InfoPanel } from "../components/InfoPanel";
import { ResourcesView } from "../components/ResourcesView";
import { SettingsView } from "../components/SettingsView";
import { TopNav } from "../components/TopNav";
import { ResizeHandle } from "./ResizeHandle";
import { useConversationChat } from "./useConversationChat";
import { useFileLibrary } from "./useFileLibrary";
import { useLayoutState } from "./useLayoutState";
import { useProjectState } from "./useProjectState";

export default function App() {
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

  const selectedSidebarConversationId =
    chatState.selectedConversationId &&
    chatState.visibleConversations.some(
      (conversation) => conversation.id === chatState.selectedConversationId,
    )
      ? chatState.selectedConversationId
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
              isSending={chatState.isSending}
              citationMode={chatState.citationMode}
              onCitationModeChange={chatState.setCitationMode}
              mindmapEnabled={chatState.mindmapEnabled}
              onMindmapEnabledChange={chatState.setMindmapEnabled}
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
                messageCount={chatState.chatTurns.length}
                sourceCount={fileLibrary.fileCount}
                infoText={chatState.infoText}
                answerText={
                  chatState.selectedTurnIndex !== null
                    ? chatState.chatTurns[chatState.selectedTurnIndex]?.assistant || ""
                    : ""
                }
                questionText={
                  chatState.selectedTurnIndex !== null
                    ? chatState.chatTurns[chatState.selectedTurnIndex]?.user || ""
                    : ""
                }
                citationFocus={chatState.citationFocus}
                indexId={fileLibrary.defaultIndexId}
                onClearCitationFocus={() => chatState.setCitationFocus(null)}
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
            onUploadUrls={fileLibrary.handleUploadUrlsToLibrary}
            onDeleteFiles={fileLibrary.handleDeleteFiles}
            onMoveFilesToGroup={fileLibrary.handleMoveFilesToGroup}
            onCreateFileGroup={fileLibrary.handleCreateFileGroup}
            onRenameFileGroup={fileLibrary.handleRenameFileGroup}
            onDeleteFileGroup={fileLibrary.handleDeleteFileGroup}
            ingestionJobs={fileLibrary.ingestionJobs}
            onRefreshIngestionJobs={fileLibrary.refreshIngestionJobs}
            uploadStatus={fileLibrary.uploadStatus}
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
