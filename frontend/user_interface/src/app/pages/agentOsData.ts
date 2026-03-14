export type AgentStatus = "active" | "paused" | "error";
export type ConnectorAuthType = "oauth2" | "api_key" | "basic" | "none";
export type ConnectorState = "Connected" | "Not connected" | "Expired";
export type TriggerType = "conversational" | "scheduled" | "event";

export type AgentSummary = {
  id: string;
  name: string;
  description: string;
  status: AgentStatus;
  lastRun: string;
  totalRuns: number;
  tools: string[];
};

export type ConnectorSummary = {
  id: string;
  name: string;
  description: string;
  authType: ConnectorAuthType;
  status: ConnectorState;
  tools: string[];
};

export type AgentRunRecord = {
  id: string;
  agentId: string;
  triggerType: TriggerType;
  status: "success" | "failed" | "cancelled";
  durationMs: number;
  llmCostUsd: number;
  startedAt: string;
  outputSummary: string;
  errorType?: string;
  errorMessage?: string;
};

export type MarketplaceAgentRecord = {
  id: string;
  name: string;
  publisher: string;
  description: string;
  rating: number;
  installs: number;
  pricing: "free" | "paid" | "enterprise";
  tags: string[];
  requiredConnectors: string[];
  versions: string[];
};

export const AGENT_OS_CONNECTORS: ConnectorSummary[] = [
  {
    id: "google_workspace",
    name: "Google Workspace",
    description: "Mail, Drive, Calendar, and docs automation.",
    authType: "oauth2",
    status: "Connected",
    tools: ["gmail.send", "gdrive.read_file", "gcalendar.create_event"],
  },
  {
    id: "slack",
    name: "Slack",
    description: "Team communication and channel operations.",
    authType: "api_key",
    status: "Connected",
    tools: ["slack.send_message", "slack.list_channels"],
  },
  {
    id: "salesforce",
    name: "Salesforce",
    description: "CRM records, pipelines, and account updates.",
    authType: "oauth2",
    status: "Expired",
    tools: ["crm.get_deal", "crm.update_deal", "crm.list_deals_by_stage"],
  },
  {
    id: "notion",
    name: "Notion",
    description: "Page creation and workspace documentation workflows.",
    authType: "api_key",
    status: "Not connected",
    tools: ["notion.read_page", "notion.create_page", "notion.update_page"],
  },
  {
    id: "github",
    name: "GitHub",
    description: "Issues, PRs, and repository collaboration.",
    authType: "oauth2",
    status: "Connected",
    tools: ["vcs.create_pr", "vcs.list_issues", "vcs.create_issue"],
  },
];

export const AGENT_OS_AGENTS: AgentSummary[] = [
  {
    id: "proposal-writer",
    name: "Proposal Writer",
    description: "Builds structured sales proposals from CRM and product context.",
    status: "active",
    lastRun: "2026-03-13T10:42:00Z",
    totalRuns: 127,
    tools: ["crm.get_deal", "gdrive.read_file", "gmail.send"],
  },
  {
    id: "deal-summary",
    name: "Deal Summary",
    description: "Summarizes pipeline changes and notable deal risks.",
    status: "active",
    lastRun: "2026-03-13T09:15:00Z",
    totalRuns: 88,
    tools: ["crm.list_deals_by_stage", "slack.send_message"],
  },
  {
    id: "ops-alerts",
    name: "Ops Alerts",
    description: "Monitors run failures and sends escalation notifications.",
    status: "paused",
    lastRun: "2026-03-12T18:03:00Z",
    totalRuns: 42,
    tools: ["slack.send_message", "http.post"],
  },
];

export const AGENT_OS_RUNS: AgentRunRecord[] = [
  {
    id: "run_1001",
    agentId: "proposal-writer",
    triggerType: "conversational",
    status: "success",
    durationMs: 22100,
    llmCostUsd: 0.18,
    startedAt: "2026-03-13T10:42:00Z",
    outputSummary: "Generated a full proposal draft with pricing options.",
  },
  {
    id: "run_1002",
    agentId: "deal-summary",
    triggerType: "scheduled",
    status: "success",
    durationMs: 9800,
    llmCostUsd: 0.07,
    startedAt: "2026-03-13T09:15:00Z",
    outputSummary: "Shared daily pipeline update to sales leadership channel.",
  },
  {
    id: "run_1003",
    agentId: "ops-alerts",
    triggerType: "event",
    status: "failed",
    durationMs: 6500,
    llmCostUsd: 0.03,
    startedAt: "2026-03-12T18:03:00Z",
    outputSummary: "Webhook payload validation failed before alert dispatch.",
    errorType: "credential_expired",
    errorMessage: "Slack token rejected by API gateway.",
  },
];

export const AGENT_OS_MARKETPLACE: MarketplaceAgentRecord[] = [
  {
    id: "marketplace_sales_pitch",
    name: "Sales Pitch Architect",
    publisher: "Axon Labs",
    description: "Creates context-aware outbound messaging with objection handling.",
    rating: 4.8,
    installs: 1740,
    pricing: "paid",
    tags: ["sales", "outbound", "proposal"],
    requiredConnectors: ["salesforce", "gmail", "slack"],
    versions: ["1.0.0", "1.1.0", "1.2.0"],
  },
  {
    id: "marketplace_support_triage",
    name: "Support Triage Assistant",
    publisher: "Maia Verified",
    description: "Classifies incoming support tickets and drafts first responses.",
    rating: 4.5,
    installs: 2390,
    pricing: "free",
    tags: ["support", "triage"],
    requiredConnectors: ["slack", "notion"],
    versions: ["2.3.0", "2.4.0"],
  },
  {
    id: "marketplace_revops_digest",
    name: "RevOps Weekly Digest",
    publisher: "Signal River",
    description: "Compiles weekly revenue operations performance with annotated risks.",
    rating: 4.2,
    installs: 950,
    pricing: "enterprise",
    tags: ["revops", "analytics", "weekly"],
    requiredConnectors: ["salesforce", "google_workspace"],
    versions: ["0.9.0", "1.0.0"],
  },
];

export function formatRelativeTime(isoLike: string): string {
  const date = new Date(isoLike);
  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }
  const diffMs = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) {
    return "just now";
  }
  if (diffMins < 60) {
    return `${diffMins}m ago`;
  }
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

