from __future__ import annotations

__all__ = ["build_execution_steps"]


def __getattr__(name: str):
    if name == "build_execution_steps":
        from .app import build_execution_steps

        return build_execution_steps
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
