"""ToolExecutor — bridges ConnectorBinding credentials to the existing AgentTool system.

Responsibility: resolve tool_id → connector → decrypted credentials → execute.
Enforces permission checks, timeout, and structured result contract.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from api.services.connectors import vault
from api.services.connectors.bindings import assert_tool_allowed, mark_last_used

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 30


class ToolResult:
    __slots__ = ("tool_id", "success", "data", "error", "latency_ms")

    def __init__(
        self,
        tool_id: str,
        *,
        success: bool,
        data: Any = None,
        error: str = "",
        latency_ms: float = 0.0,
    ) -> None:
        self.tool_id = tool_id
        self.success = success
        self.data = data
        self.error = error
        self.latency_ms = latency_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "latency_ms": round(self.latency_ms, 1),
        }


def execute_tool(
    tool_id: str,
    tenant_id: str,
    agent_id: str,
    params: dict[str, Any],
    *,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
) -> ToolResult:
    """Execute a tool for a given tenant and agent.

    1. Permission check via bindings.
    2. Resolve credentials from vault.
    3. Dispatch to the appropriate handler.
    4. Return a ToolResult.
    """
    # ── Permission check ──────────────────────────────────────────────────────
    try:
        assert_tool_allowed(tenant_id, agent_id, tool_id)
    except PermissionError as exc:
        return ToolResult(tool_id, success=False, error=str(exc))

    # ── Resolve credentials ───────────────────────────────────────────────────
    connector_id = tool_id.split(".")[0] if "." in tool_id else tool_id
    credentials = vault.get_credential(tenant_id, connector_id)

    # ── Execute ───────────────────────────────────────────────────────────────
    start = time.perf_counter()
    try:
        handler = _resolve_handler(tool_id)
        if handler is None:
            return ToolResult(
                tool_id,
                success=False,
                error=f"No handler registered for tool '{tool_id}'.",
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        data = handler(
            params=params,
            credentials=credentials,
            timeout_seconds=timeout_seconds,
            tenant_id=tenant_id,
            agent_id=agent_id,
        )
        mark_last_used(tenant_id, connector_id)
        return ToolResult(
            tool_id,
            success=True,
            data=data,
            latency_ms=(time.perf_counter() - start) * 1000,
        )

    except TimeoutError as exc:
        return ToolResult(
            tool_id,
            success=False,
            error=f"Tool '{tool_id}' timed out after {timeout_seconds}s.",
            latency_ms=(time.perf_counter() - start) * 1000,
        )
    except Exception as exc:
        logger.warning("Tool execution error for %s: %s", tool_id, exc)
        return ToolResult(
            tool_id,
            success=False,
            error=str(exc)[:500],
            latency_ms=(time.perf_counter() - start) * 1000,
        )


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------
# Each handler is a callable: (params, credentials, timeout_seconds) -> Any
# Handlers are registered lazily to avoid import-time side effects.

_HANDLERS: dict[str, Any] = {}


def register_handler(tool_id: str, handler) -> None:
    """Register a callable as the handler for a specific tool_id."""
    _HANDLERS[tool_id] = handler


def _resolve_handler(tool_id: str):
    """Return the handler for a tool_id, or None if not registered."""
    if tool_id in _HANDLERS:
        return _HANDLERS[tool_id]

    # Lazy-load built-in tool handlers on first call.
    _load_builtin_handlers()
    return _HANDLERS.get(tool_id)


_builtins_loaded = False


def _load_builtin_handlers() -> None:
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True

    try:
        from api.services.connectors.tools import http_tools
        http_tools.register(_HANDLERS)
    except Exception:
        logger.debug("http_tools not loaded", exc_info=True)

    try:
        from api.services.connectors.tools import computer_use_tool

        class _CUAdapter:
            """Adapt computer_use_tool._run_task to the standard handler signature."""
            def __call__(self, params, credentials, timeout_seconds, tenant_id="", agent_id="", **_kw):
                return computer_use_tool._run_task(params, tenant_id=tenant_id, agent_id=agent_id)

        _HANDLERS[computer_use_tool.TOOL_ID] = _CUAdapter()
    except Exception:
        logger.debug("computer_use_tool not loaded", exc_info=True)
