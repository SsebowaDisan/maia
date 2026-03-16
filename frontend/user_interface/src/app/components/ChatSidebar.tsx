import { useEffect, useMemo, useState } from "react";
import {
  ChevronRight,
  HelpCircle,
  Plus,
  Settings,
  FileText,
  Library,
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
  insightsCount?: number;
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
  insightsCount = 0,
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
        insightsCount={insightsCount}
      />

      <div className="px-3 py-3 border-t border-black/[0.06] bg-[#f6f6f7] space-y-2.5">
        <div className="relative">
          <button
            onClick={() => setWorkspaceMenuOpen((open) => !open)}
            className="w-full h-9 px-3 rounded-xl border border-black/[0.08] bg-white text-[12px] text-[#1d1d1f] hover:bg-[#f5f5f7] transition-colors inline-flex items-center justify-center gap-2"
          >
            <Library className="w-4 h-4" />
            <span>Workspace</span>
          </button>

          {workspaceMenuOpen ? (
            <div className="absolute bottom-11 left-0 right-0 rounded-xl border border-black/[0.08] bg-white shadow-lg overflow-hidden z-20">
              {[
                { id: "Files", icon: FileText, label: "Files" },
                { id: "Resources", icon: Library, label: "Resources" },
                { id: "Settings", icon: Settings, label: "Settings" },
                { id: "Help", icon: HelpCircle, label: "Help" },
              ].map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    onOpenWorkspaceTab(item.id as "Files" | "Resources" | "Settings" | "Help");
                    setWorkspaceMenuOpen(false);
                  }}
                  className="w-full px-3 py-2.5 text-left text-[13px] text-[#1d1d1f] hover:bg-[#f5f5f7] transition-colors inline-flex items-center gap-2"
                >
                  <item.icon className="w-4 h-4 text-[#6e6e73]" />
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
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
    </div>
  );
}
