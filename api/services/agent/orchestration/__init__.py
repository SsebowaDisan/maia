from __future__ import annotations

__all__ = ["AgentOrchestrator", "get_orchestrator"]


def __getattr__(name: str):
    if name in {"AgentOrchestrator", "get_orchestrator"}:
        from .app import AgentOrchestrator, get_orchestrator

        return {
            "AgentOrchestrator": AgentOrchestrator,
            "get_orchestrator": get_orchestrator,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
