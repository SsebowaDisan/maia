"""MCP tool registry — manages connections to multiple MCP servers."""
from __future__ import annotations
import logging
from typing import Any, Generator

from .adapter import McpServerConfig, McpToolAdapter, McpToolDefinition

logger = logging.getLogger(__name__)


class McpToolRegistry:
    """Central registry for MCP tool server connections.

    Provides a unified view of all tools across all connected MCP servers,
    with discovery, invocation, and health management.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, McpToolAdapter] = {}
        self._tool_index: dict[str, tuple[McpToolAdapter, McpToolDefinition]] = {}

    # ── Server management ────────────────────────────────────────────────

    def register_server(self, config: McpServerConfig) -> int:
        """Register an MCP server and discover its tools. Returns tool count."""
        if not config.enabled:
            logger.info("MCP server %s is disabled, skipping", config.name)
            return 0
        adapter = McpToolAdapter(config)
        tools = adapter.discover_tools()
        self._adapters[config.name] = adapter
        for tool in tools:
            self._tool_index[tool.tool_id] = (adapter, tool)
        logger.info("Registered MCP server %s with %d tools", config.name, len(tools))
        return len(tools)

    def unregister_server(self, name: str) -> None:
        """Remove an MCP server and its tools."""
        adapter = self._adapters.pop(name, None)
        if adapter is None:
            return
        self._tool_index = {
            tid: (a, t) for tid, (a, t) in self._tool_index.items()
            if a.server_name != name
        }

    def refresh_server(self, name: str) -> int:
        """Re-discover tools from a server. Returns new tool count."""
        adapter = self._adapters.get(name)
        if adapter is None:
            return 0
        # Remove old tools for this server
        self._tool_index = {
            tid: (a, t) for tid, (a, t) in self._tool_index.items()
            if a.server_name != name
        }
        tools = adapter.discover_tools()
        for tool in tools:
            self._tool_index[tool.tool_id] = (adapter, tool)
        return len(tools)

    def refresh_all(self) -> dict[str, int]:
        """Re-discover tools from all servers. Returns {server: count}."""
        return {name: self.refresh_server(name) for name in list(self._adapters)}

    # ── Tool access ──────────────────────────────────────────────────────

    @property
    def servers(self) -> list[str]:
        return list(self._adapters)

    @property
    def all_tools(self) -> list[McpToolDefinition]:
        return [t for _, t in self._tool_index.values()]

    def get_tool(self, tool_id: str) -> McpToolDefinition | None:
        entry = self._tool_index.get(tool_id)
        return entry[1] if entry else None

    def has_tool(self, tool_id: str) -> bool:
        return tool_id in self._tool_index

    def tools_for_server(self, name: str) -> list[McpToolDefinition]:
        return [t for a, t in self._tool_index.values() if a.server_name == name]

    # ── Invocation ───────────────────────────────────────────────────────

    def call_tool(self, tool_id: str, arguments: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
        """Invoke an MCP tool by its composite ID."""
        entry = self._tool_index.get(tool_id)
        if entry is None:
            yield {"type": "error", "content": f"Unknown MCP tool: {tool_id}"}
            return
        adapter, tool_def = entry
        yield from adapter.call_tool(tool_def.name, arguments)

    # ── OpenAI-compatible tool schemas ───────────────────────────────────

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Export all MCP tools as OpenAI function-calling tool definitions."""
        tools = []
        for tool_def in self.all_tools:
            schema = dict(tool_def.input_schema) if tool_def.input_schema else {"type": "object", "properties": {}}
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_def.tool_id,
                    "description": tool_def.description or f"MCP tool: {tool_def.name}",
                    "parameters": schema,
                },
            })
        return tools

    # ── Health ───────────────────────────────────────────────────────────

    def health(self) -> dict[str, bool]:
        """Check health of all registered servers."""
        return {name: adapter.health_check() for name, adapter in self._adapters.items()}

    # ── Config-driven setup ──────────────────────────────────────────────

    @classmethod
    def from_configs(cls, configs: list[dict[str, Any]]) -> "McpToolRegistry":
        """Build a registry from a list of server config dicts."""
        registry = cls()
        for cfg in configs:
            try:
                config = McpServerConfig(
                    name=cfg["name"],
                    url=cfg["url"],
                    api_key=cfg.get("api_key", ""),
                    headers=cfg.get("headers", {}),
                    timeout_seconds=cfg.get("timeout_seconds", 30),
                    enabled=cfg.get("enabled", True),
                )
                registry.register_server(config)
            except Exception as exc:
                logger.warning("Failed to register MCP server %s: %s", cfg.get("name", "?"), exc)
        return registry
