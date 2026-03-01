from __future__ import annotations

from importlib import import_module

__all__ = ["BaseTool", "ComponentTool", "GoogleSearchTool", "WikipediaTool", "LLMTool"]

_EXPORTS = {
    "BaseTool": (".base", "BaseTool"),
    "ComponentTool": (".base", "ComponentTool"),
    "GoogleSearchTool": (".google", "GoogleSearchTool"),
    "WikipediaTool": (".wikipedia", "WikipediaTool"),
    "LLMTool": (".llm", "LLMTool"),
}


def __getattr__(name: str):
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
