from api.services.ollama.errors import OllamaError
from api.services.ollama.service import (
    DEFAULT_OLLAMA_BASE_URL,
    OllamaService,
    normalize_ollama_base_url,
    openai_compatible_base_url,
)
from api.services.ollama.model_sync import (
    OLLAMA_RECOMMENDED_EMBEDDINGS,
    OLLAMA_RECOMMENDED_MODELS,
    active_ollama_model,
    active_ollama_embedding_model,
    upsert_ollama_embedding,
    upsert_ollama_llm,
)
from api.services.ollama.launcher import quickstart_payload, start_local_ollama
from api.services.ollama.index_migration import (
    apply_embedding_to_all_indices,
    collect_reindex_targets_for_index,
)

__all__ = [
    "DEFAULT_OLLAMA_BASE_URL",
    "OLLAMA_RECOMMENDED_EMBEDDINGS",
    "OLLAMA_RECOMMENDED_MODELS",
    "OllamaError",
    "OllamaService",
    "apply_embedding_to_all_indices",
    "active_ollama_embedding_model",
    "active_ollama_model",
    "collect_reindex_targets_for_index",
    "normalize_ollama_base_url",
    "openai_compatible_base_url",
    "quickstart_payload",
    "start_local_ollama",
    "upsert_ollama_embedding",
    "upsert_ollama_llm",
]
