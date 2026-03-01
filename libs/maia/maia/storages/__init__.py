from __future__ import annotations

from importlib import import_module

__all__ = [
    # Document stores
    "BaseDocumentStore",
    "InMemoryDocumentStore",
    "ElasticsearchDocumentStore",
    "SimpleFileDocumentStore",
    "LanceDBDocumentStore",
    # Vector stores
    "BaseVectorStore",
    "ChromaVectorStore",
    "InMemoryVectorStore",
    "SimpleFileVectorStore",
    "LanceDBVectorStore",
    "MilvusVectorStore",
    "QdrantVectorStore",
]

_EXPORTS = {
    "BaseDocumentStore": (".docstores", "BaseDocumentStore"),
    "InMemoryDocumentStore": (".docstores", "InMemoryDocumentStore"),
    "ElasticsearchDocumentStore": (".docstores", "ElasticsearchDocumentStore"),
    "SimpleFileDocumentStore": (".docstores", "SimpleFileDocumentStore"),
    "LanceDBDocumentStore": (".docstores", "LanceDBDocumentStore"),
    "BaseVectorStore": (".vectorstores", "BaseVectorStore"),
    "ChromaVectorStore": (".vectorstores", "ChromaVectorStore"),
    "InMemoryVectorStore": (".vectorstores", "InMemoryVectorStore"),
    "SimpleFileVectorStore": (".vectorstores", "SimpleFileVectorStore"),
    "LanceDBVectorStore": (".vectorstores", "LanceDBVectorStore"),
    "MilvusVectorStore": (".vectorstores", "MilvusVectorStore"),
    "QdrantVectorStore": (".vectorstores", "QdrantVectorStore"),
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
