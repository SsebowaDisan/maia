/**
 * BaseConnector — abstract base class for all connectors.
 * Handles auth, ACP event emission, and error wrapping.
 */

import type { ACPEvent } from "@maia/acp";
import { envelope, activity } from "@maia/acp";
import type { ConnectorConfig, ConnectorTool, ToolResult, ConnectorDefinition } from "./types";

export abstract class BaseConnector {
  readonly config: ConnectorConfig;
  protected events: ACPEvent[] = [];
  protected runId: string = "";
  protected agentId: string = "agent://connector";

  constructor(config: ConnectorConfig) {
    this.config = config;
  }

  /** Set the agent context for ACP events. */
  setContext(agentId: string, runId: string): void {
    this.agentId = agentId;
    this.runId = runId;
  }

  /** Execute a tool by ID. */
  async executeTool(toolId: string, params: Record<string, any>): Promise<{ result: ToolResult; events: ACPEvent[] }> {
    const tool = this.getTools().find((t) => t.id === toolId);
    if (!tool) {
      return {
        result: { success: false, error: `Unknown tool: ${toolId}`, summary: `Tool ${toolId} not found` },
        events: [],
      };
    }

    // Emit: tool started
    const startEvent = this.emit(activity({
      agentId: this.agentId,
      activity: "tool_calling",
      detail: `${this.config.name}: ${tool.name}`,
      tool: { tool_id: toolId, tool_name: tool.name, connector_id: this.config.id, status: "started" },
    }));

    try {
      const result = await tool.execute(params, this.config);

      // Emit: tool completed
      const endEvent = this.emit(activity({
        agentId: this.agentId,
        activity: "tool_calling",
        detail: result.summary,
        tool: {
          tool_id: toolId,
          tool_name: tool.name,
          connector_id: this.config.id,
          output_summary: result.summary,
          status: result.success ? "completed" : "failed",
        },
      }));

      return { result, events: [startEvent, endEvent] };
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : String(err);
      const errorEvent = this.emit(activity({
        agentId: this.agentId,
        activity: "error",
        detail: `${this.config.name} error: ${errorMsg}`,
        tool: { tool_id: toolId, tool_name: tool.name, connector_id: this.config.id, status: "failed" },
      }));

      return {
        result: { success: false, error: errorMsg, summary: `Failed: ${errorMsg}` },
        events: [startEvent, errorEvent],
      };
    }
  }

  /** Get all tools this connector provides. */
  abstract getTools(): ConnectorTool[];

  /** Get the connector definition. */
  abstract getDefinition(): ConnectorDefinition;

  protected emit(payload: any): ACPEvent {
    const event = envelope(this.agentId, this.runId, "event", payload);
    this.events.push(event);
    return event;
  }
}