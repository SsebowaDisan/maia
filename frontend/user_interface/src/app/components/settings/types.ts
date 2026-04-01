import type {
  AgentLiveEvent,
  ConnectorCredentialRecord,
  GoogleOAuthStatus,
} from "../../../api/client";
import type {
  IntegrationStatus,
  OllamaModelRecord,
  OllamaQuickstart,
  OllamaStatus,
} from "../../../api/integrations";
import type { ConnectorDefinition } from "./connectorDefinitions";

export type SettingsTabId = "general" | "models" | "access";

export type SettingsTabItem = {
  id: SettingsTabId;
  label: string;
  subtitle: string;
};

export const SETTINGS_TABS: SettingsTabItem[] = [
  {
    id: "general",
    label: "General",
    subtitle: "Workspace preferences and system status.",
  },
  {
    id: "models",
    label: "Models",
    subtitle: "Local model runtime and indexing embeddings.",
  },
  {
    id: "access",
    label: "Access",
    subtitle: "Admins, users, and workspace permissions.",
  },
];

export type GoogleToolHealthItem = {
  id: string;
  label: string;
  ok: boolean;
  message: string;
};

export type ManualConnectorState = {
  healthMap: Record<string, { ok: boolean; message: string }>;
  credentialMap: Record<string, ConnectorCredentialRecord>;
  draftValues: Record<string, Record<string, string>>;
  savingConnectorId: string | null;
  statusMessage: string;
  connectors: ConnectorDefinition[];
};

export type SharedSettingsState = {
  loading: boolean;
  oauthStatus: string;
  googleOAuthStatus: GoogleOAuthStatus;
  googleToolHealth: GoogleToolHealthItem[];
  liveEvents: AgentLiveEvent[];
  mapsStatus: IntegrationStatus;
  braveStatus: IntegrationStatus;
  mapsKeyInput: string;
  braveKeyInput: string;
  ollamaStatus: OllamaStatus;
  ollamaModels: OllamaModelRecord[];
  ollamaQuickstart: OllamaQuickstart | null;
  ollamaBaseUrlInput: string;
  ollamaModelInput: string;
  ollamaEmbeddingInput: string;
  ollamaBusyAction:
    | "config"
    | "start"
    | "pull"
    | "select"
    | "select_embedding"
    | "apply_all"
    | "refresh"
    | "onboarding"
    | null;
  ollamaProgress: { status: string; percent: number } | null;
  ollamaMessage: string;
  manual: ManualConnectorState;
};
