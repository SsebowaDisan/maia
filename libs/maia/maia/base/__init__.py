from __future__ import annotations

from importlib import import_module

__all__ = [
    "BaseComponent",
    "Document",
    "DocumentWithEmbedding",
    "BaseMessage",
    "SystemMessage",
    "AIMessage",
    "HumanMessage",
    "RetrievedDocument",
    "LLMInterface",
    "StructuredOutputLLMInterface",
    "ExtractorOutput",
    "Param",
    "Node",
    "lazy",
]

_EXPORTS = {
    "BaseComponent": (".component", "BaseComponent"),
    "Param": (".component", "Param"),
    "Node": (".component", "Node"),
    "lazy": (".component", "lazy"),
    "AIMessage": (".schema", "AIMessage"),
    "BaseMessage": (".schema", "BaseMessage"),
    "Document": (".schema", "Document"),
    "DocumentWithEmbedding": (".schema", "DocumentWithEmbedding"),
    "ExtractorOutput": (".schema", "ExtractorOutput"),
    "HumanMessage": (".schema", "HumanMessage"),
    "LLMInterface": (".schema", "LLMInterface"),
    "RetrievedDocument": (".schema", "RetrievedDocument"),
    "StructuredOutputLLMInterface": (".schema", "StructuredOutputLLMInterface"),
    "SystemMessage": (".schema", "SystemMessage"),
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
