import {
  Bot,
  ArrowRightLeft,
  Check,
  FileText,
  Folder,
  FolderOpen,
  FolderPlus,
  LayoutGrid,
  LineChart,
  PencilLine,
  Route,
  Trash2,
  X,
} from "lucide-react";

import type { ConversationSummary } from "../../../api/client";
import {
  CHAT_ICON_COMPONENTS,
  conversationMetaLabel,
  displayConversationName,
  normalizeChatIconKey,
  type ConversationDayGroup,
} from "./conversationPresentation";

type SidebarProject = {
  id: string;
  name: string;
};

type ProjectsPaneProps = {
  currentPath: string;
  isAddingProject: boolean;
  projectDraft: string;
  editingProjectId: string | null;
  editingProjectDraft: string;
  movingConversationId: string | null;
  renamingConversationId: string | null;
  renamingConversationDraft: string;
  busyConversationId: string | null;
  selectedProjectId: string;
  selectedConversationId: string | null;
  canDeleteProject: boolean;
  fallbackProjectId: string;
  projects: SidebarProject[];
  selectedProjectConversations: ConversationSummary[];
  groupedProjectConversations: Record<ConversationDayGroup, ConversationSummary[]>;
  conversationProjects: Record<string, string>;
  collapsedProjectsById: Record<string, boolean>;
  openProjectEvidenceId: string | null;
  onProjectDraftChange: (value: string) => void;
  onEditingProjectDraftChange: (value: string) => void;
  onRenamingConversationDraftChange: (value: string) => void;
  onSetIsAddingProject: (next: boolean) => void;
  onSubmitProject: () => void;
  onStartRenameProject: (project: SidebarProject) => void;
  onCommitRenameProject: () => void;
  onCancelRenameProject: () => void;
  onHandleProjectClick: (projectId: string) => void;
  onHandleProjectDoubleClick: (projectId: string) => void;
  onToggleProjectEvidenceCard: (projectId: string) => void;
  onRequestDeleteProject: (project: SidebarProject) => void;
  onSelectConversation: (conversationId: string) => void;
  onStartRenameConversation: (conversation: ConversationSummary) => void;
  onCommitRenameConversation: (conversationId: string) => Promise<void>;
  onCancelRenameConversation: () => void;
  onSetMovingConversationId: (value: string | null) => void;
  onMoveConversationToProject: (conversationId: string, projectId: string) => void;
  onRequestDeleteConversation: (conversation: ConversationSummary) => void;
  onNavigateAppRoute: (path: string) => void;
};

export function ProjectsPane({
  currentPath,
  isAddingProject,
  projectDraft,
  editingProjectId,
  editingProjectDraft,
  movingConversationId,
  renamingConversationId,
  renamingConversationDraft,
  busyConversationId,
  selectedProjectId,
  selectedConversationId,
  canDeleteProject,
  fallbackProjectId,
  projects,
  selectedProjectConversations,
  groupedProjectConversations,
  conversationProjects,
  collapsedProjectsById,
  openProjectEvidenceId,
  onProjectDraftChange,
  onEditingProjectDraftChange,
  onRenamingConversationDraftChange,
  onSetIsAddingProject,
  onSubmitProject,
  onStartRenameProject,
  onCommitRenameProject,
  onCancelRenameProject,
  onHandleProjectClick,
  onHandleProjectDoubleClick,
  onToggleProjectEvidenceCard,
  onRequestDeleteProject,
  onSelectConversation,
  onStartRenameConversation,
  onCommitRenameConversation,
  onCancelRenameConversation,
  onSetMovingConversationId,
  onMoveConversationToProject,
  onRequestDeleteConversation,
  onNavigateAppRoute,
}: ProjectsPaneProps) {
  const quickLinks = [
    { id: "operations", label: "Operations", icon: LineChart, path: "/operations" },
    { id: "workflows", label: "Workflows", icon: Route, path: "/workflow-builder" },
  ] as const;
  const normalizedPath = String(currentPath || "/").toLowerCase();

  return (
    <div className="flex-1 overflow-y-auto px-3 py-3">
      <div className="space-y-1">
        <div className="mb-2">
          {quickLinks.map((entry) => {
            const active =
              normalizedPath === entry.path ||
              normalizedPath.startsWith(`${entry.path}/`);
            return (
              <button
                key={entry.id}
                type="button"
                onClick={() => onNavigateAppRoute(entry.path)}
                className={`w-full h-9 px-2.5 rounded-xl text-left text-[14px] font-normal transition-colors inline-flex items-center gap-2 ${
                  active ? "bg-[#e7e7ea] text-[#0a0a0a]" : "text-[#0a0a0a] hover:bg-[#ececef]"
                }`}
              >
                <entry.icon className="h-4 w-4 text-[#1d1d1f]" />
                <span className="truncate">{entry.label}</span>
              </button>
            );
          })}
          <div className="mx-2 mt-3 h-px bg-black/[0.08]" />
        </div>

        {isAddingProject ? (
          <div className="rounded-xl bg-white border border-black/[0.08] px-2 py-2 flex items-center gap-1.5">
            <input
              value={projectDraft}
              onChange={(event) => onProjectDraftChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  onSubmitProject();
                }
              }}
              placeholder="Project name"
              className="flex-1 h-8 px-2.5 rounded-lg border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] placeholder:text-[#8d8d93] focus:outline-none focus:ring-2 focus:ring-black/10"
            />
            <button
              onClick={onSubmitProject}
              className="h-8 px-2.5 rounded-lg bg-[#1d1d1f] text-white text-[11px] hover:bg-[#343438] transition-colors"
            >
              Add
            </button>
          </div>
        ) : (
          <button
            onClick={() => onSetIsAddingProject(true)}
            className="w-full h-9 px-2.5 rounded-xl text-left text-[14px] font-normal text-[#0a0a0a] hover:bg-[#ececef] transition-colors inline-flex items-center gap-2"
          >
            <FolderPlus className="h-4 w-4 text-[#1d1d1f]" />
            <span>New project</span>
          </button>
        )}

        {projects.map((project) => {
          const isActive = project.id === selectedProjectId;
          const isProjectCollapsed = Boolean(collapsedProjectsById[project.id]);
          const isProjectOpen = isActive && !isProjectCollapsed;
          const isEditing = editingProjectId === project.id;
          const isEvidenceOpen = openProjectEvidenceId === project.id;
          return (
            <div key={project.id} className="rounded-xl">
              {isEditing ? (
                <div className="rounded-xl bg-white border border-black/[0.08] px-2 py-1.5 flex items-center gap-1">
                  <input
                    value={editingProjectDraft}
                    onChange={(event) => onEditingProjectDraftChange(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        onCommitRenameProject();
                      }
                      if (event.key === "Escape") {
                        event.preventDefault();
                        onCancelRenameProject();
                      }
                    }}
                    className="flex-1 h-8 px-2.5 rounded-md border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] focus:outline-none focus:ring-2 focus:ring-black/10"
                  />
                  <button
                    onClick={onCommitRenameProject}
                    className="p-1.5 rounded-md text-[#1d1d1f] hover:bg-black/10"
                    title="Save"
                  >
                    <Check className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={onCancelRenameProject}
                    className="p-1.5 rounded-md text-[#1d1d1f] hover:bg-black/10"
                    title="Cancel"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              ) : (
                <div
                  className={`group h-9 px-2.5 rounded-xl inline-flex items-center gap-2 w-full ${isActive ? "bg-[#e7e7ea]" : "hover:bg-[#ececef]"}`}
                >
                  <button
                    onClick={() => onHandleProjectClick(project.id)}
                    onDoubleClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      onHandleProjectDoubleClick(project.id);
                    }}
                    className="flex-1 min-w-0 inline-flex items-center gap-2 text-left"
                  >
                    {isProjectOpen ? (
                      <FolderOpen className="h-4 w-4 text-[#1d1d1f] shrink-0" />
                    ) : (
                      <Folder className="h-4 w-4 text-[#1d1d1f] shrink-0" />
                    )}
                    <span className="truncate text-[14px] font-normal text-[#1d1d1f]">{project.name}</span>
                  </button>
                  <button
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      onToggleProjectEvidenceCard(project.id);
                    }}
                    className={`p-1 rounded-md hover:bg-black/5 hover:text-[#1d1d1f] transition-opacity ${isEvidenceOpen ? "text-[#1d1d1f] opacity-100" : "text-[#6e6e73] opacity-0 group-hover:opacity-100"}`}
                    title="Project sources and uploads"
                  >
                    <FileText className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => onStartRenameProject(project)}
                    className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Rename project"
                  >
                    <PencilLine className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => onRequestDeleteProject(project)}
                    disabled={!canDeleteProject}
                    className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-35 disabled:cursor-not-allowed"
                    title={canDeleteProject ? "Delete project" : "Delete unavailable"}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}

              {isProjectOpen ? (
                <div className="pl-8 pr-1 pb-2 pt-1">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="min-w-0">
                      <span className="text-[11px] font-semibold uppercase tracking-[0.04em] text-[#8d8d93]">Chats</span>
                      <p className="truncate text-[11px] text-[#8d8d93]">{project.name}</p>
                    </div>
                    <span className="text-[11px] text-[#8d8d93]">{selectedProjectConversations.length}</span>
                  </div>

                  {selectedProjectConversations.length ? (
                    <div className="space-y-2">
                      {(["Today", "Yesterday", "Earlier"] as const).map((groupLabel) => {
                        const rows = groupedProjectConversations[groupLabel];
                        if (!rows.length) {
                          return null;
                        }
                        return (
                          <div key={`${project.id}-${groupLabel}`} className="space-y-1">
                            <p className="px-2 text-[11px] font-medium text-[#8d8d93]">{groupLabel}</p>
                            {rows.map((conversation) => {
                              const isSelected = conversation.id === selectedConversationId;
                              const isMoving = movingConversationId === conversation.id;
                              const isRenaming = renamingConversationId === conversation.id;
                              const isBusy = busyConversationId === conversation.id;
                              const assignedProjectId = conversationProjects[conversation.id] || fallbackProjectId;
                              const subtitle = conversationMetaLabel(conversation.date_updated, new Date());
                              const ConversationIcon = CHAT_ICON_COMPONENTS[normalizeChatIconKey(conversation.icon_key)];

                              return (
                                <div key={conversation.id} className="rounded-lg">
                                  {isRenaming ? (
                                    <div className="bg-white border border-black/[0.08] rounded-lg px-2 py-1.5 flex items-center gap-1">
                                      <input
                                        value={renamingConversationDraft}
                                        onChange={(event) => onRenamingConversationDraftChange(event.target.value)}
                                        onKeyDown={(event) => {
                                          if (event.key === "Enter") {
                                            event.preventDefault();
                                            void onCommitRenameConversation(conversation.id);
                                          }
                                          if (event.key === "Escape") {
                                            event.preventDefault();
                                            onCancelRenameConversation();
                                          }
                                        }}
                                        className="flex-1 h-7 px-2 rounded-md border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] focus:outline-none focus:ring-2 focus:ring-black/10"
                                      />
                                      <button
                                        onClick={() => void onCommitRenameConversation(conversation.id)}
                                        disabled={isBusy}
                                        className="p-1 rounded-md text-[#1d1d1f] hover:bg-black/10 disabled:opacity-40"
                                        title="Save name"
                                      >
                                        <Check className="w-3.5 h-3.5" />
                                      </button>
                                      <button
                                        onClick={onCancelRenameConversation}
                                        disabled={isBusy}
                                        className="p-1 rounded-md text-[#1d1d1f] hover:bg-black/10 disabled:opacity-40"
                                        title="Cancel"
                                      >
                                        <X className="w-3.5 h-3.5" />
                                      </button>
                                    </div>
                                  ) : (
                                    <div
                                      className={`group inline-flex min-h-[44px] w-full items-center gap-1 rounded-xl px-2.5 py-1.5 ${isSelected ? "bg-[#e3e3e8]" : "hover:bg-[#ececef]"}`}
                                    >
                                      <button
                                        onClick={() => onSelectConversation(conversation.id)}
                                        className="inline-flex min-w-0 flex-1 items-center gap-2 text-left"
                                      >
                                        <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center">
                                          <ConversationIcon
                                            className={`h-3.5 w-3.5 ${isSelected ? "text-[#1d1d1f]" : "text-[#8d8d93]"}`}
                                          />
                                        </span>
                                        <div className="min-w-0">
                                          <p className="truncate text-[14px] font-medium text-[#1d1d1f]">
                                            {displayConversationName(conversation.name)}
                                          </p>
                                          <p className="mt-0.5 truncate text-[11px] text-[#8d8d93]">{subtitle}</p>
                                        </div>
                                      </button>
                                      <button
                                        onClick={() => onStartRenameConversation(conversation)}
                                        disabled={isBusy}
                                        className="rounded-md p-1 text-[#6e6e73] opacity-0 transition-opacity hover:bg-black/5 hover:text-[#1d1d1f] group-hover:opacity-100 disabled:opacity-40"
                                        title="Rename chat"
                                      >
                                        <PencilLine className="w-3.5 h-3.5" />
                                      </button>
                                      <button
                                        onClick={() => onSetMovingConversationId(movingConversationId === conversation.id ? null : conversation.id)}
                                        disabled={isBusy}
                                        className="rounded-md p-1 text-[#6e6e73] opacity-0 transition-opacity hover:bg-black/5 hover:text-[#1d1d1f] group-hover:opacity-100 disabled:opacity-40"
                                        title="Move chat"
                                      >
                                        <ArrowRightLeft className="w-3.5 h-3.5" />
                                      </button>
                                      <button
                                        onClick={() => onRequestDeleteConversation(conversation)}
                                        disabled={isBusy}
                                        className="rounded-md p-1 text-[#6e6e73] opacity-0 transition-opacity hover:bg-black/5 hover:text-[#1d1d1f] group-hover:opacity-100 disabled:opacity-40"
                                        title="Delete chat"
                                      >
                                        <Trash2 className="w-3.5 h-3.5" />
                                      </button>
                                    </div>
                                  )}

                                  {isMoving ? (
                                    <div className="mt-1 rounded-lg border border-black/[0.08] bg-white p-1 space-y-1">
                                      {projects.map((targetProject) => {
                                        const isAssigned = targetProject.id === assignedProjectId;
                                        return (
                                          <button
                                            key={targetProject.id}
                                            onClick={() => {
                                              onMoveConversationToProject(conversation.id, targetProject.id);
                                              onSetMovingConversationId(null);
                                            }}
                                            className={`w-full text-left px-2 py-1.5 rounded-md text-[12px] transition-colors ${
                                              isAssigned
                                                ? "bg-[#1d1d1f] text-white"
                                                : "text-[#1d1d1f] hover:bg-[#f5f5f7]"
                                            }`}
                                          >
                                            {targetProject.name}
                                          </button>
                                        );
                                      })}
                                    </div>
                                  ) : null}
                                </div>
                              );
                            })}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p className="text-[12px] text-[#8d8d93] py-1.5">No chats yet.</p>
                  )}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
