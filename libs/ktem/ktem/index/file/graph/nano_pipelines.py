import asyncio
import logging
from pathlib import Path
from typing import Generator

from ktem.db.models import engine
from sqlalchemy.orm import Session
from theflow.settings import settings

from maia.base import Document, Param, RetrievedDocument

from ..pipelines import BaseFileIndexRetriever
from .graphrag_shared import (
    INDEX_BATCHSIZE,
    apply_prompt_overrides,
    build_prompt_settings,
    build_retrieved_table,
    clean_quote,
    clear_json_cache,
    collect_text_docs,
    ensure_storage_path,
    get_default_models_wrapper,
    list_of_list_to_df,
    prepare_graph_index_path,
    store_file_graph_mappings,
)
from .pipelines import GraphRAGIndexingPipeline
from .visualize import create_knowledge_graph, visualize_graph

try:
    from nano_graphrag import GraphRAG, QueryParam
    from nano_graphrag._op import (
        _find_most_related_community_from_entities,
        _find_most_related_edges_from_entities,
        _find_most_related_text_unit_from_entities,
    )
    from nano_graphrag._utils import EmbeddingFunc, compute_args_hash

except ImportError:
    print(
        (
            "Nano-GraphRAG dependencies not installed. "
            "Try `pip install nano-graphrag` to install. "
            "Nano-GraphRAG retriever pipeline will not work properly."
        )
    )


logging.getLogger("nano-graphrag").setLevel(logging.INFO)


filestorage_path = ensure_storage_path(
    Path(settings.KH_FILESTORAGE_PATH),
    "nano_graphrag",
)


async def nano_graph_rag_build_local_query_context(
    graph_func,
    query,
    query_param,
):
    knowledge_graph_inst = graph_func.chunk_entity_relation_graph
    entities_vdb = graph_func.entities_vdb
    community_reports = graph_func.community_reports
    text_chunks_db = graph_func.text_chunks

    results = await entities_vdb.query(query, top_k=query_param.top_k)
    if not len(results):
        raise ValueError("No results found")

    node_datas = await asyncio.gather(
        *[knowledge_graph_inst.get_node(r["entity_name"]) for r in results]
    )
    node_degrees = await asyncio.gather(
        *[knowledge_graph_inst.node_degree(r["entity_name"]) for r in results]
    )
    node_datas = [
        {**n, "entity_name": k["entity_name"], "rank": d}
        for k, n, d in zip(results, node_datas, node_degrees)
        if n is not None
    ]
    use_communities = await _find_most_related_community_from_entities(
        node_datas, query_param, community_reports
    )
    use_text_units = await _find_most_related_text_unit_from_entities(
        node_datas, query_param, text_chunks_db, knowledge_graph_inst
    )
    use_relations = await _find_most_related_edges_from_entities(
        node_datas, query_param, knowledge_graph_inst
    )
    entites_section_list = [["id", "entity", "type", "description", "rank"]]
    for i, n in enumerate(node_datas):
        entites_section_list.append(
            [
                str(i),
                clean_quote(n["entity_name"]),
                n.get("entity_type", "UNKNOWN"),
                clean_quote(n.get("description", "UNKNOWN")),
                n["rank"],
            ]
        )
    entities_df = list_of_list_to_df(entites_section_list)

    relations_section_list = [
        ["id", "source", "target", "description", "weight", "rank"]
    ]
    for i, e in enumerate(use_relations):
        relations_section_list.append(
            [
                str(i),
                clean_quote(e["src_tgt"][0]),
                clean_quote(e["src_tgt"][1]),
                clean_quote(e["description"]),
                e["weight"],
                e["rank"],
            ]
        )
    relations_df = list_of_list_to_df(relations_section_list)

    communities_section_list = [["id", "content"]]
    for i, c in enumerate(use_communities):
        communities_section_list.append([str(i), c["report_string"]])
    communities_df = list_of_list_to_df(communities_section_list)

    text_units_section_list = [["id", "content"]]
    for i, t in enumerate(use_text_units):
        text_units_section_list.append([str(i), t["content"]])
    sources_df = list_of_list_to_df(text_units_section_list)

    return entities_df, relations_df, communities_df, sources_df


def build_graphrag(working_dir, llm_func, embedding_func):
    graphrag_func = GraphRAG(
        working_dir=working_dir,
        best_model_func=llm_func,
        cheap_model_func=llm_func,
        embedding_func=embedding_func,
    )
    return graphrag_func


class NanoGraphRAGIndexingPipeline(GraphRAGIndexingPipeline):
    """GraphRAG specific indexing pipeline"""

    prompts: dict[str, str] = {}
    collection_graph_id: str
    index_batch_size: int = INDEX_BATCHSIZE

    def store_file_id_with_graph_id(self, file_ids: list[str | None]):
        if not settings.USE_GLOBAL_GRAPHRAG:
            return super().store_file_id_with_graph_id(file_ids)

        # Use the collection-wide graph ID for LightRAG
        graph_id = self.collection_graph_id

        # Record all files under this graph_id
        store_file_graph_mappings(self.Index, graph_id, file_ids)

        return graph_id

    @classmethod
    def get_user_settings(cls) -> dict:
        try:
            from nano_graphrag.prompt import PROMPTS

            return build_prompt_settings(PROMPTS, INDEX_BATCHSIZE)
        except ImportError as e:
            print(e)
            return {}

    def call_graphrag_index(self, graph_id: str, docs: list[Document]):
        from nano_graphrag.prompt import PROMPTS

        # modify the prompt if it is set in the settings
        apply_prompt_overrides(PROMPTS, self.prompts)

        _, input_path = prepare_graph_index_path(filestorage_path, graph_id)
        input_path.mkdir(parents=True, exist_ok=True)

        (
            llm_func,
            embedding_func,
            default_llm,
            default_embedding,
        ) = get_default_models_wrapper(EmbeddingFunc, compute_args_hash)
        print(
            f"Indexing GraphRAG with LLM {default_llm} "
            f"and Embedding {default_embedding}..."
        )

        all_docs = collect_text_docs(docs)

        yield Document(
            channel="debug",
            text="[GraphRAG] Creating/Updating index... This can take a long time.",
        )

        # Check if graph already exists
        graph_file = input_path / "graph_chunk_entity_relation.graphml"
        is_incremental = graph_file.exists()

        # Only clear cache if it's a new graph
        if not is_incremental:
            clear_json_cache(input_path)

        # Initialize or load existing GraphRAG
        graphrag_func = build_graphrag(
            input_path,
            llm_func=llm_func,
            embedding_func=embedding_func,
        )

        total_docs = len(all_docs)
        process_doc_count = 0
        yield Document(
            channel="debug",
            text=(
                f"[GraphRAG] {'Updating' if is_incremental else 'Creating'} index: "
                f"{process_doc_count} / {total_docs} documents."
            ),
        )

        for doc_id in range(0, len(all_docs), self.index_batch_size):
            cur_docs = all_docs[doc_id : doc_id + self.index_batch_size]
            combined_doc = "\n".join(cur_docs)

            # Use insert for incremental updates
            graphrag_func.insert(combined_doc)
            process_doc_count += len(cur_docs)
            yield Document(
                channel="debug",
                text=(
                    f"[GraphRAG] {'Updated' if is_incremental else 'Indexed'} "
                    f"{process_doc_count} / {total_docs} documents."
                ),
            )

        yield Document(
            channel="debug",
            text=f"[GraphRAG] {'Update' if is_incremental else 'Indexing'} finished.",
        )

    def stream(
        self, file_paths: str | Path | list[str | Path], reindex: bool = False, **kwargs
    ) -> Generator[Document, None, tuple[list[str | None], list[str | None], list[Document]]]:
        file_ids, errors, all_docs = yield from super().stream(
            file_paths, reindex=reindex, **kwargs
        )

        return file_ids, errors, all_docs


class NanoGraphRAGRetrieverPipeline(BaseFileIndexRetriever):
    """GraphRAG specific retriever pipeline"""

    Index = Param(help="The SQLAlchemy Index table")
    file_ids: list[str] = []
    search_type: str = "local"

    @classmethod
    def get_user_settings(cls) -> dict:
        return {
            "search_type": {
                "name": "Search type",
                "value": "local",
                "choices": ["local", "global"],
                "component": "dropdown",
                "info": "Whether to use local or global search in the graph.",
            }
        }

    def _build_graph_search(self):
        file_id = self.file_ids[0]

        # retrieve the graph_id from the index
        with Session(engine) as session:
            graph_id = (
                session.query(self.Index.target_id)
                .filter(self.Index.source_id == file_id)
                .filter(self.Index.relation_type == "graph")
                .first()
            )
            graph_id = graph_id[0] if graph_id else None
            assert graph_id, f"GraphRAG index not found for file_id: {file_id}"

        _, input_path = prepare_graph_index_path(filestorage_path, graph_id)
        input_path.mkdir(parents=True, exist_ok=True)

        llm_func, embedding_func, _, _ = get_default_models_wrapper(
            EmbeddingFunc,
            compute_args_hash,
        )
        graphrag_func = build_graphrag(
            input_path,
            llm_func=llm_func,
            embedding_func=embedding_func,
        )
        print("search_type", self.search_type)
        query_params = QueryParam(mode=self.search_type, only_need_context=True)

        return graphrag_func, query_params

    def _to_document(self, header: str, context_text: str) -> RetrievedDocument:
        return build_retrieved_table(header, context_text)

    def format_context_records(
        self, entities, relationships, reports, sources
    ) -> list[RetrievedDocument]:
        docs = []
        context: str = ""

        # entities current parsing error
        header = "<b>Entities</b>\n"
        context = entities[["entity", "description"]].to_markdown(index=False)
        docs.append(self._to_document(header, context))

        header = "\n<b>Relationships</b>\n"
        context = relationships[["source", "target", "description"]].to_markdown(
            index=False
        )
        docs.append(self._to_document(header, context))

        header = "\n<b>Reports</b>\n"
        context = ""
        for _, row in reports.iterrows():
            title, content = row["id"], row["content"]  # not contain title
            context += f"\n\n<h5>Report <b>{title}</b></h5>\n"
            context += content
        docs.append(self._to_document(header, context))

        header = "\n<b>Sources</b>\n"
        context = ""
        for _, row in sources.iterrows():
            title, content = row["id"], row["content"]
            context += f"\n\n<h5>Source <b>#{title}</b></h5>\n"
            context += content
        docs.append(self._to_document(header, context))

        return docs

    def plot_graph(self, relationships):
        G = create_knowledge_graph(relationships)
        plot = visualize_graph(G)
        return plot

    def run(
        self,
        text: str,
    ) -> list[RetrievedDocument]:
        if not self.file_ids:
            return []

        graphrag_func, query_params = self._build_graph_search()

        # only local mode support graph visualization
        if query_params.mode == "local":
            entities, relationships, reports, sources = asyncio.run(
                nano_graph_rag_build_local_query_context(
                    graphrag_func, text, query_params
                )
            )

            documents = self.format_context_records(
                entities, relationships, reports, sources
            )
            plot = self.plot_graph(relationships)

            documents += [
                RetrievedDocument(
                    text="",
                    metadata={
                        "file_name": "GraphRAG",
                        "type": "plot",
                        "data": plot,
                    },
                ),
            ]
        else:
            context = graphrag_func.query(text, query_params)

            documents = [
                RetrievedDocument(
                    text=context,
                    metadata={
                        "file_name": "GraphRAG {} Search".format(
                            query_params.mode.capitalize()
                        ),
                        "type": "table",
                    },
                )
            ]

        return documents
