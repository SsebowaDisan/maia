/**
 * @maia/connectors — 50+ pre-built connectors for AI agents.
 *
 * Usage:
 *   import { getAllConnectors, getConnector } from '@maia/connectors';
 *
 *   const gmail = getConnector("gmail");
 *   console.log(gmail.tools);  // send_email, search_email, ...
 */

export type {
  ConnectorConfig,
  ConnectorTool,
  ConnectorDefinition,
  ToolResult,
  AuthKind,
} from "./types";

export { BaseConnector } from "./base";

export {
  getAllConnectors,
  getConnector,
  getConnectorsByCategory,
  getCategories,
  CATALOG,
} from "./catalog";