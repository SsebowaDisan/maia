import { Suspense } from "react";
import { RoutePlaceholderPage } from "../RoutePlaceholderPage";
import { HubShell } from "../HubShell";
import { AppRouteOverlayModal } from "../../components/AppRouteOverlayModal";
import { resolveSidebarOverlayForPath } from "./common";
import { resolveAppRouteShell } from "../routeShells";
import { RouteLoadingFallback } from "./RouteLoadingFallback";
import {
  AdminReviewQueuePage,
  AgentBuilderPage,
  AgentDetailPage,
  ConnectorsPage,
  ConnectorMarketplacePage,
  CreatorDashboardPage,
  CreatorProfilePage,
  DeveloperDocsPage,
  DeveloperPortalPage,
  EditProfilePage,
  ExplorePage,
  FeedPage,
  HubAgentDetailPage,
  MarketplaceAgentDetailPage,
  MarketplaceBrowsePage,
  MarketplacePage,
  MyAgentsPage,
  OperationsDashboardPage,
  SearchResultsPage,
  TeamDetailPage,
  WorkflowBuilderPage,
  WorkspacePage,
} from "./lazyPages";

function withRouteSuspense(node: React.ReactNode) {
  return <Suspense fallback={<RouteLoadingFallback />}>{node}</Suspense>;
}

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
    return withRouteSuspense(
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <MarketplaceBrowsePage onNavigate={params.navigateToPath} />
      </HubShell>
    );
  }
  if (routeShell.key === "hub_marketplace_agent") {
    return withRouteSuspense(
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <HubAgentDetailPage slug={String(routeShell.params?.slug || "")} onNavigate={params.navigateToPath} />
      </HubShell>
    );
  }
  if (routeShell.key === "hub_marketplace_team") {
    return withRouteSuspense(
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <TeamDetailPage slug={String(routeShell.params?.slug || "")} onNavigate={params.navigateToPath} />
      </HubShell>
    );
  }
  if (routeShell.key === "hub_creator_profile") {
    return withRouteSuspense(
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <CreatorProfilePage
          username={String(routeShell.params?.username || "")}
          onNavigate={params.navigateToPath}
        />
      </HubShell>
    );
  }
  if (routeShell.key === "hub_creator_edit") {
    return withRouteSuspense(
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <EditProfilePage onNavigate={params.navigateToPath} />
      </HubShell>
    );
  }
  if (routeShell.key === "hub_creator_dashboard") {
    return withRouteSuspense(
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <CreatorDashboardPage onNavigate={params.navigateToPath} />
      </HubShell>
    );
  }
  if (routeShell.key === "hub_explore") {
    const paramsQuery = new URLSearchParams(params.locationSearch || "");
    const query = String(paramsQuery.get("q") || "").trim();
    return withRouteSuspense(
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
    return withRouteSuspense(
      <HubShell currentPath={params.pathname || "/"} onNavigate={params.navigateToPath}>
        <FeedPage onNavigate={params.navigateToPath} />
      </HubShell>
    );
  }
  if (routeShell.key === "admin_review") return withRouteSuspense(<AdminReviewQueuePage />);
  if (routeShell.key === "marketplace") return withRouteSuspense(<MarketplacePage />);
  if (routeShell.key === "marketplace_agent_detail") {
    return withRouteSuspense(
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
  if (routeShell.key === "workspace") return withRouteSuspense(<WorkspacePage />);
  if (routeShell.key === "my_agents") return withRouteSuspense(<MyAgentsPage />);
  if (routeShell.key === "connectors") return withRouteSuspense(<ConnectorsPage />);
  if (routeShell.key === "connector_marketplace") return withRouteSuspense(<ConnectorMarketplacePage />);
  if (routeShell.key === "developer") return withRouteSuspense(<DeveloperPortalPage />);
  if (routeShell.key === "developer_docs") return withRouteSuspense(<DeveloperDocsPage />);
  if (routeShell.key === "agent_builder") return withRouteSuspense(<AgentBuilderPage />);
  if (routeShell.key === "agent_edit") {
    return withRouteSuspense(<AgentBuilderPage initialAgentId={String(routeShell.params?.agentId || "")} />);
  }
  if (routeShell.key === "agent_detail") {
    return withRouteSuspense(<AgentDetailPage agentId={String(routeShell.params?.agentId || "")} />);
  }
  if (routeShell.key === "agent_run") {
    return withRouteSuspense(
      <AgentDetailPage agentId={String(routeShell.params?.agentId || "")} initialTab="history" />,
    );
  }
  if (routeShell.key === "operations") return withRouteSuspense(<OperationsDashboardPage />);
  if (routeShell.key === "workflow_builder") return withRouteSuspense(<WorkflowBuilderPage />);
  return null;
}

export { renderStandaloneRoute };
