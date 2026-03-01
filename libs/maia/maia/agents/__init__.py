from __future__ import annotations

from importlib import import_module

__all__ = [
    # agent
    "BaseAgent",
    "ReactAgent",
    "RewooAgent",
    "LangchainAgent",
    # tool
    "BaseTool",
    "ComponentTool",
    "GoogleSearchTool",
    "WikipediaTool",
    "LLMTool",
    # io
    "AgentType",
    "AgentOutput",
    "AgentFinish",
    "BaseScratchPad",
]

_EXPORTS = {
    "BaseAgent": (".base", "BaseAgent"),
    "ReactAgent": (".react.agent", "ReactAgent"),
    "RewooAgent": (".rewoo.agent", "RewooAgent"),
    "LangchainAgent": (".langchain_based", "LangchainAgent"),
    "BaseTool": (".tools", "BaseTool"),
    "ComponentTool": (".tools", "ComponentTool"),
    "GoogleSearchTool": (".tools", "GoogleSearchTool"),
    "WikipediaTool": (".tools", "WikipediaTool"),
    "LLMTool": (".tools", "LLMTool"),
    "AgentType": (".io", "AgentType"),
    "AgentOutput": (".io", "AgentOutput"),
    "AgentFinish": (".io", "AgentFinish"),
    "BaseScratchPad": (".io", "BaseScratchPad"),
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
