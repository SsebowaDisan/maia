from __future__ import annotations

from typing import Any

__all__ = ["ConnectorRegistry", "get_connector_registry"]


def __getattr__(name: str) -> Any:
    if name in {"ConnectorRegistry", "get_connector_registry"}:
        from .registry import ConnectorRegistry, get_connector_registry

        return ConnectorRegistry if name == "ConnectorRegistry" else get_connector_registry
    raise AttributeError(name)
