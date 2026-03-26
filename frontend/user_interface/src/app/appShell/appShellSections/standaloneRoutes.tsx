import { RoutePlaceholderPage } from "../RoutePlaceholderPage";
import { HubShell } from "../HubShell";
import { AdminReviewQueuePage } from "../../pages/AdminReviewQueuePage";
import { MarketplacePage } from "../../pages/MarketplacePage";
import { MarketplaceAgentDetailPage } from "../../pages/MarketplaceAgentDetailPage";
import { WorkspacePage } from "../../pages/WorkspacePage";
import { MyAgentsPage } from "../../pages/MyAgentsPage";
import { ConnectorsPage } from "../../pages/ConnectorsPage";
import { ConnectorMarketplacePage } from "../../pages/ConnectorMarketplacePage";
import { DeveloperPortalPage } from "../../pages/DeveloperPortalPage";
import { DeveloperDocsPage } from "../../pages/DeveloperDocsPage";
import { AgentBuilderPage } from "../../pages/AgentBuilderPage";
import { AgentDetailPage } from "../../pages/AgentDetailPage";
import { OperationsDashboardPage } from "../../pages/OperationsDashboardPage";
import { WorkflowBuilderPage } from "../../pages/WorkflowBuilderPage";
import { MarketplaceBrowsePage } from "../../pages/hub/MarketplaceBrowsePage";
import { HubAgentDetailPage } from "../../pages/hub/HubAgentDetailPage";
import { TeamDetailPage } from "../../pages/hub/TeamDetailPage";
import { CreatorProfilePage } from "../../pages/hub/CreatorProfilePage";
import { EditProfilePage } from "../../pages/hub/EditProfilePage";
import { CreatorDashboardPage } from "../../pages/hub/CreatorDashboardPage";
import { ExplorePage } from "../../pages/hub/ExplorePage";
import { FeedPage } from "../../pages/hub/FeedPage";
import { SearchResultsPage } from "../../pages/hub/SearchResultsPage";
import { AppRouteOverlayModal } from "../../components/AppRouteOverlayModal";
import { resolveSidebarOverlayForPath } from "./common";
import { resolveAppRouteShell } from "../routeShells";

function renderStandaloneRoute(params: {
  pathname: string;
  locationSearch: string;
  navigateToPath: (nextPath: string) => void;
}): React.ReactNode | null {
  const routeShell = resolveAppRouteShell(params.pathname);
  if (routeShell.kind === "placeholder") {
    return (
      <RoutePlaceholderPage
        title={routeShell.title}
        description={routeShell.description}
        path={routeShell.path}
      />
    );
  }
  if (routeShell.kind !== "page" || resolveSidebarOverlayForPath(params.pathname)) {
    return null;
  }
  if (routeShell.key === "hub_marketplace") {
    return (
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <MarketplaceBrowsePage onNavigate={params.navigateToPath} />
      </HubShell>
    );
  }
  if (routeShell.key === "hub_marketplace_agent") {
    return (
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <HubAgentDetailPage slug={String(routeShell.params?.slug || "")} onNavigate={params.navigateToPath} />
      </HubShell>
    );
  }
  if (routeShell.key === "hub_marketplace_team") {
    return (
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <TeamDetailPage slug={String(routeShell.params?.slug || "")} onNavigate={params.navigateToPath} />
      </HubShell>
    );
  }
  if (routeShell.key === "hub_creator_profile") {
    return (
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <CreatorProfilePage
          username={String(routeShell.params?.username || "")}
          onNavigate={params.navigateToPath}
        />
      </HubShell>
    );
  }
  if (routeShell.key === "hub_creator_edit") {
    return (
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <EditProfilePage onNavigate={params.navigateToPath} />
      </HubShell>
    );
  }
  if (routeShell.key === "hub_creator_dashboard") {
    return (
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <CreatorDashboardPage onNavigate={params.navigateToPath} />
      </HubShell>
    );
  }
  if (routeShell.key === "hub_explore") {
    const paramsQuery = new URLSearchParams(params.locationSearch || "");
    const query = String(paramsQuery.get("q") || "").trim();
    return (
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        {query ? (
          <SearchResultsPage query={query} onNavigate={params.navigateToPath} />
        ) : (
          <ExplorePage onNavigate={params.navigateToPath} />
        )}
      </HubShell>
    );
  }
  if (routeShell.key === "hub_feed") {
    return (
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <FeedPage onNavigate={params.navigateToPath} />
      </HubShell>
    );
  }
  if (routeShell.key === "admin_review") return <AdminReviewQueuePage />;
  if (routeShell.key === "marketplace") return <MarketplacePage />;
  if (routeShell.key === "marketplace_agent_detail") {
    return (
      <div className="size-full bg-[#f6f6f7]">
        <MarketplacePage />
        <AppRouteOverlayModal
          title="Agent Details"
          subtitle="Inspect capabilities, connectors, schedule, and reviews without leaving marketplace."
          onClose={() => params.navigateToPath("/marketplace")}
        >
          <MarketplaceAgentDetailPage agentId={String(routeShell.params?.agentId || "")} />
        </AppRouteOverlayModal>
      </div>
    );
  }
  if (routeShell.key === "workspace") return <WorkspacePage />;
  if (routeShell.key === "my_agents") return <MyAgentsPage />;
  if (routeShell.key === "connectors") return <ConnectorsPage />;
  if (routeShell.key === "connector_marketplace") return <ConnectorMarketplacePage />;
  if (routeShell.key === "developer") return <DeveloperPortalPage />;
  if (routeShell.key === "developer_docs") return <DeveloperDocsPage />;
  if (routeShell.key === "agent_builder") return <AgentBuilderPage />;
  if (routeShell.key === "agent_edit") {
    return <AgentBuilderPage initialAgentId={String(routeShell.params?.agentId || "")} />;
  }
  if (routeShell.key === "agent_detail") {
    return <AgentDetailPage agentId={String(routeShell.params?.agentId || "")} />;
  }
  if (routeShell.key === "agent_run") {
    return <AgentDetailPage agentId={String(routeShell.params?.agentId || "")} initialTab="history" />;
  }
  if (routeShell.key === "operations") return <OperationsDashboardPage />;
  if (routeShell.key === "workflow_builder") return <WorkflowBuilderPage />;
  return null;
}

export { renderStandaloneRoute };
