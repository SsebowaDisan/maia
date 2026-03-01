from __future__ import annotations

from importlib import import_module

__all__ = [
    "BaseDocumentStore",
    "InMemoryDocumentStore",
    "ElasticsearchDocumentStore",
    "SimpleFileDocumentStore",
    "LanceDBDocumentStore",
]

_EXPORTS = {
    "BaseDocumentStore": (".base", "BaseDocumentStore"),
    "InMemoryDocumentStore": (".in_memory", "InMemoryDocumentStore"),
    "ElasticsearchDocumentStore": (".elasticsearch", "ElasticsearchDocumentStore"),
    "SimpleFileDocumentStore": (".simple_file", "SimpleFileDocumentStore"),
    "LanceDBDocumentStore": (".lancedb", "LanceDBDocumentStore"),
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
