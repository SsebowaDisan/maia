from __future__ import annotations

import shutil
import threading
import time
from hashlib import sha256
from pathlib import Path
from typing import Generator, Optional

from ktem.db.models import engine
from llama_index.core.readers.base import BaseReader
from llama_index.core.readers.file.base import default_file_metadata_func
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from maia.base import BaseComponent, Document, Node, Param
from maia.embeddings import BaseEmbeddings
from maia.indices import VectorIndexing
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

    @Node.auto(depends_on=["Source", "Index", "embedding"])
    def vector_indexing(self) -> VectorIndexing:
        return VectorIndexing(
            vector_store=self.VS, doc_store=self.DS, embedding=self.embedding
        )

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

        print(f"Got {len(thumbnail_docs)} page thumbnails")
        page_label_to_thumbnail = {
            doc.metadata["page_label"]: doc.doc_id for doc in thumbnail_docs
        }

        if self.splitter:
            all_chunks = self.splitter(text_docs)
        else:
            all_chunks = text_docs

        for chunk in all_chunks:
            page_label = chunk.metadata.get("page_label", None)
            if page_label and page_label in page_label_to_thumbnail:
                chunk.metadata["thumbnail_doc_id"] = page_label_to_thumbnail[page_label]

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

    def store_file(self, file_path: Path) -> str:
        with file_path.open("rb") as fi:
            file_hash = sha256(fi.read()).hexdigest()

        shutil.copy(file_path, self.FSPath / file_hash)
        source = self.Source(
            name=file_path.name,
            path=file_hash,
            size=file_path.stat().st_size,
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

        stored_file_path: Path | None = None
        file_id = self.get_id_if_exists(file_path)

        if isinstance(file_path, Path):
            if file_id is not None:
                if not reindex:
                    raise ValueError(
                        f"File {file_path.name} already indexed. Please rerun with "
                        "reindex=True to force reindexing."
                    )
                else:
                    yield Document(f" => Removing old {file_path.name}", channel="debug")
                    self.delete_file(file_id)
                    file_id = self.store_file(file_path)
            else:
                file_id = self.store_file(file_path)
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
            if stored_file_path is not None:
                extra_info["file_path"] = str(stored_file_path)
            file_name = file_path.name
        else:
            extra_info = {"file_name": file_path}
            file_name = file_path

        extra_info["file_id"] = file_id
        extra_info["collection_name"] = self.collection_name

        yield Document(f" => Converting {file_name} to text", channel="debug")
        docs = self.loader.load_data(file_path, extra_info=extra_info)
        yield Document(f" => Converted {file_name} to text", channel="debug")
        yield from self.handle_docs(docs, file_id, file_name)

        self.finish(file_id, file_path)

        yield Document(f" => Finished indexing {file_name}", channel="debug")
        return file_id, docs
