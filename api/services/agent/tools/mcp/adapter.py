"""MCP (Model Context Protocol) adapter — connects to external MCP tool servers."""
from __future__ import annotations
import json
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Generator

logger = logging.getLogger(__name__)


@dataclass
class McpServerConfig:
    """Configuration for an MCP tool server connection."""
    name: str
    url: str  # e.g. "http://localhost:3001" or "https://mcp.example.com"
    api_key: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    enabled: bool = True


@dataclass
class McpToolDefinition:
    """A tool definition fetched from an MCP server."""
    server_name: str
    name: str
    description: str
    input_schema: dict[str, Any]
    # Composite ID used in Maia's tool registry
    tool_id: str = ""

    def __post_init__(self) -> None:
        if not self.tool_id:
            self.tool_id = f"mcp:{self.server_name}:{self.name}"


class McpToolAdapter:
    """Adapter that speaks MCP protocol to discover and invoke external tools.

    Implements the MCP client side:
      - GET  /tools/list        → discover available tools
      - POST /tools/call        → invoke a tool
      - GET  /resources/list    → discover resources (optional)
    """

    def __init__(self, config: McpServerConfig) -> None:
        self._config = config
        self._tools: list[McpToolDefinition] = []
        self._discovered = False

    @property
    def server_name(self) -> str:
        return self._config.name

    @property
    def base_url(self) -> str:
        return self._config.url.rstrip("/")

    def _request_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        headers.update(self._config.headers)
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        return headers

    def _http_get(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers=self._request_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self._config.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            logger.warning("MCP GET %s failed: %s", url, exc)
            raise ConnectionError(f"MCP server {self._config.name} unreachable: {exc}") from exc

    def _http_post(self, path: str, body: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._request_headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self._config.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            logger.warning("MCP POST %s failed: %s", url, exc)
            raise ConnectionError(f"MCP server {self._config.name} unreachable: {exc}") from exc

    # ── Discovery ────────────────────────────────────────────────────────

    def discover_tools(self) -> list[McpToolDefinition]:
        """Fetch the tool list from the MCP server."""
        try:
            resp = self._http_get("/tools/list")
        except ConnectionError:
            logger.warning("Cannot discover tools from MCP server %s", self._config.name)
            return []

        tools_data = resp.get("tools", resp) if isinstance(resp, dict) else resp
        if not isinstance(tools_data, list):
            logger.warning("Unexpected /tools/list response from %s", self._config.name)
            return []

        self._tools = []
        for entry in tools_data:
            if not isinstance(entry, dict) or "name" not in entry:
                continue
            self._tools.append(McpToolDefinition(
                server_name=self._config.name,
                name=entry["name"],
                description=entry.get("description", ""),
                input_schema=entry.get("inputSchema", entry.get("input_schema", {})),
            ))
        self._discovered = True
        logger.info("Discovered %d tools from MCP server %s", len(self._tools), self._config.name)
        return list(self._tools)

    @property
    def tools(self) -> list[McpToolDefinition]:
        if not self._discovered:
            self.discover_tools()
        return list(self._tools)

    # ── Invocation ───────────────────────────────────────────────────────

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
        """Invoke a tool on the MCP server. Yields trace events."""
        yield {"type": "mcp_call_start", "server": self._config.name, "tool": tool_name}

        try:
            resp = self._http_post("/tools/call", {
                "name": tool_name,
                "arguments": arguments,
            })
        except ConnectionError as exc:
            yield {"type": "error", "content": f"MCP call failed: {exc}"}
            return

        # MCP response may contain content array or direct result
        if isinstance(resp, dict):
            content = resp.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type", "text")
                        if block_type == "text":
                            yield {"type": "result", "content": block.get("text", "")}
                        elif block_type == "image":
                            yield {"type": "image", "content": block.get("data", ""), "mime": block.get("mimeType", "")}
                        elif block_type == "resource":
                            yield {"type": "resource", "content": json.dumps(block)}
                        else:
                            yield {"type": "result", "content": json.dumps(block)}
            elif isinstance(content, str):
                yield {"type": "result", "content": content}
            else:
                yield {"type": "result", "content": json.dumps(resp)}

            if resp.get("isError"):
                yield {"type": "error", "content": f"MCP tool returned error: {resp.get('content', '')}"}
        else:
            yield {"type": "result", "content": str(resp)}

    # ── Resources (optional) ─────────────────────────────────────────────

    def discover_resources(self) -> list[dict[str, Any]]:
        """Fetch the resource list from the MCP server (optional endpoint)."""
        try:
            resp = self._http_get("/resources/list")
            return resp.get("resources", []) if isinstance(resp, dict) else []
        except ConnectionError:
            return []

    # ── Health ───────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Check if the MCP server is reachable."""
        try:
            self._http_get("/tools/list")
            return True
        except ConnectionError:
            return False
