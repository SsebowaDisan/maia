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
from enum import Enum
from typing import Any, Callable, get_args, get_origin, get_type_hints

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
    type_hints = get_type_hints(fn)
    props: dict[str, Any] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        props[name] = _annotation_to_schema(type_hints.get(name, param.annotation))
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


def _annotation_to_schema(annotation: Any) -> dict[str, Any]:
    if annotation is inspect.Parameter.empty:
        return {"type": "string"}

    origin = get_origin(annotation)
    args = [arg for arg in get_args(annotation) if arg is not type(None)]
    if origin is not None and args:
        if origin in (list, tuple, set):
            item_schema = _annotation_to_schema(args[0]) if args else {"type": "string"}
            return {"type": "array", "items": {"type": item_schema.get("type", "string")}}
        if origin is dict:
            return {"type": "object"}
        return _annotation_to_schema(args[0])

    if annotation in (str,):
        return {"type": "string"}
    if annotation in (int,):
        return {"type": "integer"}
    if annotation in (float,):
        return {"type": "number"}
    if annotation in (bool,):
        return {"type": "boolean"}
    if annotation in (list, tuple, set):
        return {"type": "array", "items": {"type": "string"}}
    if annotation in (dict,):
        return {"type": "object"}
    if inspect.isclass(annotation) and issubclass(annotation, Enum):
        enum_values = [str(member.value) for member in annotation]
        return {"type": "string", "enum": enum_values}
    return {"type": "string"}


def _normalize_tool_parameters(raw_params: Any) -> list[Any]:
    from api.schemas.connector_definition.tool_schema import ToolParameter, ToolParameterType

    if raw_params is None:
        return []

    if isinstance(raw_params, list):
        normalized: list[ToolParameter] = []
        for item in raw_params:
            if isinstance(item, ToolParameter):
                normalized.append(item)
                continue
            if isinstance(item, dict):
                normalized.append(ToolParameter(**item))
        return normalized

    if not isinstance(raw_params, dict):
        return []

    schema = dict(raw_params)
    if schema.get("type") == "object" and isinstance(schema.get("properties"), dict):
        properties = dict(schema.get("properties") or {})
        required_names = {
            str(name).strip()
            for name in (schema.get("required") or [])
            if str(name).strip()
        }
    else:
        properties = schema
        required_names = set()

    normalized_params: list[ToolParameter] = []
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            prop = {"type": "string"}
        param_type = _coerce_parameter_type(prop.get("type"))
        items = prop.get("items") if isinstance(prop.get("items"), dict) else {}
        items_type = (
            _coerce_parameter_type(items.get("type"))
            if param_type == ToolParameterType.array and items.get("type")
            else None
        )
        nested_properties = (
            dict(prop.get("properties") or {})
            if param_type == ToolParameterType.object and isinstance(prop.get("properties"), dict)
            else None
        )
        normalized_params.append(
            ToolParameter(
                name=str(name),
                type=param_type,
                description=str(prop.get("description") or ""),
                required=str(name) in required_names if required_names else bool(prop.get("required", True)),
                default=prop.get("default"),
                enum=[str(item) for item in prop.get("enum", [])] if isinstance(prop.get("enum"), list) else None,
                items_type=items_type,
                properties=nested_properties,
            )
        )
    return normalized_params


def _coerce_parameter_type(value: Any):
    from api.schemas.connector_definition.tool_schema import ToolParameterType

    text = str(value or "string").strip().lower()
    try:
        return ToolParameterType(text)
    except Exception:
        return ToolParameterType.string


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
        from api.schemas.connector_definition.tool_schema import ToolActionClass, ToolSchema
        from api.schemas.connector_definition.auth_config import ApiKeyAuthConfig, NoAuthConfig

        tools = self._collect_tools()
        auth = (
            ApiKeyAuthConfig()
            if self.auth_strategy == "api_key"
            else NoAuthConfig()
        )

        return ConnectorDefinitionSchema(
            id=self.connector_id or type(self).__name__.lower(),
            name=self.display_name or type(self).__name__,
            description=self.description,
            auth=auth,
            tools=[
                ToolSchema(
                    id=f"{self.connector_id}.{name}",
                    name=name,
                    description=str(fn.__tool_description__),
                    parameters=_normalize_tool_parameters(fn.__tool_params__),
                    action_class=(
                        ToolActionClass.read
                        if bool(getattr(fn, "__tool_read_only__", True))
                        else ToolActionClass.execute
                    ),
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
