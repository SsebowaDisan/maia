from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["run_chat_turn", "stream_chat_turn", "chunk_text_for_stream"]


def __getattr__(name: str) -> Any:
    if name in ("run_chat_turn", "stream_chat_turn"):
        module = import_module(".app", __name__)
        return getattr(module, name)
    if name == "chunk_text_for_stream":
        module = import_module(".streaming", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
