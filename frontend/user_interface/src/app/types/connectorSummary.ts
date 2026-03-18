type ConnectorAuthType =
  | "oauth2"
  | "api_key"
  | "basic"
  | "bearer"
  | "service_identity"
  | "none";

type ConnectorStatus =
  | "Connected"
  | "Not connected"
  | "Needs permission"
  | "Expired";

type ConnectorSetupMode =
  | "oauth_popup"
  | "manual_credentials"
  | "service_identity"
  | "none";

type ConnectorSceneFamily =
  | "email"
  | "sheet"
  | "document"
  | "api"
  | "browser"
  | "chat"
  | "crm"
  | "support"
  | "commerce";

type ConnectorSubServiceStatus =
  | "Connected"
  | "Needs setup"
  | "Needs permission"
  | "Disabled";

type ConnectorSubService = {
  id: string;
  label: string;
  description: string;
  status: ConnectorSubServiceStatus;
  brandSlug?: string;
  sceneFamily?: ConnectorSceneFamily;
  requiredScopes?: string[];
};

type ConnectorSummary = {
  id: string;
  name: string;
  description: string;
  authType: ConnectorAuthType;
  status: ConnectorStatus;
  tools: string[];
  actionsCount?: number;
  statusMessage?: string;
  brandSlug?: string;
  suiteId?: string;
  suiteLabel?: string;
  serviceOrder?: number;
  setupMode?: ConnectorSetupMode;
  sceneFamily?: ConnectorSceneFamily;
  visibility?: "user_facing" | "internal";
  subServices?: ConnectorSubService[];
};

export type {
  ConnectorAuthType,
  ConnectorSceneFamily,
  ConnectorSetupMode,
  ConnectorStatus,
  ConnectorSubService,
  ConnectorSubServiceStatus,
  ConnectorSummary,
};
