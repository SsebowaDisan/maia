"""Compatibility shim for file index pipelines.

Deprecated module path for implementation details:
- use `ktem.index.file.file_pipelines` for new code.
"""

from .base import BaseFileIndexIndexing, BaseFileIndexRetriever
from .file_pipelines import DocumentRetrievalPipeline, IndexDocumentPipeline, IndexPipeline

__all__ = [
    "BaseFileIndexIndexing",
    "BaseFileIndexRetriever",
    "DocumentRetrievalPipeline",
    "IndexDocumentPipeline",
    "IndexPipeline",
]
