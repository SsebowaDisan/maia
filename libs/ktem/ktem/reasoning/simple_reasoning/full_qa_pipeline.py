import logging
import json
import re
import threading
from typing import Generator

from decouple import config
from ktem.embeddings.manager import embedding_models_manager as embeddings
from ktem.llms.manager import llms
from ktem.reasoning.prompt_optimization import RewriteQuestionPipeline
from ktem.utils.render import Render
from ktem.utils.visualize_cited import CreateCitationVizPipeline
from plotly.io import to_json

from maia.base import BaseComponent, Document, Node, RetrievedDocument
from maia.indices.qa.citation_qa import (
    CONTEXT_RELEVANT_WARNING_SCORE,
    DEFAULT_QA_TEXT_PROMPT,
    AnswerWithContextPipeline,
)
from maia.mindmap.indexer import build_reasoning_map
from maia.indices.qa.citation_qa_inline import AnswerWithInlineCitation
from maia.indices.qa.format_context import PrepareEvidencePipeline
from maia.indices.qa.utils import replace_think_tag_with_details

from ...utils import SUPPORTED_LANGUAGE_MAP
from ..base import BaseReasoning
from .query_context import AddQueryContextPipeline

logger = logging.getLogger(__name__)


class FullQAPipeline(BaseReasoning):
    """Question answering pipeline. Handle from question to answer."""

    class Config:
        allow_extra = True

    trigger_context: int = 150
    use_rewrite: bool = False
    mindmap_max_depth: int = 4
    include_reasoning_map: bool = True

    retrievers: list[BaseComponent]

    evidence_pipeline: PrepareEvidencePipeline = PrepareEvidencePipeline.withx()
    answering_pipeline: AnswerWithContextPipeline
    rewrite_pipeline: RewriteQuestionPipeline | None = None
    create_citation_viz_pipeline: CreateCitationVizPipeline = Node(
        default_callback=lambda _: CreateCitationVizPipeline(
            embedding=embeddings.get_default()
        )
    )
    add_query_context: AddQueryContextPipeline = AddQueryContextPipeline.withx()

    @staticmethod
    def _filter_docs_by_mindmap_focus(
        docs: list[RetrievedDocument],
        focus: dict | None,
    ) -> list[RetrievedDocument]:
        payload = focus if isinstance(focus, dict) else {}
        if not payload or not docs:
            return docs

        source_id = str(payload.get("source_id", "") or "").strip()
        source_name = str(payload.get("source_name", "") or "").strip().lower()
        page_ref = str(payload.get("page_ref", "") or payload.get("page_label", "") or "").strip()
        unit_id = str(payload.get("unit_id", "") or "").strip()
        focus_text = str(payload.get("text", "") or "").strip().lower()

        filtered = docs
        if source_id:
            filtered = [
                doc
                for doc in filtered
                if str((doc.metadata or {}).get("source_id", "") or "").strip() == source_id
            ]
        elif source_name:
            filtered = [
                doc
                for doc in filtered
                if source_name
                in str((doc.metadata or {}).get("file_name", "") or "").strip().lower()
            ]
        if page_ref:
            page_filtered = [
                doc
                for doc in filtered
                if str((doc.metadata or {}).get("page_label", "") or "").strip() == page_ref
            ]
            if page_filtered:
                filtered = page_filtered
        if unit_id:
            unit_filtered = [
                doc
                for doc in filtered
                if str((doc.metadata or {}).get("unit_id", "") or "").strip() == unit_id
            ]
            if unit_filtered:
                filtered = unit_filtered

        if focus_text and filtered:
            focus_tokens = {token for token in re.findall(r"[a-z0-9]{3,}", focus_text)}

            def overlap_score(doc: RetrievedDocument) -> int:
                text = str(doc.text or "").lower()
                return sum(1 for token in focus_tokens if token in text)

            ranked = sorted(filtered, key=overlap_score, reverse=True)
            if ranked and overlap_score(ranked[0]) > 0:
                filtered = ranked[: max(4, min(10, len(ranked)))]

        return filtered or docs

    def retrieve(
        self, message: str, history: list
    ) -> tuple[list[RetrievedDocument], list[Document]]:
        query = None
        if not query:
            query = message

        docs, doc_ids = [], []
        plot_docs = []

        for idx, retriever in enumerate(self.retrievers):
            retriever_node = self._prepare_child(retriever, f"retriever_{idx}")
            retriever_docs = retriever_node(text=query)

            retriever_docs_text = []
            retriever_docs_plot = []

            for doc in retriever_docs:
                if doc.metadata.get("type", "") == "plot":
                    retriever_docs_plot.append(doc)
                else:
                    retriever_docs_text.append(doc)

            for doc in retriever_docs_text:
                if doc.doc_id not in doc_ids:
                    docs.append(doc)
                    doc_ids.append(doc.doc_id)

            plot_docs.extend(retriever_docs_plot)

        info = [
            Document(
                channel="info",
                content=Render.collapsible_with_header(doc, open_collapsible=True),
            )
            for doc in docs
        ] + [
            Document(
                channel="plot",
                content=doc.metadata.get("data", ""),
            )
            for doc in plot_docs
        ]

        return docs, info

    def _parse_mindmap_payload(self, raw_payload) -> dict:
        if isinstance(raw_payload, dict):
            return raw_payload
        if isinstance(raw_payload, Document):
            nested = raw_payload.metadata.get("mindmap")
            if isinstance(nested, dict):
                return nested
            try:
                parsed = json.loads(str(raw_payload.text or ""))
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        if isinstance(raw_payload, str):
            try:
                parsed = json.loads(raw_payload)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return {}

    def prepare_mindmap(self, answer, docs, question) -> Document | None:
        raw_mindmap = (answer.metadata or {}).get("mindmap")
        payload = self._parse_mindmap_payload(raw_mindmap)
        if not payload:
            return None

        if self.include_reasoning_map and not isinstance(payload.get("reasoning_map"), dict):
            payload["reasoning_map"] = build_reasoning_map(
                question=str(question or ""),
                answer_text=str(answer.text or ""),
                context_nodes=list(payload.get("nodes", []))[:4],
            )

        return Document(
            channel="info",
            content="",
            metadata={"mindmap": payload},
        )

    def prepare_citation_viz(self, answer, question, docs) -> Document | None:
        doc_texts = [doc.text for doc in docs]
        citation_plot = None
        plot_content = None

        if answer.metadata["citation_viz"] and len(docs) > 1:
            try:
                citation_plot = self.create_citation_viz_pipeline(doc_texts, question)
            except Exception as exc:
                print("Failed to create citation plot:", exc)

            if citation_plot:
                plot = to_json(citation_plot)
                plot_content = Document(channel="plot", content=plot)

        return plot_content

    def show_citations_and_addons(self, answer, docs, question):
        with_citation, without_citation = self.answering_pipeline.prepare_citations(
            answer, docs
        )
        mindmap_output = self.prepare_mindmap(answer, docs, question)
        citation_plot_output = self.prepare_citation_viz(answer, question, docs)

        if not with_citation and not without_citation:
            yield Document(channel="info", content="<h5><b>No evidence found.</b></h5>")
        else:
            max_llm_rerank_score = max(
                doc.metadata.get("llm_trulens_score", 0.0) for doc in docs
            )
            has_llm_score = any("llm_trulens_score" in doc.metadata for doc in docs)
            yield Document(channel="info", content=None)

            if mindmap_output:
                yield mindmap_output

            if citation_plot_output:
                yield citation_plot_output

            if has_llm_score and max_llm_rerank_score < CONTEXT_RELEVANT_WARNING_SCORE:
                yield Document(
                    channel="info",
                    content=(
                        "<h5>WARNING! Context relevance score is low. "
                        "Double check the model answer for correctness.</h5>"
                    ),
                )

            qa_score = (
                round(answer.metadata["qa_score"], 2)
                if answer.metadata.get("qa_score")
                else None
            )
            if qa_score:
                yield Document(
                    channel="info",
                    content=f"<h5>Answer confidence: {qa_score}</h5>",
                )

            yield from with_citation
            if without_citation:
                yield from without_citation

    async def ainvoke(  # type: ignore
        self, message: str, conv_id: str, history: list, **kwargs  # type: ignore
    ) -> Document:  # type: ignore
        raise NotImplementedError

    def stream(  # type: ignore
        self, message: str, conv_id: str, history: list, **kwargs  # type: ignore
    ) -> Generator[Document, None, Document]:
        if self.use_rewrite and self.rewrite_pipeline:
            print("Chosen rewrite pipeline", self.rewrite_pipeline)
            message = self.rewrite_pipeline(question=message).text
            print("Rewrite result", message)

        print(f"Retrievers {self.retrievers}")
        docs, infos = self.retrieve(message, history)
        docs = self._filter_docs_by_mindmap_focus(
            docs,
            kwargs.get("mindmap_focus", {}),
        )
        print(f"Got {len(docs)} retrieved documents")
        yield from infos

        evidence_mode, evidence, images = self.evidence_pipeline(docs).content

        def generate_relevant_scores():
            nonlocal docs
            docs = self.retrievers[0].generate_relevant_scores(message, docs)

        if evidence and self.retrievers:
            scoring_thread = threading.Thread(target=generate_relevant_scores)
            scoring_thread.start()
        else:
            scoring_thread = None

        answer = yield from self.answering_pipeline.stream(
            question=message,
            history=history,
            evidence=evidence,
            evidence_mode=evidence_mode,
            images=images,
            conv_id=conv_id,
            retrieved_docs=docs,
            mindmap_max_depth=self.mindmap_max_depth,
            include_reasoning_map=self.include_reasoning_map,
            **kwargs,
        )

        processed_answer = replace_think_tag_with_details(answer.text)
        if processed_answer != answer.text:
            yield Document(channel="chat", content=None)
            yield Document(channel="chat", content=processed_answer)

        if scoring_thread:
            scoring_thread.join()

        yield from self.show_citations_and_addons(answer, docs, message)

        return answer

    @classmethod
    def prepare_pipeline_instance(cls, settings, retrievers):
        return cls(
            retrievers=retrievers,
            rewrite_pipeline=None,
        )

    @classmethod
    def get_pipeline(cls, settings, states, retrievers):
        max_context_length_setting = settings.get("reasoning.max_context_length", 32000)

        pipeline = cls.prepare_pipeline_instance(settings, retrievers)

        prefix = f"reasoning.options.{cls.get_info()['id']}"
        llm_name = settings.get(f"{prefix}.llm", None)
        llm = llms.get(llm_name, llms.get_default())

        evidence_pipeline = pipeline.evidence_pipeline
        evidence_pipeline.max_context_length = max_context_length_setting

        use_inline_citation = settings[f"{prefix}.highlight_citation"] == "inline"

        if use_inline_citation:
            answer_pipeline = pipeline.answering_pipeline = AnswerWithInlineCitation()
        else:
            answer_pipeline = pipeline.answering_pipeline = AnswerWithContextPipeline()

        answer_pipeline.llm = llm
        answer_pipeline.citation_pipeline.llm = llm
        answer_pipeline.n_last_interactions = settings[f"{prefix}.n_last_interactions"]
        answer_pipeline.enable_citation = (
            settings[f"{prefix}.highlight_citation"] != "off"
        )
        answer_pipeline.enable_mindmap = settings[f"{prefix}.create_mindmap"]
        answer_pipeline.enable_citation_viz = settings[f"{prefix}.create_citation_viz"]
        answer_pipeline.use_multimodal = settings[f"{prefix}.use_multimodal"]
        answer_pipeline.system_prompt = settings[f"{prefix}.system_prompt"]
        answer_pipeline.qa_template = settings[f"{prefix}.qa_prompt"]
        answer_pipeline.lang = SUPPORTED_LANGUAGE_MAP.get(
            settings["reasoning.lang"], "English"
        )

        pipeline.add_query_context.llm = llm
        pipeline.add_query_context.n_last_interactions = settings[
            f"{prefix}.n_last_interactions"
        ]

        pipeline.trigger_context = settings[f"{prefix}.trigger_context"]
        pipeline.mindmap_max_depth = int(settings.get(f"{prefix}.mindmap_max_depth", 4) or 4)
        pipeline.include_reasoning_map = bool(
            settings.get(f"{prefix}.include_reasoning_map", True)
        )
        pipeline.use_rewrite = states.get("app", {}).get("regen", False)
        if pipeline.rewrite_pipeline:
            pipeline.rewrite_pipeline.llm = llm
            pipeline.rewrite_pipeline.lang = SUPPORTED_LANGUAGE_MAP.get(
                settings["reasoning.lang"], "English"
            )
        return pipeline

    @classmethod
    def get_user_settings(cls) -> dict:
        llm = ""
        choices = [("(default)", "")]
        try:
            choices += [(_, _) for _ in llms.options().keys()]
        except Exception as exc:
            logger.exception(f"Failed to get LLM options: {exc}")

        return {
            "llm": {
                "name": "Language model",
                "value": llm,
                "component": "dropdown",
                "choices": choices,
                "special_type": "llm",
                "info": (
                    "The language model to use for generating the answer. If None, "
                    "the application default language model will be used."
                ),
            },
            "highlight_citation": {
                "name": "Citation style",
                "value": (
                    "highlight"
                    if not config("USE_LOW_LLM_REQUESTS", default=False, cast=bool)
                    else "off"
                ),
                "component": "radio",
                "choices": [
                    ("citation: highlight", "highlight"),
                    ("citation: inline", "inline"),
                    ("no citation", "off"),
                ],
            },
            "create_mindmap": {
                "name": "Create Mindmap",
                "value": False,
                "component": "checkbox",
            },
            "mindmap_max_depth": {
                "name": "Mindmap max depth",
                "value": 4,
                "component": "dropdown",
                "choices": [(str(i), i) for i in range(2, 9)],
            },
            "include_reasoning_map": {
                "name": "Include reasoning map",
                "value": True,
                "component": "checkbox",
            },
            "create_citation_viz": {
                "name": "Create Embeddings Visualization",
                "value": False,
                "component": "checkbox",
            },
            "use_multimodal": {
                "name": "Use Multimodal Input",
                "value": False,
                "component": "checkbox",
            },
            "system_prompt": {
                "name": "System Prompt",
                "value": ("This is a question answering system."),
            },
            "qa_prompt": {
                "name": "QA Prompt (contains {context}, {question}, {lang})",
                "value": DEFAULT_QA_TEXT_PROMPT,
            },
            "n_last_interactions": {
                "name": "Number of interactions to include",
                "value": 5,
                "component": "number",
                "info": "The maximum number of chat interactions to include in the LLM",
            },
            "trigger_context": {
                "name": "Maximum message length for context rewriting",
                "value": 150,
                "component": "number",
                "info": (
                    "The maximum length of the message to trigger context addition. "
                    "Exceeding this length, the message will be used as is."
                ),
            },
        }

    @classmethod
    def get_info(cls) -> dict:
        return {
            "id": "simple",
            "name": "Simple QA",
            "description": (
                "Simple RAG-based question answering pipeline. This pipeline can "
                "perform both keyword search and similarity search to retrieve the "
                "context. After that it includes that context to generate the answer."
            ),
        }
