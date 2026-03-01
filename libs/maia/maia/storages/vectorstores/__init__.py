from __future__ import annotations

from importlib import import_module

__all__ = [
    "BaseVectorStore",
    "ChromaVectorStore",
    "InMemoryVectorStore",
    "SimpleFileVectorStore",
    "LanceDBVectorStore",
    "MilvusVectorStore",
    "QdrantVectorStore",
]

_EXPORTS = {
    "BaseVectorStore": (".base", "BaseVectorStore"),
    "ChromaVectorStore": (".chroma", "ChromaVectorStore"),
    "InMemoryVectorStore": (".in_memory", "InMemoryVectorStore"),
    "SimpleFileVectorStore": (".simple_file", "SimpleFileVectorStore"),
    "LanceDBVectorStore": (".lancedb", "LanceDBVectorStore"),
    "MilvusVectorStore": (".milvus", "MilvusVectorStore"),
    "QdrantVectorStore": (".qdrant", "QdrantVectorStore"),
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
