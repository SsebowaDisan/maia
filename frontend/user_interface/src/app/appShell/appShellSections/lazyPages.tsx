import { lazy } from "react";

const lazyNamed = <TModule extends Record<string, unknown>, TKey extends keyof TModule & string>(
  loader: () => Promise<TModule>,
  exportName: TKey,
) =>
  lazy(async () => {
    const module = await loader();
    return { default: module[exportName] as React.ComponentType<any> };
  });

export const AdminReviewQueuePage = lazyNamed(() => import("../../pages/AdminReviewQueuePage"), "AdminReviewQueuePage");
export const MarketplacePage = lazyNamed(() => import("../../pages/MarketplacePage"), "MarketplacePage");
export const MarketplaceAgentDetailPage = lazyNamed(
  () => import("../../pages/MarketplaceAgentDetailPage"),
  "MarketplaceAgentDetailPage",
);
export const WorkspacePage = lazyNamed(() => import("../../pages/WorkspacePage"), "WorkspacePage");
export const MyAgentsPage = lazyNamed(() => import("../../pages/MyAgentsPage"), "MyAgentsPage");
export const ConnectorsPage = lazyNamed(() => import("../../pages/ConnectorsPage"), "ConnectorsPage");
export const ConnectorMarketplacePage = lazyNamed(
  () => import("../../pages/ConnectorMarketplacePage"),
  "ConnectorMarketplacePage",
);
export const DeveloperPortalPage = lazyNamed(() => import("../../pages/DeveloperPortalPage"), "DeveloperPortalPage");
export const DeveloperDocsPage = lazyNamed(() => import("../../pages/DeveloperDocsPage"), "DeveloperDocsPage");
export const AgentBuilderPage = lazyNamed(() => import("../../pages/AgentBuilderPage"), "AgentBuilderPage");
export const AgentDetailPage = lazyNamed(() => import("../../pages/AgentDetailPage"), "AgentDetailPage");
export const OperationsDashboardPage = lazyNamed(
  () => import("../../pages/OperationsDashboardPage"),
  "OperationsDashboardPage",
);
export const WorkflowBuilderPage = lazyNamed(() => import("../../pages/WorkflowBuilderPage"), "WorkflowBuilderPage");
export const MarketplaceBrowsePage = lazyNamed(
  () => import("../../pages/hub/MarketplaceBrowsePage"),
  "MarketplaceBrowsePage",
);
export const HubAgentDetailPage = lazyNamed(() => import("../../pages/hub/HubAgentDetailPage"), "HubAgentDetailPage");
export const TeamDetailPage = lazyNamed(() => import("../../pages/hub/TeamDetailPage"), "TeamDetailPage");
export const CreatorProfilePage = lazyNamed(
  () => import("../../pages/hub/CreatorProfilePage"),
  "CreatorProfilePage",
);
export const EditProfilePage = lazyNamed(() => import("../../pages/hub/EditProfilePage"), "EditProfilePage");
export const CreatorDashboardPage = lazyNamed(
  () => import("../../pages/hub/CreatorDashboardPage"),
  "CreatorDashboardPage",
);
export const ExplorePage = lazyNamed(() => import("../../pages/hub/ExplorePage"), "ExplorePage");
export const FeedPage = lazyNamed(() => import("../../pages/hub/FeedPage"), "FeedPage");
export const SearchResultsPage = lazyNamed(() => import("../../pages/hub/SearchResultsPage"), "SearchResultsPage");
