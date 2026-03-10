from __future__ import annotations

from pathlib import Path

from ktem.embeddings.manager import embedding_models_manager
from ktem.llms.manager import llms

from api.services.llamacpp.service import openai_compatible_base_url

LLAMACPP_MODEL_PREFIX = "llamacpp::"
LLAMACPP_EMBEDDING_PREFIX = "llamacpp-embed::"


def _model_stem(filename: str) -> str:
    """Return filename without .gguf extension."""
    return Path(filename).stem


def active_llamacpp_model() -> str | None:
    try:
        default_name = llms.get_default_name()
    except Exception:
        return None
    if not default_name.startswith(LLAMACPP_MODEL_PREFIX):
        info = llms.info().get(default_name, {})
        spec = info.get("spec", {}) if isinstance(info, dict) else {}
        if not isinstance(spec, dict):
            return None
        api_key = str(spec.get("api_key") or "").strip().lower()
        if api_key != "llamacpp":
            return None
        return str(spec.get("model") or "").strip() or None
    return default_name.replace(LLAMACPP_MODEL_PREFIX, "", 1)


def active_llamacpp_embedding() -> str | None:
    try:
        default_name = embedding_models_manager.get_default_name()
    except Exception:
        return None
    if not default_name.startswith(LLAMACPP_EMBEDDING_PREFIX):
        info = embedding_models_manager.info().get(default_name, {})
        spec = info.get("spec", {}) if isinstance(info, dict) else {}
        if not isinstance(spec, dict):
            return None
        api_key = str(spec.get("api_key") or "").strip().lower()
        if api_key != "llamacpp":
            return None
        return str(spec.get("model") or "").strip() or None
    return default_name.replace(LLAMACPP_EMBEDDING_PREFIX, "", 1)


def upsert_llamacpp_llm(*, model_filename: str, base_url: str, default: bool) -> str:
    filename = str(model_filename or "").strip()
    if not filename:
        raise ValueError("Model filename is required.")
    stem = _model_stem(filename)
    llm_name = f"{LLAMACPP_MODEL_PREFIX}{stem}"
    llm_spec = {
        "__type__": "maia.llms.ChatOpenAI",
        "temperature": 0,
        "base_url": openai_compatible_base_url(base_url),
        "api_key": "llamacpp",
        "model": filename,
        "timeout": 120,
    }
    if llm_name in llms.options():
        llms.update(name=llm_name, spec=llm_spec, default=default)
    else:
        llms.add(name=llm_name, spec=llm_spec, default=default)
    return llm_name


def upsert_llamacpp_embedding(*, model_filename: str, base_url: str, default: bool) -> str:
    filename = str(model_filename or "").strip()
    if not filename:
        raise ValueError("Embedding model filename is required.")
    stem = _model_stem(filename)
    embedding_name = f"{LLAMACPP_EMBEDDING_PREFIX}{stem}"
    embedding_spec = {
        "__type__": "maia.embeddings.OpenAIEmbeddings",
        "api_key": "llamacpp",
        "base_url": openai_compatible_base_url(base_url),
        "model": filename,
        "timeout": 120,
        "context_length": 8191,
    }
    if embedding_name in embedding_models_manager.options():
        embedding_models_manager.update(name=embedding_name, spec=embedding_spec, default=default)
    else:
        embedding_models_manager.add(name=embedding_name, spec=embedding_spec, default=default)
    return embedding_name
