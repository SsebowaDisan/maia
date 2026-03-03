import { useMemo, useState } from "react";
import {
  ArrowRightLeft,
  Check,
  ChevronRight,
  Folder,
  FolderOpen,
  FolderPlus,
  HelpCircle,
  PencilLine,
  Plus,
  Settings,
  Trash2,
  X,
  FileText,
  Library,
} from "lucide-react";
import type { ConversationSummary } from "../../api/client";

const LETTER_OR_NUMBER_RE = /^[\p{L}\p{N}]$/u;
const EXTENDED_PICTOGRAPHIC_RE = /^\p{Extended_Pictographic}$/u;

function startsWithIcon(text: string) {
  const chars = Array.from(text);
  if (!chars.length) {
    return false;
  }
  const first = chars[0] || "";
  if (!first || LETTER_OR_NUMBER_RE.test(first)) {
    return false;
  }
  const codePoint = first.codePointAt(0) || 0;
  return EXTENDED_PICTOGRAPHIC_RE.test(first) || codePoint >= 0x2600;
}

function displayConversationName(name: string) {
  const cleaned = String(name || "").trim();
  if (!cleaned) {
    return "New chat";
  }
  return cleaned;
}

function stripChatIcon(name: string) {
  const cleaned = String(name || "").trim();
  const chars = Array.from(cleaned);
  if (chars.length >= 2 && startsWithIcon(cleaned) && chars[1] === " ") {
    return chars.slice(2).join("").trim();
  }
  return cleaned;
}

interface SidebarProject {
  id: string;
  name: string;
}

interface ChatSidebarProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  conversations: ConversationSummary[];
  allConversations: ConversationSummary[];
  selectedConversationId: string | null;
  onSelectConversation: (conversationId: string) => void;
  onNewConversation: () => void;
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
  mindmapEnabled: boolean;
  onMindmapEnabledChange: (enabled: boolean) => void;
  mindmapMaxDepth: number;
  onMindmapMaxDepthChange: (depth: number) => void;
  mindmapIncludeReasoning: boolean;
  onMindmapIncludeReasoningChange: (enabled: boolean) => void;
  width?: number;
}

export function ChatSidebar({
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
  mindmapEnabled,
  onMindmapEnabledChange,
  mindmapMaxDepth,
  onMindmapMaxDepthChange,
  mindmapIncludeReasoning,
  onMindmapIncludeReasoningChange,
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

  const fallbackProjectId = useMemo(() => projects[0]?.id || "", [projects]);

  const selectedProjectConversations = useMemo(
    () =>
      [...conversations].sort(
        (left, right) =>
          new Date(right.date_updated).getTime() - new Date(left.date_updated).getTime(),
      ),
    [conversations],
  );

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
    const confirmed = window.confirm(
      `Delete project \"${project.name}\"? Conversations in it will be reassigned automatically.`,
    );
    if (confirmed) {
      onDeleteProject(project.id);
    }
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

  const requestDeleteConversation = async (conversation: ConversationSummary) => {
    const confirmed = window.confirm(
      `Delete chat \"${displayConversationName(conversation.name)}\"?`,
    );
    if (!confirmed) {
      return;
    }
    setBusyConversationId(conversation.id);
    try {
      await onDeleteConversation(conversation.id);
      if (movingConversationId === conversation.id) {
        setMovingConversationId(null);
      }
      if (renamingConversationId === conversation.id) {
        cancelRenameConversation();
      }
    } catch (error) {
      console.error(error);
    } finally {
      setBusyConversationId(null);
    }
  };

  if (isCollapsed) {
    return (
      <div className="w-16 min-h-0 bg-[#f6f6f7] border-r border-black/[0.06] flex flex-col items-center py-4">
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
      className="min-h-0 bg-[#f6f6f7] border-r border-black/[0.06] flex flex-col overflow-hidden"
      style={{ width: `${Math.round(width)}px` }}
    >
      <div className="px-4 pt-4 pb-3 border-b border-black/[0.06]">
        <div className="flex items-center justify-between">
          <h2 className="text-[17px] font-medium tracking-tight text-[#1d1d1f]">Projects</h2>
          <button
            onClick={onToggleCollapse}
            className="p-1.5 rounded-lg hover:bg-black/5 transition-colors"
            title="Collapse sidebar"
          >
            <ChevronRight className="w-4 h-4 text-[#6e6e73]" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        <div className="space-y-1">
          {isAddingProject ? (
            <div className="rounded-xl bg-white border border-black/[0.08] px-2 py-2 flex items-center gap-1.5">
              <input
                value={projectDraft}
                onChange={(event) => setProjectDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    submitProject();
                  }
                }}
                placeholder="Project name"
                className="flex-1 h-8 px-2.5 rounded-lg border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] placeholder:text-[#8d8d93] focus:outline-none focus:ring-2 focus:ring-black/10"
              />
              <button
                onClick={submitProject}
                className="h-8 px-2.5 rounded-lg bg-[#1d1d1f] text-white text-[11px] hover:bg-[#343438] transition-colors"
              >
                Add
              </button>
            </div>
          ) : (
            <button
              onClick={() => setIsAddingProject(true)}
              className="w-full h-10 px-2.5 rounded-xl text-left text-[15px] text-[#0a0a0a] hover:bg-[#ececef] transition-colors inline-flex items-center gap-2"
            >
              <FolderPlus className="w-4.5 h-4.5 text-[#1d1d1f]" />
              <span>New project</span>
            </button>
          )}

          {projects.map((project) => {
            const isActive = project.id === selectedProjectId;
            const isEditing = editingProjectId === project.id;
            return (
              <div key={project.id} className="rounded-xl">
                {isEditing ? (
                  <div className="rounded-xl bg-white border border-black/[0.08] px-2 py-1.5 flex items-center gap-1">
                    <input
                      value={editingProjectDraft}
                      onChange={(event) => setEditingProjectDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          commitRenameProject();
                        }
                        if (event.key === "Escape") {
                          event.preventDefault();
                          cancelRenameProject();
                        }
                      }}
                      className="flex-1 h-8 px-2.5 rounded-md border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] focus:outline-none focus:ring-2 focus:ring-black/10"
                    />
                    <button
                      onClick={commitRenameProject}
                      className="p-1.5 rounded-md text-[#1d1d1f] hover:bg-black/10"
                      title="Save"
                    >
                      <Check className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={cancelRenameProject}
                      className="p-1.5 rounded-md text-[#1d1d1f] hover:bg-black/10"
                      title="Cancel"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : (
                  <div className={`group h-10 px-2.5 rounded-xl inline-flex items-center gap-2 w-full ${isActive ? "bg-[#e7e7ea]" : "hover:bg-[#ececef]"}`}>
                    <button
                      onClick={() => onSelectProject(project.id)}
                      className="flex-1 min-w-0 inline-flex items-center gap-2 text-left"
                    >
                      {isActive ? (
                        <FolderOpen className="w-4.5 h-4.5 text-[#1d1d1f] shrink-0" />
                      ) : (
                        <Folder className="w-4.5 h-4.5 text-[#1d1d1f] shrink-0" />
                      )}
                      <span className="text-[15px] text-[#1d1d1f] truncate">{project.name}</span>
                    </button>
                    <button
                      onClick={() => startRenameProject(project)}
                      className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Rename project"
                    >
                      <PencilLine className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => requestDeleteProject(project)}
                      disabled={!canDeleteProject}
                      className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-35 disabled:cursor-not-allowed"
                      title={canDeleteProject ? "Delete project" : "At least one project is required"}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}

                {isActive ? (
                  <div className="pl-8 pr-1 pb-2 pt-1">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[12px] text-[#8d8d93]">Recent</span>
                      <button
                        onClick={onNewConversation}
                        className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f]"
                        title="New chat in this project"
                      >
                        <Plus className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    {selectedProjectConversations.length ? (
                      <div className="space-y-1">
                        {selectedProjectConversations.map((conversation) => {
                          const isSelected = conversation.id === selectedConversationId;
                          const isMoving = movingConversationId === conversation.id;
                          const isRenaming = renamingConversationId === conversation.id;
                          const isBusy = busyConversationId === conversation.id;
                          const assignedProjectId =
                            conversationProjects[conversation.id] || fallbackProjectId;

                          return (
                            <div key={conversation.id} className="rounded-lg">
                              {isRenaming ? (
                                <div className="bg-white border border-black/[0.08] rounded-lg px-2 py-1.5 flex items-center gap-1">
                                  <input
                                    value={renamingConversationDraft}
                                    onChange={(event) => setRenamingConversationDraft(event.target.value)}
                                    onKeyDown={(event) => {
                                      if (event.key === "Enter") {
                                        event.preventDefault();
                                        void commitRenameConversation(conversation.id);
                                      }
                                      if (event.key === "Escape") {
                                        event.preventDefault();
                                        cancelRenameConversation();
                                      }
                                    }}
                                    className="flex-1 h-7 px-2 rounded-md border border-black/[0.1] bg-white text-[12px] text-[#1d1d1f] focus:outline-none focus:ring-2 focus:ring-black/10"
                                  />
                                  <button
                                    onClick={() => void commitRenameConversation(conversation.id)}
                                    disabled={isBusy}
                                    className="p-1 rounded-md text-[#1d1d1f] hover:bg-black/10 disabled:opacity-40"
                                    title="Save name"
                                  >
                                    <Check className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={cancelRenameConversation}
                                    disabled={isBusy}
                                    className="p-1 rounded-md text-[#1d1d1f] hover:bg-black/10 disabled:opacity-40"
                                    title="Cancel"
                                  >
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                              ) : (
                                <div className={`group rounded-lg px-2 py-1.5 inline-flex items-center gap-1 w-full ${isSelected ? "bg-[#e4e4e8]" : "hover:bg-[#ececef]"}`}>
                                  <button
                                    onClick={() => onSelectConversation(conversation.id)}
                                    className="flex-1 min-w-0 text-left"
                                  >
                                    <p className="text-[14px] text-[#1d1d1f] truncate">{displayConversationName(conversation.name)}</p>
                                  </button>
                                  <button
                                    onClick={() => startRenameConversation(conversation)}
                                    disabled={isBusy}
                                    className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-40"
                                    title="Rename chat"
                                  >
                                    <PencilLine className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={() =>
                                      setMovingConversationId((current) =>
                                        current === conversation.id ? null : conversation.id,
                                      )
                                    }
                                    disabled={isBusy}
                                    className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-40"
                                    title="Move chat"
                                  >
                                    <ArrowRightLeft className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={() => void requestDeleteConversation(conversation)}
                                    disabled={isBusy}
                                    className="p-1 rounded-md text-[#6e6e73] hover:bg-black/5 hover:text-[#1d1d1f] opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-40"
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
                                          onMoveConversationToProject(
                                            conversation.id,
                                            targetProject.id,
                                          );
                                          setMovingConversationId(null);
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

      <div className="px-3 py-3 border-t border-black/[0.06] bg-[#f6f6f7] space-y-2.5">
        <div className="rounded-xl border border-black/[0.08] bg-white p-2.5 space-y-2">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-[#6e6e73]">Mind-map</p>
          <label className="flex items-center justify-between gap-2 text-[12px] text-[#1d1d1f]">
            <span>Generate automatically</span>
            <input
              type="checkbox"
              checked={mindmapEnabled}
              onChange={(event) => onMindmapEnabledChange(event.target.checked)}
              className="h-4 w-4 rounded border-black/[0.15]"
            />
          </label>
          <label className="flex items-center justify-between gap-2 text-[12px] text-[#1d1d1f]">
            <span>Include reasoning map</span>
            <input
              type="checkbox"
              checked={mindmapIncludeReasoning}
              onChange={(event) => onMindmapIncludeReasoningChange(event.target.checked)}
              className="h-4 w-4 rounded border-black/[0.15]"
            />
          </label>
          <div className="flex items-center justify-between gap-2">
            <span className="text-[12px] text-[#1d1d1f]">Max depth</span>
            <select
              value={String(mindmapMaxDepth)}
              onChange={(event) => onMindmapMaxDepthChange(Number(event.target.value))}
              className="h-7 rounded-md border border-black/[0.1] bg-white px-2 text-[11px] text-[#1d1d1f]"
            >
              {[2, 3, 4, 5, 6, 7, 8].map((depth) => (
                <option key={depth} value={depth}>
                  {depth}
                </option>
              ))}
            </select>
          </div>
        </div>

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
    </div>
  );
}
