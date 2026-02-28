from __future__ import annotations

import json
import logging
import time
import warnings
from collections import defaultdict
from typing import Optional, Sequence

from decouple import config
from ktem.db.models import engine
from ktem.embeddings.manager import embedding_models_manager
from ktem.llms.manager import llms
from ktem.rerankings.manager import reranking_models_manager
from llama_index.core.vector_stores import (
    FilterCondition,
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)
from llama_index.core.vector_stores.types import VectorStoreQueryMode
from sqlalchemy import select
from sqlalchemy.orm import Session

from maia.embeddings import BaseEmbeddings
from maia.indices import VectorRetrieval
from maia.indices.rankings import BaseReranking, LLMReranking, LLMTrulensScoring
from maia.base import Node, RetrievedDocument

from ..base import BaseFileIndexRetriever

logger = logging.getLogger(__name__)


class DocumentRetrievalPipeline(BaseFileIndexRetriever):
    """Retrieve relevant document."""

    embedding: BaseEmbeddings
    rerankers: Sequence[BaseReranking] = []
    llm_scorer: LLMReranking | None = LLMReranking.withx()
    get_extra_table: bool = False
    mmr: bool = False
    top_k: int = 5
    retrieval_mode: str = "hybrid"

    @Node.auto(depends_on=["embedding", "VS", "DS"])
    def vector_retrieval(self) -> VectorRetrieval:
        return VectorRetrieval(
            embedding=self.embedding,
            vector_store=self.VS,
            doc_store=self.DS,
            retrieval_mode=self.retrieval_mode,  # type: ignore
            rerankers=self.rerankers,
        )

    def run(
        self,
        text: str,
        doc_ids: Optional[list[str]] = None,
        *args,
        **kwargs,
    ) -> list[RetrievedDocument]:
        if doc_ids:
            flatten_doc_ids = []
            for doc_id in doc_ids:
                if doc_id is None:
                    raise ValueError("No document is selected")

                if doc_id.startswith("["):
                    flatten_doc_ids.extend(json.loads(doc_id))
                else:
                    flatten_doc_ids.append(doc_id)
            doc_ids = flatten_doc_ids

        print("searching in doc_ids", doc_ids)
        if not doc_ids:
            logger.info(f"Skip retrieval because of no selected files: {self}")
            return []

        retrieval_kwargs: dict = {}
        with Session(engine) as session:
            stmt = select(self.Index).where(
                self.Index.relation_type == "document",
                self.Index.source_id.in_(doc_ids),
            )
            results = session.execute(stmt)
            chunk_ids = [row[0].target_id for row in results.all()]

        retrieval_kwargs["do_extend"] = True
        retrieval_kwargs["scope"] = chunk_ids
        retrieval_kwargs["filters"] = MetadataFilters(
            filters=[
                MetadataFilter(
                    key="file_id",
                    value=doc_ids,
                    operator=FilterOperator.IN,
                )
            ],
            condition=FilterCondition.OR,
        )

        if self.mmr:
            retrieval_kwargs["mode"] = VectorStoreQueryMode.MMR
            retrieval_kwargs["mmr_threshold"] = 0.5

        s_time = time.time()
        print(f"retrieval_kwargs: {retrieval_kwargs.keys()}")
        docs = self.vector_retrieval(text=text, top_k=self.top_k, **retrieval_kwargs)
        print("retrieval step took", time.time() - s_time)

        if not self.get_extra_table:
            return docs

        table_pages = defaultdict(list)
        retrieved_id = set([doc.doc_id for doc in docs])
        for doc in docs:
            if "page_label" not in doc.metadata:
                continue
            if "file_name" not in doc.metadata:
                warnings.warn(
                    "file_name not in metadata while page_label is in metadata: "
                    f"{doc.metadata}"
                )
            table_pages[doc.metadata["file_name"]].append(doc.metadata["page_label"])

        queries: list[dict] = [
            {"$and": [{"file_name": {"$eq": file_name}}, {"page_label": {"$in": pages}}]}
            for file_name, pages in table_pages.items()
        ]
        if queries:
            try:
                extra_docs = self.vector_retrieval(
                    text="",
                    top_k=50,
                    where=queries[0] if len(queries) == 1 else {"$or": queries},
                )
                for doc in extra_docs:
                    if doc.doc_id not in retrieved_id:
                        docs.append(doc)
            except Exception:
                print("Error retrieving additional tables")

        return docs

    def generate_relevant_scores(
        self, query: str, documents: list[RetrievedDocument]
    ) -> list[RetrievedDocument]:
        docs = (
            documents
            if not self.llm_scorer
            else self.llm_scorer(documents=documents, query=query)
        )
        return docs

    @classmethod
    def get_user_settings(cls) -> dict:
        from ktem.llms.manager import llms

        try:
            reranking_llm = llms.get_default_name()
            reranking_llm_choices = list(llms.options().keys())
        except Exception as exc:
            logger.error(exc)
            reranking_llm = None
            reranking_llm_choices = []

        return {
            "reranking_llm": {
                "name": "LLM for relevant scoring",
                "value": reranking_llm,
                "component": "dropdown",
                "choices": reranking_llm_choices,
                "special_type": "llm",
            },
            "num_retrieval": {
                "name": "Number of document chunks to retrieve",
                "value": 10,
                "component": "number",
            },
            "retrieval_mode": {
                "name": "Retrieval mode",
                "value": "hybrid",
                "choices": ["vector", "text", "hybrid"],
                "component": "dropdown",
            },
            "prioritize_table": {
                "name": "Prioritize table",
                "value": False,
                "choices": [True, False],
                "component": "checkbox",
            },
            "mmr": {
                "name": "Use MMR",
                "value": False,
                "choices": [True, False],
                "component": "checkbox",
            },
            "use_reranking": {
                "name": "Use reranking",
                "value": True,
                "choices": [True, False],
                "component": "checkbox",
            },
            "use_llm_reranking": {
                "name": "Use LLM relevant scoring",
                "value": not config("USE_LOW_LLM_REQUESTS", default=False, cast=bool),
                "choices": [True, False],
                "component": "checkbox",
            },
        }

    @classmethod
    def get_pipeline(cls, user_settings, index_settings, selected):
        use_llm_reranking = user_settings.get("use_llm_reranking", False)

        retriever = cls(
            get_extra_table=user_settings["prioritize_table"],
            top_k=user_settings["num_retrieval"],
            mmr=user_settings["mmr"],
            embedding=embedding_models_manager[
                index_settings.get(
                    "embedding", embedding_models_manager.get_default_name()
                )
            ],
            retrieval_mode=user_settings["retrieval_mode"],
            llm_scorer=(LLMTrulensScoring() if use_llm_reranking else None),
            rerankers=[
                reranking_models_manager[
                    index_settings.get(
                        "reranking", reranking_models_manager.get_default_name()
                    )
                ]
            ],
        )
        if not user_settings["use_reranking"]:
            retriever.rerankers = []  # type: ignore

        for reranker in retriever.rerankers:
            if isinstance(reranker, LLMReranking):
                reranker.llm = llms.get(
                    user_settings["reranking_llm"], llms.get_default()
                )

        if retriever.llm_scorer:
            retriever.llm_scorer.llm = llms.get(
                user_settings["reranking_llm"], llms.get_default()
            )

        kwargs = {".doc_ids": selected}
        retriever.set_run(kwargs, temp=False)
        return retriever
