from api.services.llamacpp.errors import LlamaCppError
from api.services.llamacpp.service import (
    DEFAULT_LLAMACPP_HOST,
    DEFAULT_LLAMACPP_PORT,
    LlamaCppService,
    build_base_url,
    openai_compatible_base_url,
)
from api.services.llamacpp.model_manager import (
    RECOMMENDED_MODELS,
    delete_model,
    download_model,
    get_model_dir,
    list_local_models,
)
from api.services.llamacpp.launcher import (
    get_server_pid,
    is_llamacpp_installed,
    start_llamacpp_server,
    stop_llamacpp_server,
)
from api.services.llamacpp.model_sync import (
    LLAMACPP_EMBEDDING_PREFIX,
    LLAMACPP_MODEL_PREFIX,
    active_llamacpp_embedding,
    active_llamacpp_model,
    upsert_llamacpp_embedding,
    upsert_llamacpp_llm,
)

DEFAULT_LLAMACPP_MODEL_DIR = ""

__all__ = [
    "DEFAULT_LLAMACPP_HOST",
    "DEFAULT_LLAMACPP_MODEL_DIR",
    "DEFAULT_LLAMACPP_PORT",
    "LLAMACPP_EMBEDDING_PREFIX",
    "LLAMACPP_MODEL_PREFIX",
    "LlamaCppError",
    "LlamaCppService",
    "RECOMMENDED_MODELS",
    "active_llamacpp_embedding",
    "active_llamacpp_model",
    "build_base_url",
    "delete_model",
    "download_model",
    "get_model_dir",
    "get_server_pid",
    "is_llamacpp_installed",
    "list_local_models",
    "openai_compatible_base_url",
    "start_llamacpp_server",
    "stop_llamacpp_server",
    "upsert_llamacpp_embedding",
    "upsert_llamacpp_llm",
]
