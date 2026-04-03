import { useEffect, useState } from "react";
import { ACTIVE_USER_ID } from "../../api/client/core";
import { DEFAULT_PROJECT_ID, STORAGE_KEYS } from "./constants";
import { readStoredJson, readStoredText } from "./storage";
import type { SidebarProject } from "./types";

type ConversationMode = "ask" | "rag" | "company_agent" | "deep_search" | "brain";

function createProjectId() {
  return `project-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

function storageScopeForUser(rawUserId: string | null): string {
  const normalized = String(rawUserId || "default").trim().replace(/[^a-zA-Z0-9._-]/g, "_");
  return normalized || "default";
}

const USER_STORAGE_SCOPE = storageScopeForUser(ACTIVE_USER_ID);
const SCOPED_STORAGE_KEYS = {
  projects: `${STORAGE_KEYS.projects}:${USER_STORAGE_SCOPE}`,
  selectedProject: `${STORAGE_KEYS.selectedProject}:${USER_STORAGE_SCOPE}`,
  conversationProjects: `${STORAGE_KEYS.conversationProjects}:${USER_STORAGE_SCOPE}`,
  conversationModes: `${STORAGE_KEYS.conversationModes}:${USER_STORAGE_SCOPE}`,
} as const;

export function useProjectState() {
  const [projects, setProjects] = useState<SidebarProject[]>(() => {
    const stored = readStoredJson<SidebarProject[]>(
      SCOPED_STORAGE_KEYS.projects,
      readStoredJson<SidebarProject[]>(STORAGE_KEYS.projects, []),
    );
    const isLegacyDefaultOnly =
      stored.length === 1 &&
      String(stored[0]?.name || "").trim().toLowerCase() === "general";
    if (isLegacyDefaultOnly) {
      return [];
    }
    if (stored.length > 0) {
      return stored;
    }
    return [];
  });
  const [selectedProjectId, setSelectedProjectId] = useState(() =>
    readStoredText(
      SCOPED_STORAGE_KEYS.selectedProject,
      readStoredText(STORAGE_KEYS.selectedProject, DEFAULT_PROJECT_ID),
    ),
  );
  const [conversationProjects, setConversationProjects] = useState<Record<string, string>>(() =>
    readStoredJson<Record<string, string>>(
      SCOPED_STORAGE_KEYS.conversationProjects,
      readStoredJson<Record<string, string>>(STORAGE_KEYS.conversationProjects, {}),
    ),
  );
  const [conversationModes, setConversationModes] = useState<Record<string, ConversationMode>>(
    () =>
      readStoredJson<Record<string, ConversationMode>>(
        SCOPED_STORAGE_KEYS.conversationModes,
        readStoredJson<Record<string, ConversationMode>>(STORAGE_KEYS.conversationModes, {}),
      ),
  );

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(SCOPED_STORAGE_KEYS.projects, JSON.stringify(projects));
  }, [projects]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(SCOPED_STORAGE_KEYS.selectedProject, selectedProjectId);
  }, [selectedProjectId]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(
      SCOPED_STORAGE_KEYS.conversationProjects,
      JSON.stringify(conversationProjects),
    );
  }, [conversationProjects]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(SCOPED_STORAGE_KEYS.conversationModes, JSON.stringify(conversationModes));
  }, [conversationModes]);

  useEffect(() => {
    if (!projects.some((project) => project.id === selectedProjectId)) {
      setSelectedProjectId(projects[0]?.id || DEFAULT_PROJECT_ID);
    }
  }, [projects, selectedProjectId]);

  useEffect(() => {
    const singleton = projects.length === 1 ? projects[0] : null;
    if (!singleton) {
      return;
    }
    const singletonName = String(singleton.name || "").trim().toLowerCase();
    if (singletonName !== "general") {
      return;
    }
    const hasConversationMappedToSingleton = Object.values(conversationProjects).some(
      (projectId) => String(projectId || "").trim() === singleton.id,
    );
    if (hasConversationMappedToSingleton) {
      return;
    }
    setProjects([]);
  }, [conversationProjects, projects]);

  const handleCreateProject = (name: string) => {
    const normalizedName = name.trim();
    if (!normalizedName) {
      return;
    }

    const existing = projects.find(
      (project) => project.name.toLowerCase() === normalizedName.toLowerCase(),
    );
    if (existing) {
      setSelectedProjectId(existing.id);
      return;
    }

    const newProjectId = createProjectId();
    const nextProject: SidebarProject = { id: newProjectId, name: normalizedName };
    setProjects((prev) => [...prev, nextProject]);
    setSelectedProjectId(newProjectId);
  };

  const handleRenameProject = (projectId: string, name: string) => {
    const normalizedName = name.trim();
    if (!normalizedName) {
      return;
    }
    const duplicate = projects.find(
      (project) =>
        project.id !== projectId && project.name.toLowerCase() === normalizedName.toLowerCase(),
    );
    if (duplicate) {
      return;
    }
    setProjects((prev) =>
      prev.map((project) =>
        project.id === projectId ? { ...project, name: normalizedName } : project,
      ),
    );
  };

  const handleDeleteProject = (projectId: string) => {
    const remainingProjects = projects.filter((project) => project.id !== projectId);
    const nextProjects = remainingProjects;
    const fallbackProjectId = nextProjects[0]?.id || DEFAULT_PROJECT_ID;

    setProjects(nextProjects);
    setConversationProjects((prev) => {
      const next = { ...prev };
      Object.entries(next).forEach(([conversationId, assignedProjectId]) => {
        if (assignedProjectId === projectId) {
          next[conversationId] = fallbackProjectId;
        }
      });
      return next;
    });

    if (selectedProjectId === projectId) {
      setSelectedProjectId(fallbackProjectId);
    }
  };

  const handleMoveConversationToProject = (conversationId: string, projectId: string) => {
    setConversationProjects((prev) => ({
      ...prev,
      [conversationId]: projectId,
    }));
  };

  return {
    conversationModes,
    conversationProjects,
    handleCreateProject,
    handleDeleteProject,
    handleMoveConversationToProject,
    handleRenameProject,
    projects,
    selectedProjectId,
    setConversationModes,
    setConversationProjects,
    setSelectedProjectId,
  };
}
