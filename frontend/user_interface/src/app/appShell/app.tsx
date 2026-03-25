import { useEffect, useMemo, useRef, useState } from "react";
import { getSharedMindmap, listDocuments } from "../../api/client";
import { getMindmapPayload } from "../components/infoPanelDerived";
import { useCanvasStore } from "../stores/canvasStore";
import { useUiPrefsStore } from "../stores/uiPrefsStore";
import { useWorkflowViewStore } from "../stores/workflowViewStore";
import {
  clearCitationDeepLinkInUrl,
  readCitationDeepLinkFromUrl,
} from "../utils/citationDeepLink";
import {
  clearMindmapShareInUrl,
  readMindmapShareFromUrl,
} from "../utils/mindmapDeepLink";
import { useFileLibrary } from "./useFileLibrary";
import { useLayoutState } from "./useLayoutState";
import { useProjectState } from "./useProjectState";
import { useConversationChat } from "./useConversationChat";
import { hasHttpUrl, isWorkspaceModalTab, webSummaryHasUrl, type WorkspaceModalTab } from "./workspaceHelpers";
import { AppChatWorkspaceLayout } from "./appShellSections/chatWorkspaceLayout";
import {
  resolveOverlayReturnPath,
  resolveSidebarOverlayForPath,
  type MindmapNodeFollowUpDraft,
  type SidebarOverlayConfig,
  SIDEBAR_OVERLAY_BY_PATH,
} from "./appShellSections/common";
import { renderStandaloneRoute } from "./appShellSections/standaloneRoutes";
import type { MarketplacePricingFilter } from "../components/marketplace/MarketplaceHeaderControls";

export default function App() {
  const [pathname, setPathname] = useState(() => window.location.pathname || "/");
  const [locationSearch, setLocationSearch] = useState(() => window.location.search || "");
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
  const deepLinkHandledRef = useRef(false);
  const mindmapLinkHandledRef = useRef(false);
  const lastAutoOpenCitationKeyRef = useRef("");
  const lastAutoOpenActivityKeyRef = useRef("");

  const density = useUiPrefsStore((state) => state.density);
  const setLastVisitedPath = useUiPrefsStore((state) => state.setLastVisitedPath);
  const upsertCanvasDocuments = useCanvasStore((state) => state.upsertDocuments);
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
    if (normalizedNext === "/insights" || normalizedNext === "/run-timeline") {
      const opsOverlay = SIDEBAR_OVERLAY_BY_PATH["/operations"];
      if (opsOverlay) {
        setSidebarOverlay(opsOverlay);
        if (layout.activeTab !== "Chat") {
          layout.setActiveTab("Chat");
        }
      }
      const opsTab = normalizedNext === "/insights" ? "insights" : "timeline";
      window.history.replaceState({}, "", `/operations?tab=${opsTab}`);
      setPathname("/operations");
      setLocationSearch(`?tab=${opsTab}`);
      return;
    }
    const overlay = SIDEBAR_OVERLAY_BY_PATH[normalizedNext];
    if (overlay) {
      setSidebarOverlay(overlay);
      if (layout.activeTab !== "Chat") {
        layout.setActiveTab("Chat");
      }
      window.history.replaceState({}, "", overlay.path);
      setPathname(overlay.path);
      setLocationSearch("");
      return;
    }
    setSidebarOverlay(null);
    navigateToPath(nextPath);
  };

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

  useEffect(() => {
    useWorkflowViewStore.getState().setRunInChat((message: string) => {
      setSidebarOverlay(null);
      if (window.location.pathname !== "/") {
        window.history.replaceState({}, "", "/");
        setPathname("/");
        setLocationSearch("");
      }
      layout.setActiveTab("Chat");
      layout.setIsInfoPanelOpen(true);
      useWorkflowViewStore.getState().setStagedMessage(message);
    });
    return () => {
      useWorkflowViewStore.getState().setRunInChat(null);
    };
  }, [layout]);

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
  }, [chatState.refreshConversations, fileLibrary.refreshFileCount, fileLibrary.refreshIngestionJobs, upsertCanvasDocuments]);

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
  }, [chatState.handleSelectConversation, chatState.setCitationFocus, layout]);

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
          sharedMap = resolved.map && typeof resolved.map === "object" ? (resolved.map as Record<string, unknown>) : null;
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
  }, [chatState.handleSelectConversation, layout]);

  useEffect(() => {
    const focus = chatState.citationFocus;
    const focusTarget = String(focus?.fileId || focus?.sourceUrl || "").trim();
    const nextKey = focusTarget
      ? `${focusTarget}:${focus?.page || ""}:${String(focus?.extract || "").slice(0, 96)}:${String(focus?.evidenceId || "")}:${String(focus?.sourceName || "").slice(0, 64)}`
      : "";
    if (!nextKey || nextKey === lastAutoOpenCitationKeyRef.current) {
      return;
    }
    lastAutoOpenCitationKeyRef.current = nextKey;
    if (layout.activeTab !== "Chat") {
      layout.setActiveTab("Chat");
    }
    if (!layout.isInfoPanelOpen) {
      layout.setIsInfoPanelOpen(true);
    }
  }, [chatState.citationFocus, layout]);

  useEffect(() => {
    const latestEventRunId = String(chatState.activityEvents[chatState.activityEvents.length - 1]?.run_id || "").trim();
    const hasActivitySignal = Boolean(latestEventRunId) || chatState.isActivityStreaming || chatState.activityEvents.length > 0;
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
  }, [chatState.activityEvents, chatState.isActivityStreaming, layout]);

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
  }, [layout.activeTab, layout]);

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
    setSidebarOverlay((current) => (current?.key === overlayFromPath.key ? current : overlayFromPath));
    if (layout.activeTab !== "Chat") {
      layout.setActiveTab("Chat");
    }
  }, [pathname, layout]);

  useEffect(() => {
    setLastVisitedPath(pathname);
  }, [pathname, setLastVisitedPath]);

  const standaloneRoute = renderStandaloneRoute({ pathname, locationSearch, navigateToPath });
  if (standaloneRoute) {
    return <>{standaloneRoute}</>;
  }

  const selectedSidebarConversationId =
    chatState.selectedConversationId &&
    chatState.visibleConversations.some((conversation) => conversation.id === chatState.selectedConversationId)
      ? chatState.selectedConversationId
      : null;
  const selectedTurn =
    chatState.selectedTurnIndex !== null ? chatState.chatTurns[chatState.selectedTurnIndex] || null : null;
  const latestTurn = chatState.chatTurns.length ? chatState.chatTurns[chatState.chatTurns.length - 1] || null : null;
  const activeTurn = selectedTurn || latestTurn;
  const selectedTurnMindmap =
    activeTurn?.mindmap && Object.keys(activeTurn.mindmap || {}).length > 0 ? activeTurn.mindmap : {};
  const effectiveMindmapPayload =
    Object.keys(selectedTurnMindmap || {}).length > 0 ? selectedTurnMindmap : activeTurn ? {} : sharedMindmap || {};
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
    Boolean(activeTurn?.activityRunId) || (Array.isArray(chatState.activityEvents) && chatState.activityEvents.length > 0);
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
      setLocationSearch("");
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

  return (
    <AppChatWorkspaceLayout
      density={density}
      layout={layout}
      chatState={chatState}
      projectState={projectState}
      fileLibrary={fileLibrary}
      pathname={pathname}
      sidebarOverlay={sidebarOverlay}
      workspaceModalTab={workspaceModalTab}
      liveWorkspaceModalTab={liveWorkspaceModalTab}
      selectedSidebarConversationId={selectedSidebarConversationId}
      isInfoPanelVisible={isInfoPanelVisible}
      toggleInfoPanel={toggleInfoPanel}
      activeTurn={activeTurn}
      effectiveMindmapPayload={effectiveMindmapPayload}
      marketplaceQuery={marketplaceQuery}
      setMarketplaceQuery={setMarketplaceQuery}
      marketplacePricingFilter={marketplacePricingFilter}
      setMarketplacePricingFilter={setMarketplacePricingFilter}
      marketplaceResultCount={marketplaceResultCount}
      setMarketplaceResultCount={setMarketplaceResultCount}
      mindmapNodeFollowUp={mindmapNodeFollowUp}
      setMindmapNodeFollowUp={setMindmapNodeFollowUp}
      isSendingMindmapFollowUp={isSendingMindmapFollowUp}
      setIsSendingMindmapFollowUp={setIsSendingMindmapFollowUp}
      closeWorkspaceModal={closeWorkspaceModal}
      openWorkspaceModal={openWorkspaceModal}
      closeSidebarOverlay={closeSidebarOverlay}
      handleSidebarConversationSelect={handleSidebarConversationSelect}
      handleSidebarAppRoute={handleSidebarAppRoute}
      setSidebarOverlay={setSidebarOverlay}
    />
  );
}
