from __future__ import annotations

import os
import re
import shutil
import threading
import time
from hashlib import sha1, sha256
from pathlib import Path
from typing import Generator, Optional

from ktem.db.models import engine
from llama_index.core.readers.base import BaseReader
from llama_index.core.readers.file.base import default_file_metadata_func
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.services.observability.citation_trace import record_trace_event
from maia.base import BaseComponent, Document, Node, Param
from maia.embeddings import BaseEmbeddings
from maia.indices import VectorIndexing
from maia.indices.qa.highlight_boxes import merge_adjacent_highlight_boxes, normalize_highlight_boxes
from maia.indices.splitters import BaseSplitter

from .settings import default_token_func


class IndexPipeline(BaseComponent):
    """Index a single file."""

    loader: BaseReader
    splitter: BaseSplitter | None
    chunk_batch_size: int = 200

    Source = Param(help="The SQLAlchemy Source table")
    Index = Param(help="The SQLAlchemy Index table")
    VS = Param(help="The VectorStore")
    DS = Param(help="The DocStore")
    FSPath = Param(help="The file storage path")
    user_id = Param(help="The user id")
    collection_name: str = "default"
    private: bool = False
    run_embedding_in_thread: bool = False
    embedding: BaseEmbeddings
    file_hash_chunk_size_bytes: int = 1024 * 1024

    @Node.auto(depends_on=["Source", "Index", "embedding"])
    def vector_indexing(self) -> VectorIndexing:
        return VectorIndexing(
            vector_store=self.VS, doc_store=self.DS, embedding=self.embedding
        )

    @staticmethod
    def _normalize_anchor_text(raw: str) -> str:
        return re.sub(r"\s+", " ", str(raw or "")).strip()

    def _assign_evidence_unit_anchors(
        self,
        *,
        text_docs: list[Document],
        all_chunks: list[Document],
        non_text_docs: list[Document],
        thumbnail_docs: list[Document],
        file_id: str,
    ) -> None:
        max_evidence_units_per_chunk = 12
        page_text_by_label: dict[str, str] = {}
        page_cursor_by_label: dict[str, int] = {}
        raw_page_units_by_label: dict[str, list[dict[str, object]]] = {}
        anchored_page_units_by_label: dict[str, list[dict[str, object]]] = {}

        for row in text_docs:
            metadata = row.metadata if isinstance(row.metadata, dict) else {}
            page_label = str(metadata.get("page_label", "") or "").strip()
            if not page_label:
                continue
            existing = page_text_by_label.get(page_label, "")
            joined = f"{existing}\n{row.text or ''}".strip()
            page_text_by_label[page_label] = joined
            if page_label not in page_cursor_by_label:
                page_cursor_by_label[page_label] = 0
            page_units = metadata.get("page_units")
            if isinstance(page_units, list) and page_units:
                raw_page_units_by_label.setdefault(page_label, []).extend(
                    [dict(item) for item in page_units if isinstance(item, dict)]
                )

        for page_label, page_units in raw_page_units_by_label.items():
            page_text = page_text_by_label.get(page_label, "")
            if not page_text:
                continue
            unit_cursor = 0
            anchored_units: list[dict[str, object]] = []
            for unit in page_units:
                unit_text = self._normalize_anchor_text(str(unit.get("text", "") or ""))
                if not unit_text:
                    continue
                start = page_text.find(unit_text, unit_cursor)
                if start < 0:
                    start = page_text.lower().find(unit_text.lower(), unit_cursor)
                if start < 0 and len(unit_text) >= 12:
                    probe = unit_text[: min(42, len(unit_text))]
                    start = page_text.lower().find(probe.lower(), unit_cursor)
                if start < 0:
                    start = page_text.lower().find(unit_text.lower())
                if start < 0:
                    continue
                end = min(len(page_text), start + len(unit_text))
                highlight_boxes = normalize_highlight_boxes(unit.get("highlight_boxes") or [])
                anchored_units.append(
                    {
                        "text": unit_text,
                        "char_start": start,
                        "char_end": end,
                        "highlight_boxes": highlight_boxes,
                    }
                )
                unit_cursor = max(unit_cursor, end)
            if anchored_units:
                anchored_page_units_by_label[page_label] = anchored_units

        for chunk in all_chunks:
            metadata = chunk.metadata if isinstance(chunk.metadata, dict) else {}
            metadata.setdefault("source_id", file_id)
            page_label = str(metadata.get("page_label", "") or "").strip()
            normalized_chunk = self._normalize_anchor_text(chunk.text or "")
            match_quality = "estimated"

            if page_label and normalized_chunk and page_label in page_text_by_label:
                page_text = page_text_by_label.get(page_label, "")
                search_from = max(0, int(page_cursor_by_label.get(page_label, 0) or 0))
                start = page_text.find(normalized_chunk, search_from)
                if start < 0:
                    start = page_text.lower().find(normalized_chunk.lower(), search_from)
                if start < 0 and len(normalized_chunk) >= 14:
                    probe = normalized_chunk[: min(42, len(normalized_chunk))]
                    start = page_text.lower().find(probe.lower(), search_from)
                if start >= 0:
                    end = min(len(page_text), start + len(normalized_chunk))
                    metadata["char_start"] = start
                    metadata["char_end"] = end
                    page_cursor_by_label[page_label] = max(
                        page_cursor_by_label.get(page_label, 0),
                        end,
                    )
                    match_quality = "exact"

            if "char_start" in metadata and "char_end" in metadata:
                try:
                    if int(metadata.get("char_end", 0) or 0) <= int(metadata.get("char_start", 0) or 0):
                        metadata.pop("char_start", None)
                        metadata.pop("char_end", None)
                except Exception:
                    metadata.pop("char_start", None)
                    metadata.pop("char_end", None)

            chunk_boxes: list[dict[str, float]] = []
            chunk_units: list[dict[str, object]] = []
            try:
                chunk_char_start = int(metadata.get("char_start", 0) or 0)
                chunk_char_end = int(metadata.get("char_end", 0) or 0)
            except Exception:
                chunk_char_start = 0
                chunk_char_end = 0
            anchored_units = anchored_page_units_by_label.get(page_label, [])
            if anchored_units:
                if chunk_char_end > chunk_char_start:
                    for unit in anchored_units:
                        unit_start = int(unit.get("char_start", 0) or 0)
                        unit_end = int(unit.get("char_end", 0) or 0)
                        if unit_end <= chunk_char_start or unit_start >= chunk_char_end:
                            continue
                        boxes = normalize_highlight_boxes(unit.get("highlight_boxes") or [])
                        if boxes:
                            chunk_boxes.extend(boxes)
                        if len(chunk_units) < max_evidence_units_per_chunk:
                            chunk_units.append(
                                {
                                    "text": str(unit.get("text", "") or "")[:240],
                                    "char_start": unit_start,
                                    "char_end": unit_end,
                                    "highlight_boxes": boxes,
                                }
                            )
                if not chunk_boxes and normalized_chunk:
                    normalized_chunk_lower = normalized_chunk.lower()
                    for unit in anchored_units:
                        unit_text = str(unit.get("text", "") or "")
                        if not unit_text:
                            continue
                        if unit_text.lower() in normalized_chunk_lower or normalized_chunk_lower[: min(42, len(normalized_chunk_lower))] in unit_text.lower():
                            boxes = normalize_highlight_boxes(unit.get("highlight_boxes") or [])
                            if boxes:
                                chunk_boxes.extend(boxes)
                            if len(chunk_units) < max_evidence_units_per_chunk:
                                chunk_units.append(
                                    {
                                        "text": unit_text[:240],
                                        "char_start": int(unit.get("char_start", 0) or 0),
                                        "char_end": int(unit.get("char_end", 0) or 0),
                                        "highlight_boxes": boxes,
                                    }
                                )
                merged_boxes = merge_adjacent_highlight_boxes(chunk_boxes) if chunk_boxes else []
                if merged_boxes:
                    metadata["highlight_boxes"] = merged_boxes
                if chunk_units:
                    deduped_units: list[dict[str, object]] = []
                    seen_unit_keys: set[str] = set()
                    for unit in chunk_units:
                        unit_boxes = normalize_highlight_boxes(unit.get("highlight_boxes") or [])
                        if not unit_boxes:
                            continue
                        unit_text = self._normalize_anchor_text(str(unit.get("text", "") or ""))
                        try:
                            unit_start = int(unit.get("char_start", 0) or 0)
                            unit_end = int(unit.get("char_end", 0) or 0)
                        except Exception:
                            unit_start = 0
                            unit_end = 0
                        unit_key = (
                            f"{unit_start}|{unit_end}|{sha1(unit_text.encode('utf-8')).hexdigest()[:12]}"
                        )
                        if unit_key in seen_unit_keys:
                            continue
                        seen_unit_keys.add(unit_key)
                        deduped_units.append(
                            {
                                "text": unit_text[:240],
                                "char_start": unit_start if unit_start > 0 else None,
                                "char_end": unit_end if unit_end > unit_start else None,
                                "highlight_boxes": unit_boxes,
                            }
                        )
                        if len(deduped_units) >= max_evidence_units_per_chunk:
                            break
                    if deduped_units:
                        metadata["evidence_units"] = deduped_units

            span_key = (
                f"{file_id}|{page_label}|{metadata.get('char_start', 0)}|"
                f"{metadata.get('char_end', 0)}|"
                f"{sha1(normalized_chunk.encode('utf-8')).hexdigest()[:16]}"
            )
            metadata.setdefault(
                "unit_id",
                f"eu-{sha1(span_key.encode('utf-8')).hexdigest()[:20]}",
            )
            metadata.setdefault("match_quality", match_quality)
            metadata.pop("page_units", None)
            chunk.metadata = metadata

        for row in [*non_text_docs, *thumbnail_docs]:
            metadata = row.metadata if isinstance(row.metadata, dict) else {}
            metadata.setdefault("source_id", file_id)
            page_label = str(metadata.get("page_label", "") or "").strip()
            normalized_text = self._normalize_anchor_text(row.text or "")
            span_key = (
                f"{file_id}|{page_label}|{sha1(normalized_text.encode('utf-8')).hexdigest()[:16]}"
            )
            metadata.setdefault(
                "unit_id",
                f"eu-{sha1(span_key.encode('utf-8')).hexdigest()[:20]}",
            )
            metadata.setdefault("match_quality", "estimated")
            metadata.pop("page_units", None)
            row.metadata = metadata

        for row in text_docs:
            metadata = row.metadata if isinstance(row.metadata, dict) else {}
            metadata.pop("page_units", None)
            row.metadata = metadata

    def handle_docs(self, docs, file_id, file_name) -> Generator[Document, None, int]:
        s_time = time.time()
        text_docs = []
        non_text_docs = []
        thumbnail_docs = []

        for doc in docs:
            doc_type = doc.metadata.get("type", "text")
            if doc_type == "text":
                text_docs.append(doc)
            elif doc_type == "thumbnail":
                thumbnail_docs.append(doc)
            else:
                non_text_docs.append(doc)

        page_labels = sorted(
            {
                str(doc.metadata.get("page_label", "")).strip()
                for doc in text_docs
                if str(doc.metadata.get("page_label", "")).strip()
            }
        )
        record_trace_event(
            "index.docs_loaded",
            {
                "file_name": file_name,
                "file_id": file_id,
                "doc_count": len(docs),
                "text_doc_count": len(text_docs),
                "non_text_doc_count": len(non_text_docs),
                "thumbnail_doc_count": len(thumbnail_docs),
                "page_count": len(page_labels),
                "page_labels_preview": page_labels[:10],
            },
        )

        print(f"Got {len(thumbnail_docs)} page thumbnails")
        page_label_to_thumbnail = {
            doc.metadata["page_label"]: doc.doc_id for doc in thumbnail_docs
        }

        if self.splitter:
            all_chunks = self.splitter(text_docs)
        else:
            all_chunks = text_docs

        record_trace_event(
            "index.chunks_created",
            {
                "file_name": file_name,
                "file_id": file_id,
                "text_chunk_count": len(all_chunks),
            },
        )

        for chunk in all_chunks:
            page_label = chunk.metadata.get("page_label", None)
            if page_label and page_label in page_label_to_thumbnail:
                chunk.metadata["thumbnail_doc_id"] = page_label_to_thumbnail[page_label]

        self._assign_evidence_unit_anchors(
            text_docs=text_docs,
            all_chunks=all_chunks,
            non_text_docs=non_text_docs,
            thumbnail_docs=thumbnail_docs,
            file_id=file_id,
        )

        to_index_chunks = all_chunks + non_text_docs + thumbnail_docs

        chunks = []
        n_chunks = 0
        chunk_size = self.chunk_batch_size * 4
        for start_idx in range(0, len(to_index_chunks), chunk_size):
            chunks = to_index_chunks[start_idx : start_idx + chunk_size]
            yield Document(
                f" => [{file_name}] Adding {len(chunks)} chunks to doc store",
                channel="debug",
            )
            self.handle_chunks_docstore(chunks, file_id)
            n_chunks += len(chunks)
            yield Document(
                f" => [{file_name}] Processed {n_chunks} chunks",
                channel="debug",
            )

        def insert_chunks_to_vectorstore():
            chunks = []
            n_chunks = 0
            chunk_size = self.chunk_batch_size
            for start_idx in range(0, len(to_index_chunks), chunk_size):
                chunks = to_index_chunks[start_idx : start_idx + chunk_size]
                yield Document(
                    f" => [{file_name}] Adding {len(chunks)} chunks to vector store",
                    channel="debug",
                )
                self.handle_chunks_vectorstore(chunks, file_id)
                n_chunks += len(chunks)
                if self.VS:
                    yield Document(
                        f" => [{file_name}] Created embedding for {n_chunks} chunks",
                        channel="debug",
                    )

        if self.run_embedding_in_thread:
            print("Running embedding in thread")
            threading.Thread(
                target=lambda: list(insert_chunks_to_vectorstore())
            ).start()
        else:
            yield from insert_chunks_to_vectorstore()

        print("indexing step took", time.time() - s_time)
        record_trace_event(
            "index.persisted",
            {
                "file_name": file_name,
                "file_id": file_id,
                "chunk_count": n_chunks,
                "duration_seconds": round(time.time() - s_time, 3),
            },
        )
        return n_chunks

    def handle_chunks_docstore(self, chunks, file_id):
        self.vector_indexing.add_to_docstore(chunks)

        with Session(engine) as session:
            nodes = []
            for chunk in chunks:
                nodes.append(
                    self.Index(
                        source_id=file_id,
                        target_id=chunk.doc_id,
                        relation_type="document",
                    )
                )
            session.add_all(nodes)
            session.commit()

    def handle_chunks_vectorstore(self, chunks, file_id):
        self.vector_indexing.add_to_vectorstore(chunks)
        self.vector_indexing.write_chunk_to_file(chunks)

        if self.VS:
            with Session(engine) as session:
                nodes = []
                for chunk in chunks:
                    nodes.append(
                        self.Index(
                            source_id=file_id,
                            target_id=chunk.doc_id,
                            relation_type="vector",
                        )
                    )
                session.add_all(nodes)
                session.commit()

    def get_id_if_exists(self, file_path: str | Path) -> Optional[str]:
        file_name = file_path.name if isinstance(file_path, Path) else file_path
        if self.private:
            cond: tuple = (
                self.Source.name == file_name,
                self.Source.user == self.user_id,
            )
        else:
            cond = (self.Source.name == file_name,)

        with Session(engine) as session:
            stmt = select(self.Source).where(*cond)
            item = session.execute(stmt).first()
            if item:
                return item[0].id

        return None

    def store_url(self, url: str) -> str:
        file_hash = sha256(url.encode()).hexdigest()
        source = self.Source(
            name=url,
            path=file_hash,
            size=0,
            user=self.user_id,  # type: ignore
        )
        with Session(engine) as session:
            session.add(source)
            session.commit()
            file_id = source.id

        return file_id

    @staticmethod
    def _is_sha256_hex(value: str) -> bool:
        candidate = str(value or "").strip().lower()
        return len(candidate) == 64 and all(ch in "0123456789abcdef" for ch in candidate)

    def _compute_sha256(self, file_path: Path) -> str:
        digest = sha256()
        chunk_size = max(64 * 1024, int(self.file_hash_chunk_size_bytes or 1024 * 1024))
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(chunk_size)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def store_file(
        self,
        file_path: Path,
        *,
        precomputed_sha256: str | None = None,
        precomputed_size: int | None = None,
    ) -> str:
        file_hash = str(precomputed_sha256 or "").strip().lower()
        if not self._is_sha256_hex(file_hash):
            file_hash = self._compute_sha256(file_path)

        file_size = 0
        if precomputed_size is not None:
            try:
                file_size = max(0, int(precomputed_size))
            except Exception:
                file_size = 0
        if file_size <= 0:
            file_size = int(file_path.stat().st_size)

        target_path = self.FSPath / file_hash
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            try:
                os.link(file_path, target_path)
            except Exception:
                shutil.copy2(file_path, target_path)

        source = self.Source(
            name=file_path.name,
            path=file_hash,
            size=file_size,
            user=self.user_id,  # type: ignore
        )
        with Session(engine) as session:
            session.add(source)
            session.commit()
            file_id = source.id

        return file_id

    def get_stored_file_path(self, file_id: str) -> Path | None:
        with Session(engine) as session:
            stmt = select(self.Source.path).where(self.Source.id == file_id)
            row = session.execute(stmt).first()
            if not row or not row[0]:
                return None
            return self.FSPath / str(row[0])

    def _source_has_document_relations(self, file_id: str) -> bool:
        with Session(engine) as session:
            stmt = select(self.Index.id).where(
                self.Index.source_id == file_id,
                self.Index.relation_type == "document",
            ).limit(1)
            row = session.execute(stmt).first()
            return bool(row)

    def finish(self, file_id: str, file_path: str | Path) -> str:
        with Session(engine) as session:
            stmt = select(self.Source).where(self.Source.id == file_id)
            result = session.execute(stmt).first()
            if not result:
                return file_id

            item = result[0]

            doc_ids_stmt = select(self.Index.target_id).where(
                self.Index.source_id == file_id,
                self.Index.relation_type == "document",
            )
            doc_ids = [row[0] for row in session.execute(doc_ids_stmt)]
            token_func = self.get_token_func()
            if doc_ids and token_func:
                docs = self.DS.get(doc_ids)
                item.note["tokens"] = sum([len(token_func(doc.text)) for doc in docs])

            item.note["loader"] = self.get_from_path("loader").__class__.__name__

            session.add(item)
            session.commit()

        return file_id

    def get_token_func(self):
        return default_token_func

    def delete_file(self, file_id: str):
        with Session(engine) as session:
            session.execute(delete(self.Source).where(self.Source.id == file_id))
            vs_ids, ds_ids = [], []
            index = session.execute(
                select(self.Index).where(self.Index.source_id == file_id)
            ).all()
            for each in index:
                if each[0].relation_type == "vector":
                    vs_ids.append(each[0].target_id)
                elif each[0].relation_type == "document":
                    ds_ids.append(each[0].target_id)
                session.delete(each[0])
            session.commit()

        if vs_ids and self.VS:
            self.VS.delete(vs_ids)
        if ds_ids:
            self.DS.delete(ds_ids)

    def run(
        self, file_path: str | Path, reindex: bool, **kwargs
    ) -> tuple[str, list[Document]]:
        raise NotImplementedError

    def stream(
        self, file_path: str | Path, reindex: bool, **kwargs
    ) -> Generator[Document, None, tuple[str, list[Document]]]:
        if isinstance(file_path, Path):
            file_path = file_path.resolve()

        uploaded_file_meta = kwargs.get("uploaded_file_meta")
        file_meta: dict = {}
        if isinstance(file_path, Path) and isinstance(uploaded_file_meta, dict):
            resolved_key = str(file_path)
            row = uploaded_file_meta.get(resolved_key)
            if isinstance(row, dict):
                file_meta = row
        record_trace_event(
            "index.stream_started",
            {
                "file_name": file_path.name if isinstance(file_path, Path) else str(file_path),
                "is_path": isinstance(file_path, Path),
                "reindex": bool(reindex),
                "ingestion_route": str(file_meta.get("ingestion_route") or ""),
                "reader_mode": str(file_meta.get("ingestion_reader_mode") or ""),
            },
        )

        stored_file_path: Path | None = None
        preferred_file_id = str(file_meta.get("source_id") or "").strip() or None
        file_id = preferred_file_id or self.get_id_if_exists(file_path)

        if isinstance(file_path, Path):
            precomputed_sha256 = str(file_meta.get("checksum") or "").strip() or None
            precomputed_size = None
            raw_size = file_meta.get("size")
            if raw_size is not None and str(raw_size).strip():
                try:
                    precomputed_size = int(raw_size)
                except Exception:
                    precomputed_size = None
            if file_id is not None:
                has_document_relations = self._source_has_document_relations(file_id)
                if not reindex and has_document_relations:
                    record_trace_event(
                        "index.stream_duplicate_blocked",
                        {
                            "file_name": file_path.name,
                            "existing_file_id": file_id,
                        },
                    )
                    raise ValueError(
                        f"File {file_path.name} already indexed. Please rerun with "
                        "reindex=True to force reindexing."
                    )
                elif reindex and has_document_relations:
                    yield Document(f" => Removing old {file_path.name}", channel="debug")
                    self.delete_file(file_id)
                    file_id = self.store_file(
                        file_path,
                        precomputed_sha256=precomputed_sha256,
                        precomputed_size=precomputed_size,
                    )
                else:
                    stored_file_path = self.get_stored_file_path(file_id)
                    record_trace_event(
                        "index.stream_reserved_source_reused",
                        {
                            "file_name": file_path.name,
                            "existing_file_id": file_id,
                            "has_document_relations": bool(has_document_relations),
                        },
                    )
            else:
                file_id = self.store_file(
                    file_path,
                    precomputed_sha256=precomputed_sha256,
                    precomputed_size=precomputed_size,
                )
            record_trace_event(
                "index.file_stored",
                {
                    "file_name": file_path.name,
                    "file_id": file_id,
                    "checksum": str(file_meta.get("checksum") or "")[:16],
                    "size": file_meta.get("size"),
                },
            )
            if stored_file_path is None:
                stored_file_path = self.get_stored_file_path(file_id)
        else:
            if file_id is not None:
                if not reindex:
                    raise ValueError(f"URL {file_path} already indexed.")
                yield Document(f" => Removing old {file_path}", channel="debug")
                self.delete_file(file_id)

            file_id = self.store_url(file_path)

        if isinstance(file_path, Path):
            extra_info = default_file_metadata_func(str(file_path))
            if isinstance(file_meta, dict) and file_meta:
                for key, value in file_meta.items():
                    if value is None:
                        continue
                    extra_info[key] = value
            if stored_file_path is not None:
                extra_info["file_path"] = str(stored_file_path)
            file_name = file_path.name
        else:
            extra_info = {"file_name": file_path}
            file_name = file_path

        extra_info["file_id"] = file_id
        extra_info["collection_name"] = self.collection_name

        load_target = stored_file_path if isinstance(file_path, Path) and stored_file_path is not None else file_path
        yield Document(f" => Converting {file_name} to text", channel="debug")
        docs = self.loader.load_data(load_target, extra_info=extra_info)
        record_trace_event(
            "index.loader_completed",
            {
                "file_name": file_name,
                "file_id": file_id,
                "loader": self.loader.__class__.__name__,
                "doc_count": len(docs),
            },
        )
        yield Document(f" => Converted {file_name} to text", channel="debug")
        yield from self.handle_docs(docs, file_id, file_name)

        self.finish(file_id, file_path)
        record_trace_event(
            "index.stream_completed",
            {
                "file_name": file_name,
                "file_id": file_id,
            },
        )

        yield Document(f" => Finished indexing {file_name}", channel="debug")
        return file_id, docs
