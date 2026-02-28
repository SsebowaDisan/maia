from __future__ import annotations

from ktem.embeddings.manager import embedding_models_manager
from ktem.llms.manager import llms

from api.services.ollama.service import openai_compatible_base_url

OLLAMA_MODEL_PREFIX = "ollama::"
OLLAMA_EMBEDDING_PREFIX = "ollama-embed::"
OLLAMA_RECOMMENDED_MODELS = [
    "qwen3:8b",
    "llama3.1:8b",
    "llama3:8b",
    "deepseek-r1:8b",
    "qwen3:14b",
    "llama3.2:3b",
]
OLLAMA_RECOMMENDED_EMBEDDINGS = [
    "embeddinggemma",
    "qwen3-embedding:0.6b",
    "nomic-embed-text",
    "mxbai-embed-large",
    "bge-m3",
    "snowflake-arctic-embed2",
    "all-minilm",
]


def active_ollama_model() -> str | None:
    try:
        default_name = llms.get_default_name()
    except Exception:
        return None

    info = llms.info().get(default_name, {})
    spec = info.get("spec", {}) if isinstance(info, dict) else {}
    if not isinstance(spec, dict):
        return None

    model = str(spec.get("model") or "").strip()
    api_key = str(spec.get("api_key") or "").strip().lower()
    if default_name.startswith(OLLAMA_MODEL_PREFIX):
        return model or default_name.replace(OLLAMA_MODEL_PREFIX, "", 1)
    if api_key == "ollama":
        return model or None
    return None


def upsert_ollama_llm(*, model: str, base_url: str, default: bool) -> str:
    model_name = " ".join(str(model or "").split()).strip()
    if not model_name:
        raise ValueError("Model name is required.")

    llm_name = f"{OLLAMA_MODEL_PREFIX}{model_name}"
    llm_spec = {
        "__type__": "maia.llms.ChatOpenAI",
        "temperature": 0,
        "base_url": openai_compatible_base_url(base_url),
        "api_key": "ollama",
        "model": model_name,
        "timeout": 120,
    }
    if llm_name in llms.options():
        llms.update(name=llm_name, spec=llm_spec, default=default)
    else:
        llms.add(name=llm_name, spec=llm_spec, default=default)
    return llm_name


def active_ollama_embedding_model() -> str | None:
    try:
        default_name = embedding_models_manager.get_default_name()
    except Exception:
        return None

    info = embedding_models_manager.info().get(default_name, {})
    spec = info.get("spec", {}) if isinstance(info, dict) else {}
    if not isinstance(spec, dict):
        return None

    model = str(spec.get("model") or spec.get("model_name") or "").strip()
    api_key = str(spec.get("api_key") or "").strip().lower()
    if default_name.startswith(OLLAMA_EMBEDDING_PREFIX):
        return model or default_name.replace(OLLAMA_EMBEDDING_PREFIX, "", 1)
    if api_key == "ollama":
        return model or None
    return None


def upsert_ollama_embedding(*, model: str, base_url: str, default: bool) -> str:
    model_name = " ".join(str(model or "").split()).strip()
    if not model_name:
        raise ValueError("Embedding model name is required.")

    embedding_name = f"{OLLAMA_EMBEDDING_PREFIX}{model_name}"
    embedding_spec = {
        "__type__": "maia.embeddings.OpenAIEmbeddings",
        "api_key": "ollama",
        "base_url": openai_compatible_base_url(base_url),
        "model": model_name,
        "timeout": 120,
        "context_length": 8191,
    }
    if embedding_name in embedding_models_manager.options():
        embedding_models_manager.update(
            name=embedding_name,
            spec=embedding_spec,
            default=default,
        )
    else:
        embedding_models_manager.add(
            name=embedding_name,
            spec=embedding_spec,
            default=default,
        )
    return embedding_name
