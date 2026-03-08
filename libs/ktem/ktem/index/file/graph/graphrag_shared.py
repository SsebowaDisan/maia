import glob
import logging
import os
import re
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from ktem.db.models import engine
from ktem.embeddings.manager import embedding_models_manager as embeddings
from ktem.llms.manager import llms
from maia.base import Document, RetrievedDocument
from maia.base.schema import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.orm import Session
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

INDEX_BATCHSIZE = 4
PROMPT_BLACKLIST_KEYWORDS = ["default", "response", "process"]


def ensure_storage_path(root: Path, folder_name: str) -> Path:
    storage_path = root / folder_name
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


def get_llm_func(model, compute_args_hash_fn: Callable[..., str]):
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((Exception,)),
        after=lambda retry_state: logging.warning(
            f"LLM API call attempt {retry_state.attempt_number} failed. Retrying..."
        ),
    )
    async def _call_model(model, input_messages):
        return (await model.ainvoke(input_messages)).text

    async def llm_func(
        prompt, system_prompt=None, history_messages=[], **kwargs
    ) -> str:
        input_messages = [SystemMessage(text=system_prompt)] if system_prompt else []

        hashing_kv = kwargs.pop("hashing_kv", None)
        if history_messages:
            for msg in history_messages:
                if msg.get("role") == "user":
                    input_messages.append(HumanMessage(text=msg["content"]))
                else:
                    input_messages.append(AIMessage(text=msg["content"]))

        input_messages.append(HumanMessage(text=prompt))

        if hashing_kv is not None:
            args_hash = compute_args_hash_fn("model", input_messages)
            if_cache_return = await hashing_kv.get_by_id(args_hash)
            if if_cache_return is not None:
                return if_cache_return["return"]

        try:
            output = await _call_model(model, input_messages)
        except Exception as exc:
            logging.error(f"Failed to call LLM API after 3 retries: {exc}")
            raise

        print("-" * 50)
        print(output, "\n", "-" * 50)

        if hashing_kv is not None:
            await hashing_kv.upsert({args_hash: {"return": output, "model": "model"}})

        return output

    return llm_func


def get_embedding_func(model):
    async def embedding_func(texts: list[str]) -> np.ndarray:
        outputs = model(texts)
        return np.array([doc.embedding for doc in outputs])

    return embedding_func


def get_default_models_wrapper(embedding_func_cls, compute_args_hash_fn):
    default_embedding = embeddings.get_default()
    default_embedding_dim = len(default_embedding(["Hi"])[0].embedding)
    embedding_func = embedding_func_cls(
        embedding_dim=default_embedding_dim,
        max_token_size=8192,
        func=get_embedding_func(default_embedding),
    )
    print("GraphRAG embedding dim", default_embedding_dim)

    default_llm = llms.get_default()
    llm_func = get_llm_func(default_llm, compute_args_hash_fn)

    return llm_func, embedding_func, default_llm, default_embedding


def prepare_graph_index_path(filestorage_path: Path, graph_id: str):
    root_path = filestorage_path / graph_id
    input_path = root_path / "input"
    return root_path, input_path


def list_of_list_to_df(data: list[list]) -> pd.DataFrame:
    return pd.DataFrame(data[1:], columns=data[0])


def clean_quote(value: str) -> str:
    return re.sub(r"[\"']", "", value)


def build_prompt_settings(prompts: dict[str, Any], batch_size: int) -> dict:
    settings_dict = {
        "batch_size": {
            "name": "Index batch size (reduce if you have rate limit issues)",
            "value": batch_size,
            "component": "number",
        }
    }
    settings_dict.update(
        {
            prompt_name: {
                "name": f"Prompt for '{prompt_name}'",
                "value": content,
                "component": "text",
            }
            for prompt_name, content in prompts.items()
            if all(
                keyword not in prompt_name.lower()
                for keyword in PROMPT_BLACKLIST_KEYWORDS
            )
            and isinstance(content, str)
        }
    )
    return settings_dict


def apply_prompt_overrides(
    prompts: dict[str, Any], overrides: dict[str, str]
) -> None:
    for prompt_name, content in overrides.items():
        if prompt_name in prompts:
            prompts[prompt_name] = content


def collect_text_docs(docs: list[Document]) -> list[str]:
    return [
        doc.text
        for doc in docs
        if doc.metadata.get("type", "text") == "text" and len(doc.text.strip()) > 0
    ]


def clear_json_cache(path: Path) -> None:
    for json_file in glob.glob(f"{path}/*.json"):
        os.remove(json_file)


def store_file_graph_mappings(
    index_model, graph_id: str, file_ids: list[str | None]
) -> None:
    with Session(engine) as session:
        for file_id in file_ids:
            if not file_id:
                continue
            existing = (
                session.query(index_model)
                .filter(
                    index_model.source_id == file_id,
                    index_model.target_id == graph_id,
                    index_model.relation_type == "graph",
                )
                .first()
            )
            if not existing:
                node = index_model(
                    source_id=file_id,
                    target_id=graph_id,
                    relation_type="graph",
                )
                session.add(node)
        session.commit()


def build_retrieved_table(header: str, context_text: str) -> RetrievedDocument:
    return RetrievedDocument(
        text=context_text,
        metadata={
            "file_name": header,
            "type": "table",
            "llm_trulens_score": 1.0,
        },
        score=1.0,
    )
