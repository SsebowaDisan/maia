from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Generator

from maia.base import Document, Param
from maia.embeddings import BaseEmbeddings
from maia.indices.ingests.files import (
    KH_DEFAULT_FILE_EXTRACTORS,
    KH_OCR_FILE_EXTRACTORS,
    adobe_reader,
    azure_reader,
    docling_reader,
    unstructured,
)
from maia.indices.splitters import TokenSplitter
from maia.loaders import WebReader

from ktem.embeddings.manager import embedding_models_manager

from ..base import BaseFileIndexIndexing
from .index_pipeline import IndexPipeline
from .settings import dev_settings

logger = logging.getLogger(__name__)


class IndexDocumentPipeline(BaseFileIndexIndexing):
    """Index the file and decide pipeline based on file type."""

    reader_mode: str = Param("default", help="The reader mode")
    embedding: BaseEmbeddings
    run_embedding_in_thread: bool = False
    web_crawl_depth: int = Param(
        0, help="How many link levels to crawl when indexing a URL. 0 means unlimited."
    )
    web_crawl_max_pages: int = Param(
        0, help="Maximum number of pages to crawl per input URL. 0 means unlimited."
    )
    web_crawl_same_domain_only: bool = Param(
        True, help="Only crawl links that stay on the same domain."
    )
    web_crawl_include_pdfs: bool = Param(
        True, help="Include linked PDF URLs while crawling."
    )
    web_crawl_include_images: bool = Param(
        True, help="Include linked image URLs while crawling."
    )

    @Param.auto(depends_on="reader_mode")
    def readers(self):
        readers = deepcopy(
            KH_OCR_FILE_EXTRACTORS
            if self.reader_mode == "ocr"
            else KH_DEFAULT_FILE_EXTRACTORS
        )
        print("reader_mode", self.reader_mode)
        if self.reader_mode == "adobe":
            readers[".pdf"] = adobe_reader
        elif self.reader_mode == "azure-di":
            readers[".pdf"] = azure_reader
        elif self.reader_mode == "docling":
            readers[".pdf"] = docling_reader

        dev_readers, _, _ = dev_settings()
        readers.update(dev_readers)

        return readers

    @classmethod
    def get_user_settings(cls):
        return {
            "reader_mode": {
                "name": "File loader",
                "value": "default",
                "choices": [
                    ("Default (open-source)", "default"),
                    ("OCR (local, scanned/image-first)", "ocr"),
                    ("Adobe API (figure+table extraction)", "adobe"),
                    (
                        "Azure AI Document Intelligence (figure+table extraction)",
                        "azure-di",
                    ),
                    ("Docling (figure+table extraction)", "docling"),
                ],
                "component": "dropdown",
            },
            "web_crawl_depth": {
                "name": "Web crawl depth",
                "value": 0,
                "component": "number",
            },
            "web_crawl_max_pages": {
                "name": "Web crawl max pages",
                "value": 0,
                "component": "number",
            },
            "web_crawl_same_domain_only": {
                "name": "Web crawl same domain only",
                "value": True,
                "component": "checkbox",
            },
            "web_crawl_include_pdfs": {
                "name": "Web crawl include PDFs",
                "value": True,
                "component": "checkbox",
            },
            "web_crawl_include_images": {
                "name": "Web crawl include images",
                "value": True,
                "component": "checkbox",
            },
        }

    @classmethod
    def get_pipeline(cls, user_settings, index_settings) -> BaseFileIndexIndexing:
        def _to_int(value, default: int, minimum: int) -> int:
            try:
                return max(minimum, int(value))
            except (TypeError, ValueError):
                return default

        def _to_bool(value, default: bool) -> bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"1", "true", "yes", "on"}:
                    return True
                if lowered in {"0", "false", "no", "off"}:
                    return False
            return default

        use_quick_index_mode = user_settings.get("quick_index_mode", False)
        print("use_quick_index_mode", use_quick_index_mode)
        obj = cls(
            embedding=embedding_models_manager[
                index_settings.get(
                    "embedding", embedding_models_manager.get_default_name()
                )
            ],
            run_embedding_in_thread=use_quick_index_mode,
            reader_mode=user_settings.get("reader_mode", "default"),
            web_crawl_depth=_to_int(user_settings.get("web_crawl_depth", 0), 0, 0),
            web_crawl_max_pages=_to_int(
                user_settings.get("web_crawl_max_pages", 0), 0, 0
            ),
            web_crawl_same_domain_only=_to_bool(
                user_settings.get("web_crawl_same_domain_only", True), True
            ),
            web_crawl_include_pdfs=_to_bool(
                user_settings.get("web_crawl_include_pdfs", True), True
            ),
            web_crawl_include_images=_to_bool(
                user_settings.get("web_crawl_include_images", True), True
            ),
        )
        return obj

    def is_url(self, file_path: str | Path) -> bool:
        return isinstance(file_path, str) and (
            file_path.startswith("http://") or file_path.startswith("https://")
        )

    def route(self, file_path: str | Path) -> IndexPipeline:
        _, dev_chunk_size, dev_chunk_overlap = dev_settings()

        chunk_size = self.chunk_size or dev_chunk_size
        chunk_overlap = self.chunk_overlap or dev_chunk_overlap

        if self.is_url(file_path):
            reader = WebReader(
                max_depth=self.web_crawl_depth,
                max_pages=self.web_crawl_max_pages,
                same_domain_only=self.web_crawl_same_domain_only,
                include_pdfs=self.web_crawl_include_pdfs,
                include_images=self.web_crawl_include_images,
            )
        else:
            assert isinstance(file_path, Path)
            ext = file_path.suffix.lower()
            reader = self.readers.get(ext, unstructured)
            if reader is None:
                raise NotImplementedError(
                    f"No supported pipeline to index {file_path.name}. Please specify "
                    "the suitable pipeline for this file type in the settings."
                )

        print(f"Chunk size: {chunk_size}, chunk overlap: {chunk_overlap}")

        print("Using reader", reader)
        splitter = None
        if chunk_size or chunk_overlap:
            splitter = TokenSplitter(
                chunk_size=chunk_size or 1024,
                chunk_overlap=chunk_overlap or 256,
                separator="\n\n",
                backup_separators=["\n", ".", "\u200B"],
            )

        pipeline: IndexPipeline = IndexPipeline(
            loader=reader,
            splitter=splitter,
            run_embedding_in_thread=self.run_embedding_in_thread,
            Source=self.Source,
            Index=self.Index,
            VS=self.VS,
            DS=self.DS,
            FSPath=self.FSPath,
            user_id=self.user_id,
            private=self.private,
            embedding=self.embedding,
        )

        return pipeline

    def run(
        self, file_paths: str | Path | list[str | Path], *args, **kwargs
    ) -> tuple[list[str | None], list[str | None]]:
        raise NotImplementedError

    def stream(
        self, file_paths: str | Path | list[str | Path], reindex: bool = False, **kwargs
    ) -> Generator[
        Document, None, tuple[list[str | None], list[str | None], list[Document]]
    ]:
        if not isinstance(file_paths, list):
            file_paths = [file_paths]

        file_ids: list[str | None] = []
        errors: list[str | None] = []
        all_docs = []

        n_files = len(file_paths)
        for idx, file_path in enumerate(file_paths):
            if self.is_url(file_path):
                file_name = file_path
            else:
                file_path = Path(file_path)
                file_name = file_path.name

            yield Document(
                content=f"Indexing [{idx + 1}/{n_files}]: {file_name}",
                channel="debug",
            )

            try:
                pipeline = self.route(file_path)
                file_id, docs = yield from pipeline.stream(
                    file_path, reindex=reindex, **kwargs
                )
                all_docs.extend(docs)
                file_ids.append(file_id)
                errors.append(None)
                yield Document(
                    content={
                        "file_path": file_path,
                        "file_name": file_name,
                        "status": "success",
                        "file_id": file_id,
                    },
                    channel="index",
                )
            except Exception as exc:
                logger.exception(exc)
                file_ids.append(None)
                errors.append(str(exc))
                yield Document(
                    content={
                        "file_path": file_path,
                        "file_name": file_name,
                        "status": "failed",
                        "message": str(exc),
                        "file_id": None,
                    },
                    channel="index",
                )

        return file_ids, errors, all_docs
