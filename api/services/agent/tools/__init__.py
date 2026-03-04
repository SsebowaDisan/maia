from __future__ import annotations

__all__ = ["ToolRegistry", "get_tool_registry"]


def __getattr__(name: str):
    if name in {"ToolRegistry", "get_tool_registry"}:
        from .registry import ToolRegistry, get_tool_registry

        return {
            "ToolRegistry": ToolRegistry,
            "get_tool_registry": get_tool_registry,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
