from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class _DummyEmbedding:
    openai_api_key: str = ""


@dataclass
class _DummyIndexingVectorPipeline:
    embedding: _DummyEmbedding


class ReaderIndexingPipeline:
    """Compatibility test shim used by libs/ktem legacy QA tests.

    The historical tests import `ReaderIndexingPipeline` from a top-level
    `index` module. In this monorepo layout, that module no longer exists.
    This lightweight implementation preserves the expected interface used by
    tests without affecting the main runtime.
    """

    def __init__(self, storage_path: str | Path) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.indexing_vector_pipeline = _DummyIndexingVectorPipeline(
            embedding=_DummyEmbedding()
        )
        self._indexed_files: list[Path] = []

    def __call__(self, input_file_path: str | Path, force_reindex: bool = False) -> None:
        path = Path(input_file_path)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        if force_reindex:
            self._indexed_files = [path]
        elif path not in self._indexed_files:
            self._indexed_files.append(path)

    def to_retrieving_pipeline(self):
        def _retrieve(query: str) -> list[dict[str, Any]]:
            _ = query
            if not self._indexed_files:
                return []
            first = self._indexed_files[0]
            return [
                {
                    "doc_id": first.stem or "doc-1",
                    "text": f"Indexed file: {first.name}",
                    "metadata": {"file_name": first.name, "file_path": str(first)},
                }
            ]

        return _retrieve

    def to_qa_pipeline(self, **kwargs: Any):
        _ = kwargs

        def _qa(prompt: str) -> str:
            question = " ".join(str(prompt or "").split()).strip()
            if not question:
                question = "Summarize this document."
            if self._indexed_files:
                return f"{question} Indexed {self._indexed_files[0].name}."
            return f"{question} No indexed documents."

        return _qa


__all__ = ["ReaderIndexingPipeline"]
