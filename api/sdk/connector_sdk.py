"""B4-04 — Connector SDK.

Responsibility: Python base class that third-party developers subclass to
create custom connectors.  The SDK handles credential injection, timeout,
error normalisation, and schema generation automatically.

Usage:
    from api.sdk.connector_sdk import ConnectorBase, tool

    class MyConnector(ConnectorBase):
        connector_id = "my_connector"
        display_name = "My Service"
        description = "Connects to My Service API."
        auth_strategy = "api_key"

        @tool(description="Fetch a widget by ID.")
        def get_widget(self, widget_id: str) -> dict:
            return self._get(f"https://api.myservice.com/widgets/{widget_id}")

    # Build ConnectorDefinitionSchema from the class:
    sdk = MyConnector(credentials={"api_key": "sk-..."})
    schema = sdk.build_definition()
"""
from __future__ import annotations

import functools
import inspect
import logging
import urllib.error
import urllib.request
import json
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── @tool decorator ────────────────────────────────────────────────────────────

def tool(
    *,
    description: str = "",
    params: dict[str, Any] | None = None,
    read_only: bool = True,
) -> Callable:
    """Mark a ConnectorBase method as a connector tool.

    Args:
        description: Human-readable description (shown in LLM function spec).
        params: JSON Schema properties for the tool parameters.  Auto-derived
                from type hints if not provided.
        read_only: Whether this tool only reads data (informational).
    """
    def decorator(fn: Callable) -> Callable:
        fn.__is_connector_tool__ = True
        fn.__tool_description__ = description or fn.__doc__ or ""
        fn.__tool_params__ = params or _infer_params(fn)
        fn.__tool_read_only__ = read_only

        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            try:
                return fn(self, *args, **kwargs)
            except Exception as exc:
                logger.error("Tool %s.%s failed: %s", type(self).__name__, fn.__name__, exc)
                raise

        wrapper.__is_connector_tool__ = True
        wrapper.__tool_description__ = fn.__tool_description__
        wrapper.__tool_params__ = fn.__tool_params__
        wrapper.__tool_read_only__ = fn.__tool_read_only__
        return wrapper

    return decorator


def _infer_params(fn: Callable) -> dict[str, Any]:
    """Derive JSON Schema params dict from function signature type hints."""
    sig = inspect.signature(fn)
    props: dict[str, Any] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        ann = param.annotation
        json_type = "string"
        if ann in (int,):
            json_type = "integer"
        elif ann in (float,):
            json_type = "number"
        elif ann in (bool,):
            json_type = "boolean"
        elif ann in (list, List := "list"):
            json_type = "array"
        props[name] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


# ── ConnectorBase ──────────────────────────────────────────────────────────────

class ConnectorBase:
    """Base class for custom Maia connectors.

    Subclass this, set class attributes, and decorate methods with @tool.
    """

    connector_id: str = ""
    display_name: str = ""
    description: str = ""
    auth_strategy: str = "api_key"  # "api_key" | "oauth2" | "basic" | "none"

    def __init__(self, credentials: dict[str, Any] | None = None) -> None:
        self.credentials: dict[str, Any] = credentials or {}

    # ── Schema generation ──────────────────────────────────────────────────────

    def build_definition(self):
        """Generate a ConnectorDefinitionSchema from this class's metadata."""
        from api.schemas.connector_definition.schema import ConnectorDefinitionSchema
        from api.schemas.connector_definition.tool_schema import ToolSchema
        from api.schemas.connector_definition.auth_config import ApiKeyAuthConfig, NoAuthConfig

        tools = self._collect_tools()
        auth = (
            ApiKeyAuthConfig()
            if self.auth_strategy == "api_key"
            else NoAuthConfig()
        )

        return ConnectorDefinitionSchema(
            id=self.connector_id or type(self).__name__.lower(),
            display_name=self.display_name or type(self).__name__,
            description=self.description,
            auth=auth,
            tools=[
                ToolSchema(
                    id=f"{self.connector_id}.{name}",
                    name=name,
                    description=str(fn.__tool_description__),
                    parameters=fn.__tool_params__,
                )
                for name, fn in tools.items()
            ],
        )

    # ── HTTP helpers ───────────────────────────────────────────────────────────

    def _get(self, url: str, *, headers: dict | None = None, timeout: int = 30) -> dict[str, Any]:
        hdrs = self._base_headers()
        hdrs.update(headers or {})
        req = urllib.request.Request(url, headers=hdrs)
        return self._execute_request(req, timeout)

    def _post(self, url: str, body: dict, *, headers: dict | None = None, timeout: int = 30) -> dict[str, Any]:
        hdrs = self._base_headers()
        hdrs.update(headers or {})
        data = json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
        return self._execute_request(req, timeout)

    def _execute_request(self, req: urllib.request.Request, timeout: int) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                try:
                    return json.loads(raw)
                except Exception:
                    return {"raw": raw.decode("utf-8", errors="replace")[:4000]}
        except urllib.error.HTTPError as exc:
            raise ConnectionError(f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='ignore')[:300]}")

    def _base_headers(self) -> dict[str, str]:
        token = self.credentials.get("api_key") or self.credentials.get("access_token") or ""
        if token:
            return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        return {"Content-Type": "application/json"}

    def test_connection(self) -> bool:
        """Override to verify credentials.  Default: always True."""
        return True

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _collect_tools(self) -> dict[str, Any]:
        tools: dict[str, Any] = {}
        for name in dir(type(self)):
            fn = getattr(type(self), name, None)
            if callable(fn) and getattr(fn, "__is_connector_tool__", False):
                tools[name] = fn
        return tools
