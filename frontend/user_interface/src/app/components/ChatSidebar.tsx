import { useEffect, useMemo, useState } from "react";
import {
  ChevronRight,
  Code2,
  HelpCircle,
  Plus,
  Settings,
  FileText,
  Library,
  Plug,
  Store,
} from "lucide-react";
import { type ConversationSummary } from "../../api/client";
import {
  conversationDayGroup,
  displayConversationName,
  stripChatIcon,
  type ConversationDayGroup,
} from "./chatSidebar/conversationPresentation";
import { DeletePromptModal } from "./chatSidebar/DeletePromptModal";
import { ProjectsPane } from "./chatSidebar/ProjectsPane";
import { ProjectEvidenceModal } from "./chatSidebar/ProjectEvidenceModal";
import { useDeletePromptController } from "./chatSidebar/useDeletePromptController";
import { useProjectEvidenceDeletion } from "./chatSidebar/useProjectEvidenceDeletion";
import { useProjectEvidenceState } from "./chatSidebar/useProjectEvidenceState";
import { DeveloperPortalModal } from "./developer/DeveloperPortalModal";
import { MarketplaceNotificationBell } from "./marketplace/MarketplaceNotificationBell";

interface SidebarProject {
  id: string;
  name: string;
}

interface ChatSidebarProps {
  currentPath: string;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  conversations: ConversationSummary[];
  allConversations: ConversationSummary[];
  selectedConversationId: string | null;
  onSelectConversation: (conversationId: string) => void;
  onNewConversation: (projectId?: string) => void | Promise<void>;
  projects: SidebarProject[];
  selectedProjectId: string;
  onSelectProject: (projectId: string) => void;
  onCreateProject: (name: string) => void;
  onRenameProject: (projectId: string, name: string) => void;
  onDeleteProject: (projectId: string) => void;
  canDeleteProject: boolean;
  conversationProjects: Record<string, string>;
  onMoveConversationToProject: (conversationId: string, projectId: string) => void;
  onRenameConversation: (conversationId: string, name: string) => Promise<void>;
  onDeleteConversation: (conversationId: string) => Promise<void>;
  onOpenWorkspaceTab: (tab: "Files" | "Resources" | "Settings" | "Help") => void;
  onNavigateAppRoute: (path: string) => void;
  width?: number;
}

export function ChatSidebar({
  currentPath,
  isCollapsed,
  onToggleCollapse,
  conversations,
  allConversations,
  selectedConversationId,
  onSelectConversation,
  onNewConversation,
  projects,
  selectedProjectId,
  onSelectProject,
  onCreateProject,
  onRenameProject,
  onDeleteProject,
  canDeleteProject,
  conversationProjects,
  onMoveConversationToProject,
  onRenameConversation,
  onDeleteConversation,
  onOpenWorkspaceTab,
  onNavigateAppRoute,
  width = 300,
}: ChatSidebarProps) {
  const [isAddingProject, setIsAddingProject] = useState(false);
  const [projectDraft, setProjectDraft] = useState("");
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);
  const [editingProjectDraft, setEditingProjectDraft] = useState("");
  const [movingConversationId, setMovingConversationId] = useState<string | null>(null);
  const [renamingConversationId, setRenamingConversationId] = useState<string | null>(null);
  const [renamingConversationDraft, setRenamingConversationDraft] = useState("");
  const [busyConversationId, setBusyConversationId] = useState<string | null>(null);
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(false);
  const [developerModalOpen, setDeveloperModalOpen] = useState(false);
  const {
    deletePromptOpen,
    deletePromptTitle,
    deletePromptDescription,
    deletePromptConfirmLabel,
    deletePromptInput,
    deletePromptBusy,
    deletePromptError,
    setDeletePromptInput,
    setDeletePromptError,
    openDeletePrompt,
    closeDeletePrompt,
    confirmDeletePrompt,
  } = useDeletePromptController();

  const fallbackProjectId = useMemo(() => projects[0]?.id || "", [projects]);

  const selectedProjectConversations = useMemo(
    () =>
      [...conversations].sort(
        (left, right) =>
          new Date(right.date_updated).getTime() - new Date(left.date_updated).getTime(),
      ),
    [conversations],
  );
  const groupedProjectConversations = useMemo(() => {
    const now = new Date();
    const groups: Record<ConversationDayGroup, ConversationSummary[]> = {
      Today: [],
      Yesterday: [],
      Earlier: [],
    };
    for (const conversation of selectedProjectConversations) {
      groups[conversationDayGroup(conversation.date_updated, now)].push(conversation);
    }
    return groups;
  }, [selectedProjectConversations]);
  const {
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
  } = useProjectEvidenceState({
    allConversations,
    conversationProjects,
    fallbackProjectId,
    projects,
    onSelectProject,
  });

  const { handleDeleteEvidenceItem } = useProjectEvidenceDeletion({
    evidenceProjectId,
    getEvidenceDisplayLabel,
    openDeletePrompt,
    setEvidenceActionBusyByKey,
    setProjectUploadStatus,
    setSourceAliases,
    setProjectSourceBindings,
    loadProjectEvidence,
  });

  useEffect(() => {
    if (!deletePromptOpen) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeDeletePrompt();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [closeDeletePrompt, deletePromptOpen]);

  const submitProject = () => {
    const normalized = projectDraft.trim();
    if (!normalized) {
      return;
    }
    onCreateProject(normalized);
    setProjectDraft("");
    setIsAddingProject(false);
  };

  const startRenameProject = (project: SidebarProject) => {
    setEditingProjectId(project.id);
    setEditingProjectDraft(project.name);
  };

  const commitRenameProject = () => {
    if (!editingProjectId) {
      return;
    }
    const normalized = editingProjectDraft.trim();
    if (!normalized) {
      return;
    }
    onRenameProject(editingProjectId, normalized);
    setEditingProjectId(null);
    setEditingProjectDraft("");
  };

  const cancelRenameProject = () => {
    setEditingProjectId(null);
    setEditingProjectDraft("");
  };

  const requestDeleteProject = (project: SidebarProject) => {
    if (!canDeleteProject) {
      return;
    }
    const deletingLastProject = projects.length <= 1;
    const details = deletingLastProject
      ? "Maia will create a replacement project automatically."
      : "Conversations in it will be reassigned automatically.";
    openDeletePrompt({
      title: "Delete project",
      description: `Type delete to remove "${project.name}". ${details}`,
      confirmLabel: "Delete project",
      action: async () => {
        setProjectSourceBindings((prev) => {
          if (!Object.prototype.hasOwnProperty.call(prev, project.id)) {
            return prev;
          }
          const next = { ...prev };
          delete next[project.id];
          return next;
        });
        onDeleteProject(project.id);
      },
    });
  };

  const startRenameConversation = (conversation: ConversationSummary) => {
    setRenamingConversationId(conversation.id);
    setRenamingConversationDraft(stripChatIcon(conversation.name));
    setMovingConversationId(null);
  };

  const cancelRenameConversation = () => {
    setRenamingConversationId(null);
    setRenamingConversationDraft("");
  };

  const commitRenameConversation = async (conversationId: string) => {
    const normalized = renamingConversationDraft.trim();
    if (!normalized) {
      return;
    }
    setBusyConversationId(conversationId);
    try {
      await onRenameConversation(conversationId, normalized);
      setRenamingConversationId(null);
      setRenamingConversationDraft("");
    } catch (error) {
      console.error(error);
    } finally {
      setBusyConversationId(null);
    }
  };

  const requestDeleteConversation = (conversation: ConversationSummary) => {
    const label = displayConversationName(conversation.name);
    openDeletePrompt({
      title: "Delete chat",
      description: `Type delete to remove "${label}". This cannot be undone.`,
      confirmLabel: "Delete chat",
      action: async () => {
        setBusyConversationId(conversation.id);
        try {
          await onDeleteConversation(conversation.id);
          if (movingConversationId === conversation.id) {
            setMovingConversationId(null);
          }
          if (renamingConversationId === conversation.id) {
            cancelRenameConversation();
          }
        } finally {
          setBusyConversationId(null);
        }
      },
    });
  };

  if (isCollapsed) {
    return (
      <div className="w-16 min-h-0 rounded-[28px] border border-black/[0.06] bg-[#f6f6f7] shadow-[0_14px_40px_rgba(15,23,42,0.06)] flex flex-col items-center py-4">
        <button
          onClick={onToggleCollapse}
          className="p-2 rounded-xl hover:bg-black/5 transition-colors"
          title="Expand sidebar"
        >
          <ChevronRight className="w-5 h-5 text-[#6e6e73]" />
        </button>
      </div>
    );
  }

  return (
    <div
      className="min-h-0 rounded-[28px] border border-black/[0.06] bg-[#f6f6f7] shadow-[0_14px_40px_rgba(15,23,42,0.06)] flex flex-col overflow-hidden"
      style={{ width: `${Math.round(width)}px` }}
    >
      <div className="border-b border-black/[0.06] px-4 pb-4 pt-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">Workspace</p>
            <h2 className="mt-1 text-[20px] font-semibold tracking-[-0.02em] text-[#17171b]">Chats</h2>
          </div>
          <div className="inline-flex items-center gap-1.5">
            <MarketplaceNotificationBell onNavigate={onNavigateAppRoute} />
            <button
              onClick={() => {
                void onNewConversation(selectedProjectId);
              }}
              className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-black/[0.08] bg-white text-[#6e6e73] transition-colors hover:bg-[#f5f5f7] hover:text-[#1d1d1f]"
              title="New chat"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onToggleCollapse}
              className="p-1.5 rounded-lg hover:bg-black/5 transition-colors"
              title="Collapse sidebar"
            >
              <ChevronRight className="w-4 h-4 text-[#6e6e73]" />
            </button>
          </div>
        </div>
      </div>

      <ProjectsPane
        currentPath={currentPath}
        isAddingProject={isAddingProject}
        projectDraft={projectDraft}
        editingProjectId={editingProjectId}
        editingProjectDraft={editingProjectDraft}
        movingConversationId={movingConversationId}
        renamingConversationId={renamingConversationId}
        renamingConversationDraft={renamingConversationDraft}
        busyConversationId={busyConversationId}
        selectedProjectId={selectedProjectId}
        selectedConversationId={selectedConversationId}
        canDeleteProject={canDeleteProject}
        fallbackProjectId={fallbackProjectId}
        projects={projects}
        selectedProjectConversations={selectedProjectConversations}
        groupedProjectConversations={groupedProjectConversations}
        conversationProjects={conversationProjects}
        collapsedProjectsById={collapsedProjectsById}
        openProjectEvidenceId={openProjectEvidenceId}
        onProjectDraftChange={setProjectDraft}
        onEditingProjectDraftChange={setEditingProjectDraft}
        onRenamingConversationDraftChange={setRenamingConversationDraft}
        onSetIsAddingProject={setIsAddingProject}
        onSubmitProject={submitProject}
        onStartRenameProject={startRenameProject}
        onCommitRenameProject={commitRenameProject}
        onCancelRenameProject={cancelRenameProject}
        onHandleProjectClick={handleProjectClick}
        onHandleProjectDoubleClick={handleProjectDoubleClick}
        onToggleProjectEvidenceCard={toggleProjectEvidenceCard}
        onRequestDeleteProject={requestDeleteProject}
        onSelectConversation={onSelectConversation}
        onStartRenameConversation={startRenameConversation}
        onCommitRenameConversation={commitRenameConversation}
        onCancelRenameConversation={cancelRenameConversation}
        onSetMovingConversationId={setMovingConversationId}
        onMoveConversationToProject={onMoveConversationToProject}
        onRequestDeleteConversation={requestDeleteConversation}
        onNavigateAppRoute={onNavigateAppRoute}
      />

      <div className="px-3 py-3 border-t border-black/[0.06] bg-[#f6f6f7]">
        <div className="relative">
          <button
            onClick={() => setWorkspaceMenuOpen((open) => !open)}
            className="w-full h-9 px-3 rounded-xl border border-black/[0.06] bg-white/80 backdrop-blur text-[12px] font-medium text-[#1d1d1f] hover:bg-white transition-all inline-flex items-center justify-center gap-2 shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
          >
            <Library className="w-3.5 h-3.5 text-[#86868b]" />
            <span>Workspace</span>
          </button>

          {workspaceMenuOpen ? (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setWorkspaceMenuOpen(false)} />
              <div className="absolute bottom-11 left-0 right-0 z-20 max-h-[70vh] overflow-y-auto rounded-2xl border border-black/[0.06] bg-white/95 backdrop-blur-xl shadow-[0_12px_40px_-8px_rgba(0,0,0,0.16),0_4px_12px_-4px_rgba(0,0,0,0.06)]">
                <div className="p-1.5">
                  {[
                    { id: "Files", icon: FileText, label: "Files", hint: "Documents & uploads", bg: "bg-[#eff6ff]", bgHover: "group-hover:bg-[#dbeafe]", iconColor: "text-[#2563eb]" },
                    { id: "Resources", icon: Library, label: "Resources", hint: "Knowledge sources", bg: "bg-[#f5f3ff]", bgHover: "group-hover:bg-[#ede9fe]", iconColor: "text-[#7c3aed]" },
                  ].map((item) => (
                    <button
                      key={item.id}
                      onClick={() => {
                        onOpenWorkspaceTab(item.id as "Files" | "Resources" | "Settings" | "Help");
                        setWorkspaceMenuOpen(false);
                      }}
                      className="w-full px-3 py-2 rounded-[10px] text-left hover:bg-black/[0.04] transition-colors inline-flex items-center gap-3 group"
                    >
                      <div className={`flex h-7 w-7 items-center justify-center rounded-lg ${item.bg} transition-colors ${item.bgHover}`}>
                        <item.icon className={`w-3.5 h-3.5 ${item.iconColor}`} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] font-medium text-[#1d1d1f] leading-tight">{item.label}</p>
                        <p className="text-[11px] text-[#86868b] leading-tight">{item.hint}</p>
                      </div>
                    </button>
                  ))}
                </div>
                <div className="mx-3 h-px bg-black/[0.06]" />
                <div className="p-1.5">
                  <button
                    onClick={() => {
                      onNavigateAppRoute("/connectors");
                      setWorkspaceMenuOpen(false);
                    }}
                    className="w-full px-3 py-2 rounded-[10px] text-left hover:bg-black/[0.04] transition-colors inline-flex items-center gap-3 group"
                  >
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#f0fdf4] transition-colors group-hover:bg-[#dcfce7]">
                      <Plug className="w-3.5 h-3.5 text-[#16a34a]" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-medium text-[#1d1d1f] leading-tight">Connectors</p>
                      <p className="text-[11px] text-[#86868b] leading-tight">Integrations & APIs</p>
                    </div>
                  </button>
                  <button
                    onClick={() => {
                      onOpenWorkspaceTab("Settings");
                      setWorkspaceMenuOpen(false);
                    }}
                    className="w-full px-3 py-2 rounded-[10px] text-left hover:bg-black/[0.04] transition-colors inline-flex items-center gap-3 group"
                  >
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#f8fafc] transition-colors group-hover:bg-[#f1f5f9]">
                      <Settings className="w-3.5 h-3.5 text-[#64748b]" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-medium text-[#1d1d1f] leading-tight">Settings</p>
                      <p className="text-[11px] text-[#86868b] leading-tight">Preferences & config</p>
                    </div>
                  </button>
                </div>
                <div className="mx-3 h-px bg-black/[0.06]" />
                <div className="p-1.5">
                  <a
                    href="/marketplace"
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => setWorkspaceMenuOpen(false)}
                    className="w-full px-3 py-2 rounded-[10px] text-left hover:bg-black/[0.04] transition-colors inline-flex items-center gap-3 group"
                  >
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#fdf2f8] transition-colors group-hover:bg-[#fce7f3]">
                      <Store className="w-3.5 h-3.5 text-[#db2777]" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-medium text-[#1d1d1f] leading-tight">Marketplace</p>
                      <p className="text-[11px] text-[#86868b] leading-tight">Discover agents & teams</p>
                    </div>
                  </a>
                  <button
                    onClick={() => {
                      setWorkspaceMenuOpen(false);
                      setDeveloperModalOpen(true);
                    }}
                    className="w-full px-3 py-2 rounded-[10px] text-left hover:bg-black/[0.04] transition-colors inline-flex items-center gap-3 group"
                  >
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#fff7ed] transition-colors group-hover:bg-[#ffedd5]">
                      <Code2 className="w-3.5 h-3.5 text-[#ea580c]" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-medium text-[#1d1d1f] leading-tight">Developer</p>
                      <p className="text-[11px] text-[#86868b] leading-tight">Publish agents</p>
                    </div>
                  </button>
                  <button
                    onClick={() => {
                      onOpenWorkspaceTab("Help");
                      setWorkspaceMenuOpen(false);
                    }}
                    className="w-full px-3 py-2 rounded-[10px] text-left hover:bg-black/[0.04] transition-colors inline-flex items-center gap-3 group"
                  >
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#f8fafc] transition-colors group-hover:bg-[#f1f5f9]">
                      <HelpCircle className="w-3.5 h-3.5 text-[#64748b]" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-medium text-[#1d1d1f] leading-tight">Help</p>
                      <p className="text-[11px] text-[#86868b] leading-tight">Guides & support</p>
                    </div>
                  </button>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>

      <DeletePromptModal
        open={deletePromptOpen}
        title={deletePromptTitle}
        description={deletePromptDescription}
        confirmLabel={deletePromptConfirmLabel}
        inputValue={deletePromptInput}
        busy={deletePromptBusy}
        errorMessage={deletePromptError}
        onClose={closeDeletePrompt}
        onInputChange={(value) => {
          setDeletePromptInput(value);
          if (deletePromptError) {
            setDeletePromptError("");
          }
        }}
        onConfirm={() => void confirmDeletePrompt()}
      />

      <ProjectEvidenceModal
        evidenceProject={evidenceProject}
        evidenceProjectId={evidenceProjectId}
        evidenceProjectState={evidenceProjectState}
        evidenceProjectUploadBusy={evidenceProjectUploadBusy}
        evidenceProjectUploadStatus={evidenceProjectUploadStatus}
        evidenceProjectUrlDraft={evidenceProjectUrlDraft}
        editingEvidenceKey={editingEvidenceKey}
        editingEvidenceDraft={editingEvidenceDraft}
        evidenceActionBusyByKey={evidenceActionBusyByKey}
        fileInputRef={(node) => {
          fileInputByProjectRef.current[evidenceProjectId] = node;
        }}
        getEvidenceDisplayLabel={getEvidenceDisplayLabel}
        onClose={closeEvidenceModal}
        onRefresh={() => void loadProjectEvidence(evidenceProjectId)}
        onStartRenameEvidenceItem={startRenameEvidenceItem}
        onCancelRenameEvidenceItem={cancelRenameEvidenceItem}
        onCommitRenameEvidenceItem={commitRenameEvidenceItem}
        onEditingEvidenceDraftChange={setEditingEvidenceDraft}
        onDeleteEvidenceItem={handleDeleteEvidenceItem}
        onProjectFileUpload={(files) => void handleProjectFileUpload(evidenceProjectId, files)}
        onProjectUrlDraftChange={(value) =>
          setProjectUrlDraftById((prev) => ({
            ...prev,
            [evidenceProjectId]: value,
          }))
        }
        onSubmitProjectUrls={() => void submitProjectUrls(evidenceProjectId)}
      />

      <DeveloperPortalModal
        open={developerModalOpen}
        onClose={() => setDeveloperModalOpen(false)}
      />
    </div>
  );
}
