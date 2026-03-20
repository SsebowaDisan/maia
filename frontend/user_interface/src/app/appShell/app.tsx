import { useEffect, useMemo, useRef, useState } from "react";
import { AppRouteOverlayModal } from "../components/AppRouteOverlayModal";
import { ChatMain } from "../components/ChatMain";
import { ChatSidebar } from "../components/ChatSidebar";
import { InfoPanel } from "../components/InfoPanel";
import { WorkspaceOverlayModal } from "../components/WorkspaceOverlayModal";
import { NodeFollowUpModal } from "../components/mindmapViewer/NodeFollowUpModal";
import { getSharedMindmap, listDocuments } from "../../api/client";
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
import { HubShell } from "./HubShell";
import { AgentBuilderPage } from "../pages/AgentBuilderPage";
import { AgentDetailPage } from "../pages/AgentDetailPage";
import { AdminReviewQueuePage } from "../pages/AdminReviewQueuePage";
import { ConnectorMarketplacePage } from "../pages/ConnectorMarketplacePage";
import { ConnectorsPage } from "../pages/ConnectorsPage";
import { DeveloperDocsPage } from "../pages/DeveloperDocsPage";
import { DeveloperPortalPage } from "../pages/DeveloperPortalPage";
import { MarketplaceAgentDetailPage } from "../pages/MarketplaceAgentDetailPage";
import { MarketplacePage } from "../pages/MarketplacePage";
import { MyAgentsPage } from "../pages/MyAgentsPage";
import {
  MarketplaceHeaderControls,
  type MarketplacePricingFilter,
} from "../components/marketplace/MarketplaceHeaderControls";
import { OperationsDashboardPage } from "../pages/OperationsDashboardPage";
import { WorkflowBuilderPage } from "../pages/WorkflowBuilderPage";
import { WorkspacePage } from "../pages/WorkspacePage";
import { CreatorProfilePage } from "../pages/hub/CreatorProfilePage";
import { CreatorDashboardPage } from "../pages/hub/CreatorDashboardPage";
import { EditProfilePage } from "../pages/hub/EditProfilePage";
import { ExplorePage } from "../pages/hub/ExplorePage";
import { FeedPage } from "../pages/hub/FeedPage";
import { HubAgentDetailPage } from "../pages/hub/HubAgentDetailPage";
import { MarketplaceBrowsePage } from "../pages/hub/MarketplaceBrowsePage";
import { SearchResultsPage } from "../pages/hub/SearchResultsPage";
import { TeamDetailPage } from "../pages/hub/TeamDetailPage";
import { WorkflowHeaderFields } from "../components/workflowCanvas/WorkflowHeaderFields";
import { useCanvasStore } from "../stores/canvasStore";
import { useUiPrefsStore } from "../stores/uiPrefsStore";
import { useWorkflowViewStore } from "../stores/workflowViewStore";
type MindmapNodeFollowUpDraft = {
  nodeId: string;
  title: string;
  text: string;
  pageRef?: string;
  sourceId?: string;
  sourceName?: string;
  defaultPrompt: string;
};

type SidebarOverlayKey =
  | "admin_review"
  | "connectors"
  | "my_agents"
  | "workspace"
  | "marketplace"
  | "workflow_builder"
  | "operations";

type SidebarOverlayConfig = {
  key: SidebarOverlayKey;
  path: string;
  title: string;
  subtitle: string;
};

const SIDEBAR_OVERLAY_BY_PATH: Record<string, SidebarOverlayConfig> = {
  "/admin/review": {
    key: "admin_review",
    path: "/admin/review",
    title: "Review Queue",
    subtitle: "Review pending submissions and approve or reject marketplace agents.",
  },
  "/connectors": {
    key: "connectors",
    path: "/connectors",
    title: "Connectors",
    subtitle: "Manage integration credentials, health, and permissions without leaving chat.",
  },
  "/settings": {
    key: "connectors",
    path: "/connectors",
    title: "Settings",
    subtitle: "Manage integrations and connector settings.",
  },
  "/workspace": {
    key: "workspace",
    path: "/workspace",
    title: "Agents",
    subtitle: "Inspect agent runs, updates, and memory context while staying in the same session.",
  },
  "/agents": {
    key: "my_agents",
    path: "/agents",
    title: "My Agents",
    subtitle: "Review installed agents, statuses, and jump to chat-ready actions.",
  },
  "/workflow-builder": {
    key: "workflow_builder",
    path: "/workflow-builder",
    title: "Workflows",
    subtitle: "Compose multi-agent flows and preview orchestration in one canvas.",
  },
  "/operations": {
    key: "operations",
    path: "/operations",
    title: "Operations",
    subtitle: "Track run reliability, budgets, and system health in real time.",
  },
};

function resolveSidebarOverlayForPath(path: string): SidebarOverlayConfig | null {
  const normalizedPath = String(path || "/")
    .trim()
    .toLowerCase();
  return SIDEBAR_OVERLAY_BY_PATH[normalizedPath] || null;
}

function resolveOverlayReturnPath(search: string): string | null {
  const params = new URLSearchParams(String(search || ""));
  const raw = String(params.get("from") || "").trim();
  if (!raw) {
    return null;
  }
  const candidate = raw.startsWith("/") ? raw : `/${raw}`;
  const route = resolveAppRouteShell(candidate);
  if (route.kind !== "page") {
    return null;
  }
  return route.path;
}
function WorkflowBuilderHeaderActions() {
  const view = useWorkflowViewStore((s) => s.view);
  const setView = useWorkflowViewStore((s) => s.setView);
  if (view === "gallery") return null;
  return <WorkflowHeaderFields onBackToGallery={() => setView("gallery")} />;
}

export default function App() {
  const [pathname, setPathname] = useState(() => window.location.pathname || "/");
  const [locationSearch, setLocationSearch] = useState(() => window.location.search || "");
  const deepLinkHandledRef = useRef(false);
  const mindmapLinkHandledRef = useRef(false);
  const lastAutoOpenCitationKeyRef = useRef("");
  const lastAutoOpenActivityKeyRef = useRef("");
  const [sharedMindmap, setSharedMindmap] = useState<Record<string, unknown> | null>(null);
  const [workspaceModalTab, setWorkspaceModalTab] = useState<WorkspaceModalTab | null>(null);
  const [sidebarOverlay, setSidebarOverlay] = useState<SidebarOverlayConfig | null>(() =>
    resolveSidebarOverlayForPath(window.location.pathname || "/"),
  );
  const [marketplaceQuery, setMarketplaceQuery] = useState("");
  const [marketplacePricingFilter, setMarketplacePricingFilter] =
    useState<MarketplacePricingFilter>("all");
  const [marketplaceResultCount, setMarketplaceResultCount] = useState(0);
  const [mindmapNodeFollowUp, setMindmapNodeFollowUp] = useState<MindmapNodeFollowUpDraft | null>(null);
  const [isSendingMindmapFollowUp, setIsSendingMindmapFollowUp] = useState(false);
  const routeShell = useMemo(() => resolveAppRouteShell(pathname), [pathname]);
  const density = useUiPrefsStore((state) => state.density);
  const setLastVisitedPath = useUiPrefsStore((state) => state.setLastVisitedPath);
  const upsertCanvasDocuments = useCanvasStore((state) => state.upsertDocuments);
  const navigateToPath = (nextPath: string) => {
    const normalizedNext = String(nextPath || "/").trim() || "/";
    const nextUrl = new URL(normalizedNext, window.location.origin);
    const nextPathname = String(nextUrl.pathname || "/");
    const nextSearch = String(nextUrl.search || "");
    if (window.location.pathname === nextPathname && window.location.search === nextSearch) {
      return;
    }
    window.history.pushState({}, "", `${nextPathname}${nextSearch}`);
    setPathname(nextPathname);
    setLocationSearch(nextSearch);
  };
  const handleSidebarAppRoute = (nextPath: string) => {
    const normalizedNext = String(nextPath || "/").trim().toLowerCase();
    // Redirect legacy paths into Operations tabs
    if (normalizedNext === "/insights") {
      const opsOverlay = SIDEBAR_OVERLAY_BY_PATH["/operations"];
      if (opsOverlay) {
        setSidebarOverlay(opsOverlay);
        if (layout.activeTab !== "Chat") {
          layout.setActiveTab("Chat");
        }
      }
      window.history.replaceState({}, "", "/operations?tab=insights");
      setPathname("/operations");
      return;
    }
    if (normalizedNext === "/run-timeline") {
      const opsOverlay = SIDEBAR_OVERLAY_BY_PATH["/operations"];
      if (opsOverlay) {
        setSidebarOverlay(opsOverlay);
        if (layout.activeTab !== "Chat") {
          layout.setActiveTab("Chat");
        }
      }
      window.history.replaceState({}, "", "/operations?tab=timeline");
      setPathname("/operations");
      return;
    }
    const overlay = SIDEBAR_OVERLAY_BY_PATH[normalizedNext];
    if (overlay) {
      setSidebarOverlay(overlay);
      if (layout.activeTab !== "Chat") {
        layout.setActiveTab("Chat");
      }
      // Set clean URL for the overlay — no query param leaks
      window.history.replaceState({}, "", overlay.path);
      setPathname(overlay.path);
      setLocationSearch("");
      return;
    }
    setSidebarOverlay(null);
    navigateToPath(nextPath);
  };
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

  // Cmd+K / Ctrl+K to open workflow quick-switcher when on workflow builder
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        const overlay = resolveSidebarOverlayForPath(window.location.pathname);
        if (overlay?.key === "workflow_builder") {
          e.preventDefault();
          useWorkflowViewStore.getState().openQuickSwitcher();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Register runInChat callback so the workflow builder can stage messages in the composer
  useEffect(() => {
    useWorkflowViewStore.getState().setRunInChat((message: string) => {
      // Close overlay and navigate to chat
      setSidebarOverlay(null);
      const currentPath = window.location.pathname;
      if (currentPath && currentPath !== "/") {
        window.history.replaceState({}, "", "/");
        setPathname("/");
      }
      layout.setActiveTab("Chat");
      layout.setIsInfoPanelOpen(true);
      // Stage the message in the composer instead of sending immediately.
      // This lets the user review, edit, and attach documents before sending.
      useWorkflowViewStore.getState().setStagedMessage(message);
    });
    return () => {
      useWorkflowViewStore.getState().setRunInChat(null);
    };
  }, [layout, setSidebarOverlay]);

  useEffect(() => {
    const load = async () => {
      try {
        const results = await Promise.all([
          chatState.refreshConversations(),
          fileLibrary.refreshFileCount(),
          fileLibrary.refreshIngestionJobs(),
          listDocuments({ limit: 20 }),
        ]);
        const documents = results[3];
        if (Array.isArray(documents) && documents.length > 0) {
          upsertCanvasDocuments(documents);
        }
      } catch {
        // Keep UI available even if backend is not ready.
      }
    };
    void load();
  }, [
    chatState.refreshConversations,
    fileLibrary.refreshFileCount,
    fileLibrary.refreshIngestionJobs,
    upsertCanvasDocuments,
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

  useEffect(() => {
    const latestEventRunId = String(
      chatState.activityEvents[chatState.activityEvents.length - 1]?.run_id || "",
    ).trim();
    const hasActivitySignal =
      Boolean(latestEventRunId) ||
      chatState.isActivityStreaming ||
      chatState.activityEvents.length > 0;
    if (!hasActivitySignal) {
      return;
    }
    const nextKey = latestEventRunId || `activity_stream_${chatState.activityEvents.length}`;
    if (!nextKey || nextKey === lastAutoOpenActivityKeyRef.current) {
      return;
    }
    lastAutoOpenActivityKeyRef.current = nextKey;
    if (layout.activeTab !== "Chat") {
      layout.setActiveTab("Chat");
    }
    if (!layout.isInfoPanelOpen) {
      layout.setIsInfoPanelOpen(true);
    }
  }, [
    chatState.activityEvents,
    chatState.isActivityStreaming,
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
  const hasActivityConversationContent =
    Boolean(activeTurn?.activityRunId) ||
    (Array.isArray(chatState.activityEvents) && chatState.activityEvents.length > 0);
  const hasInfoPanelContent =
    Boolean(chatState.citationFocus) ||
    hasMindmapPayload ||
    hasSourceUrl ||
    hasEvidenceHtml ||
    hasActivityConversationContent;
  const isInfoPanelVisible = layout.isInfoPanelOpen && hasInfoPanelContent;
  const toggleInfoPanel = () => {
    if (!hasInfoPanelContent) {
      layout.setIsInfoPanelOpen(false);
      return;
    }
    layout.setIsInfoPanelOpen(!layout.isInfoPanelOpen);
  };

  useEffect(() => {
    if (!workspaceModalTab && !sidebarOverlay) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setWorkspaceModalTab(null);
        setSidebarOverlay(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [workspaceModalTab, sidebarOverlay]);

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

  const closeSidebarOverlay = () => {
    const returnPath = resolveOverlayReturnPath(window.location.search);
    const activeOverlayPath = sidebarOverlay?.path || null;
    if (returnPath) {
      const returnOverlay = resolveSidebarOverlayForPath(returnPath);
      setSidebarOverlay(returnOverlay || null);
      window.history.replaceState({}, "", returnPath);
      setPathname(returnPath);
      return;
    }
    setSidebarOverlay(null);
    if (activeOverlayPath && pathname === activeOverlayPath) {
      window.history.replaceState({}, "", "/");
      setPathname("/");
      setLocationSearch("");
    }
  };

  const handleSidebarConversationSelect = (conversationId: string) => {
    if (sidebarOverlay) {
      setSidebarOverlay(null);
    }
    if (workspaceModalTab) {
      setWorkspaceModalTab(null);
    }
    if (layout.activeTab !== "Chat") {
      layout.setActiveTab("Chat");
    }
    void chatState.handleSelectConversation(conversationId);
  };

  const liveWorkspaceModalTab = workspaceModalTab || (isWorkspaceModalTab(layout.activeTab) ? layout.activeTab : null);

  useEffect(() => {
    const handleNavigation = () => {
      setPathname(window.location.pathname || "/");
      setLocationSearch(window.location.search || "");
    };
    window.addEventListener("popstate", handleNavigation);
    return () => window.removeEventListener("popstate", handleNavigation);
  }, []);

  useEffect(() => {
    const overlayFromPath = resolveSidebarOverlayForPath(pathname);
    if (!overlayFromPath) {
      setSidebarOverlay(null);
      return;
    }
    setSidebarOverlay((current) => {
      if (current?.key === overlayFromPath.key) {
        return current;
      }
      return overlayFromPath;
    });
    if (layout.activeTab !== "Chat") {
      layout.setActiveTab("Chat");
    }
  }, [pathname, layout.activeTab, layout.setActiveTab]);

  useEffect(() => {
    setLastVisitedPath(pathname);
  }, [pathname, setLastVisitedPath]);

  const renderSidebarOverlayContent = () => {
    if (!sidebarOverlay) {
      return null;
    }
    if (sidebarOverlay.key === "admin_review") {
      return <AdminReviewQueuePage />;
    }
    if (sidebarOverlay.key === "connectors") {
      return <ConnectorsPage />;
    }
    if (sidebarOverlay.key === "workspace") {
      return <WorkspacePage />;
    }
    if (sidebarOverlay.key === "my_agents") {
      return <MyAgentsPage />;
    }
    if (sidebarOverlay.key === "marketplace") {
      return (
        <MarketplacePage
          query={marketplaceQuery}
          onQueryChange={setMarketplaceQuery}
          pricingFilter={marketplacePricingFilter}
          onPricingFilterChange={setMarketplacePricingFilter}
          onFilteredCountChange={setMarketplaceResultCount}
          hideTopControls
        />
      );
    }
    if (sidebarOverlay.key === "workflow_builder") {
      return <WorkflowBuilderPage />;
    }
    if (sidebarOverlay.key === "operations") {
      return <OperationsDashboardPage />;
    }
    return null;
  };

  if (routeShell.kind === "page" && !resolveSidebarOverlayForPath(pathname)) {
    if (routeShell.key === "hub_marketplace") {
      return (
        <HubShell currentPath={pathname || "/"} onNavigate={navigateToPath}>
          <MarketplaceBrowsePage onNavigate={navigateToPath} />
        </HubShell>
      );
    }
    if (routeShell.key === "hub_marketplace_agent") {
      return (
        <HubShell currentPath={pathname || "/"} onNavigate={navigateToPath}>
          <HubAgentDetailPage slug={String(routeShell.params?.slug || "")} onNavigate={navigateToPath} />
        </HubShell>
      );
    }
    if (routeShell.key === "hub_marketplace_team") {
      return (
        <HubShell currentPath={pathname || "/"} onNavigate={navigateToPath}>
          <TeamDetailPage slug={String(routeShell.params?.slug || "")} onNavigate={navigateToPath} />
        </HubShell>
      );
    }
    if (routeShell.key === "hub_creator_profile") {
      return (
        <HubShell currentPath={pathname || "/"} onNavigate={navigateToPath}>
          <CreatorProfilePage
            username={String(routeShell.params?.username || "")}
            onNavigate={navigateToPath}
          />
        </HubShell>
      );
    }
    if (routeShell.key === "hub_creator_edit") {
      return (
        <HubShell currentPath={pathname || "/"} onNavigate={navigateToPath}>
          <EditProfilePage onNavigate={navigateToPath} />
        </HubShell>
      );
    }
    if (routeShell.key === "hub_creator_dashboard") {
      return (
        <HubShell currentPath={pathname || "/"} onNavigate={navigateToPath}>
          <CreatorDashboardPage onNavigate={navigateToPath} />
        </HubShell>
      );
    }
    if (routeShell.key === "hub_explore") {
      const params = new URLSearchParams(locationSearch || "");
      const query = String(params.get("q") || "").trim();
      return (
        <HubShell currentPath={pathname || "/"} onNavigate={navigateToPath}>
          {query ? (
            <SearchResultsPage query={query} onNavigate={navigateToPath} />
          ) : (
            <ExplorePage onNavigate={navigateToPath} />
          )}
        </HubShell>
      );
    }
    if (routeShell.key === "hub_feed") {
      return (
        <HubShell currentPath={pathname || "/"} onNavigate={navigateToPath}>
          <FeedPage onNavigate={navigateToPath} />
        </HubShell>
      );
    }
    if (routeShell.key === "admin_review") {
      return <AdminReviewQueuePage />;
    }
    if (routeShell.key === "marketplace") {
      return <MarketplacePage />;
    }
    if (routeShell.key === "marketplace_agent_detail") {
      return (
        <div className="size-full bg-[#f6f6f7]">
          <MarketplacePage />
          <AppRouteOverlayModal
            title="Agent Details"
            subtitle="Inspect capabilities, connectors, schedule, and reviews without leaving marketplace."
            onClose={() => navigateToPath("/marketplace")}
          >
            <MarketplaceAgentDetailPage agentId={String(routeShell.params?.agentId || "")} />
          </AppRouteOverlayModal>
        </div>
      );
    }
    if (routeShell.key === "workspace") {
      return <WorkspacePage />;
    }
    if (routeShell.key === "my_agents") {
      return <MyAgentsPage />;
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
    if (routeShell.key === "agent_edit") {
      return <AgentBuilderPage initialAgentId={String(routeShell.params?.agentId || "")} />;
    }
    if (routeShell.key === "agent_detail") {
      return <AgentDetailPage agentId={String(routeShell.params?.agentId || "")} />;
    }
    if (routeShell.key === "agent_run") {
      return (
        <AgentDetailPage
          agentId={String(routeShell.params?.agentId || "")}
          initialTab="history"
        />
      );
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
    <div className="size-full bg-[#f6f6f7] overflow-hidden">
      <div
        ref={layout.layoutRef}
        className={`flex h-full min-h-0 gap-1 overflow-hidden px-1 ${density === "compact" ? "py-1.5" : "py-2"}`}
      >
        {layout.activeTab === "Chat" || isWorkspaceModalTab(layout.activeTab) ? (
          <>
            <ChatSidebar
              currentPath={sidebarOverlay?.path || pathname}
              isCollapsed={layout.isSidebarCollapsed}
              width={layout.sidebarWidth}
              onToggleCollapse={() => layout.setIsSidebarCollapsed(!layout.isSidebarCollapsed)}
              conversations={chatState.visibleConversations}
              allConversations={chatState.conversations}
              selectedConversationId={selectedSidebarConversationId}
              onSelectConversation={handleSidebarConversationSelect}
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
              onNavigateAppRoute={handleSidebarAppRoute}
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

            {sidebarOverlay ? (
              <AppRouteOverlayModal
                title={sidebarOverlay.title}
                subtitle={sidebarOverlay.subtitle}
                headerActions={
                  sidebarOverlay.key === "workflow_builder" ? <WorkflowBuilderHeaderActions /> : null
                }
                headerToolbar={
                  sidebarOverlay.key === "marketplace" ? (
                    <MarketplaceHeaderControls
                      query={marketplaceQuery}
                      onQueryChange={setMarketplaceQuery}
                      pricingFilter={marketplacePricingFilter}
                      onPricingFilterChange={setMarketplacePricingFilter}
                      resultCount={marketplaceResultCount}
                      compact
                    />
                  ) : null
                }
                contentClassName={sidebarOverlay.key === "workflow_builder" ? "bg-transparent p-0" : ""}
                onClose={closeSidebarOverlay}
              >
                {renderSidebarOverlayContent()}
              </AppRouteOverlayModal>
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
