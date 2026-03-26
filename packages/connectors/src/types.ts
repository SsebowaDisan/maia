/**
 * Connector types — shared interface for all connectors.
 */

export type AuthKind = "oauth2" | "api_key" | "token" | "basic" | "none";

export interface ConnectorConfig {
  /** Unique connector ID (e.g., "gmail", "slack"). */
  id: string;
  /** Human-readable name. */
  name: string;
  /** What this connector does. */
  description: string;
  /** Auth type required. */
  authKind: AuthKind;
  /** API credentials — provided by the user. */
  credentials: Record<string, string>;
  /** Base URL for API calls. */
  baseUrl?: string;
}

export interface ConnectorTool {
  /** Tool ID (e.g., "send_email", "create_issue"). */
  id: string;
  /** Human-readable name. */
  name: string;
  /** What this tool does. */
  description: string;
  /** JSON Schema for input parameters. */
  inputSchema: Record<string, any>;
  /** The function that executes this tool. */
  execute: (params: Record<string, any>, config: ConnectorConfig) => Promise<ToolResult>;
}

export interface ToolResult {
  success: boolean;
  data?: any;
  error?: string;
  /** Summary for ACP event rendering. */
  summary: string;
}

export interface ConnectorDefinition {
  id: string;
  name: string;
  description: string;
  authKind: AuthKind;
  category: string;
  iconEmoji: string;
  tools: ConnectorTool[];
  /** Required credential fields (e.g., ["api_key"], ["client_id", "client_secret"]). */
  requiredCredentials: string[];
  /** Documentation URL. */
  docsUrl?: string;
}