"""MCP (Model Context Protocol) server management API.

Provides endpoints for registering external MCP tool servers, discovering
their tools, invoking tools, and checking health status.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from api.services.agent.tools.mcp import McpServerConfig, McpToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

# ---------------------------------------------------------------------------
# Singleton registry
# ---------------------------------------------------------------------------

_mcp_registry: McpToolRegistry | None = None


def get_mcp_registry() -> McpToolRegistry:
    global _mcp_registry
    if _mcp_registry is None:
        _mcp_registry = McpToolRegistry()
    return _mcp_registry


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterServerBody(BaseModel):
    name: str
    url: str
    api_key: str = ""
    headers: dict[str, str] = {}
    timeout_seconds: int = 30
    enabled: bool = True


class ServerInfo(BaseModel):
    name: str
    url: str
    tool_count: int
    enabled: bool


class ToolInfo(BaseModel):
    tool_id: str
    server_name: str
    name: str
    description: str
    input_schema: dict[str, Any]


class CallToolBody(BaseModel):
    arguments: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Routes — server management
# ---------------------------------------------------------------------------


@router.get("/servers", response_model=list[ServerInfo])
def list_servers():
    """List registered MCP servers and their tool counts."""
    registry = get_mcp_registry()
    results = []
    for name in registry.servers:
        tools = registry.tools_for_server(name)
        # Recover the URL from the adapter
        adapter = registry._adapters.get(name)
        url = adapter.base_url if adapter else ""
        enabled = adapter._config.enabled if adapter else True
        results.append(ServerInfo(
            name=name,
            url=url,
            tool_count=len(tools),
            enabled=enabled,
        ))
    return results


@router.post("/servers", response_model=ServerInfo, status_code=status.HTTP_201_CREATED)
def register_server(body: RegisterServerBody):
    """Register a new MCP server and discover its tools."""
    registry = get_mcp_registry()
    if body.name in registry.servers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"MCP server '{body.name}' is already registered.",
        )
    config = McpServerConfig(
        name=body.name,
        url=body.url,
        api_key=body.api_key,
        headers=body.headers,
        timeout_seconds=body.timeout_seconds,
        enabled=body.enabled,
    )
    tool_count = registry.register_server(config)
    return ServerInfo(
        name=body.name,
        url=body.url,
        tool_count=tool_count,
        enabled=body.enabled,
    )


@router.delete("/servers/{name}")
def unregister_server(name: str):
    """Unregister an MCP server and remove its tools."""
    registry = get_mcp_registry()
    if name not in registry.servers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP server '{name}' not found.",
        )
    registry.unregister_server(name)
    return {"deleted": True}


@router.post("/servers/{name}/refresh")
def refresh_server(name: str):
    """Re-discover tools from an MCP server."""
    registry = get_mcp_registry()
    if name not in registry.servers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP server '{name}' not found.",
        )
    tool_count = registry.refresh_server(name)
    return {"server": name, "tool_count": tool_count}


# ---------------------------------------------------------------------------
# Routes — tools
# ---------------------------------------------------------------------------


@router.get("/tools", response_model=list[ToolInfo])
def list_tools():
    """List all discovered MCP tools across all servers."""
    registry = get_mcp_registry()
    return [
        ToolInfo(
            tool_id=t.tool_id,
            server_name=t.server_name,
            name=t.name,
            description=t.description,
            input_schema=t.input_schema,
        )
        for t in registry.all_tools
    ]


@router.post("/tools/{tool_id:path}/call")
def call_tool(tool_id: str, body: CallToolBody):
    """Invoke an MCP tool by its composite ID."""
    registry = get_mcp_registry()
    if not registry.has_tool(tool_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP tool '{tool_id}' not found.",
        )
    events = list(registry.call_tool(tool_id, body.arguments))
    # Separate errors from results
    errors = [e for e in events if e.get("type") == "error"]
    results = [e for e in events if e.get("type") != "error" and e.get("type") != "mcp_call_start"]
    if errors and not results:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=errors[0].get("content", "MCP tool call failed."),
        )
    return {"tool_id": tool_id, "results": results, "errors": errors}


# ---------------------------------------------------------------------------
# Routes — health
# ---------------------------------------------------------------------------


@router.get("/health")
def mcp_health():
    """Health check all registered MCP servers."""
    registry = get_mcp_registry()
    server_health = registry.health()
    all_ok = all(server_health.values()) if server_health else True
    return {
        "healthy": all_ok,
        "servers": server_health,
    }
