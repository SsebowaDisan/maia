type ConnectorSubService = {
  id: string;
  label: string;
  description: string;
  status: "Connected" | "Needs permission" | "Disabled";
};

type ConnectorSummary = {
  id: string;
  name: string;
  description: string;
  authType: "oauth2" | "api_key" | "basic" | "none";
  status: "Connected" | "Not connected" | "Expired";
  tools: string[];
  subServices?: ConnectorSubService[];
};

export type { ConnectorSummary, ConnectorSubService };
