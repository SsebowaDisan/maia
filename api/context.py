from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
from typing import Any

try:
    from decouple import config
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal CI env
    def config(name: str, default: Any = None, **_: Any) -> Any:
        return os.getenv(name, default)


def _bootstrap_local_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    for rel in ("libs/ktem", "libs/maia"):
        lib_path = root / rel
        if lib_path.exists():
            path_str = str(lib_path)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)


_bootstrap_local_imports()

from ktem.embeddings.manager import embedding_models_manager  # noqa: E402
from ktem.llms.manager import llms  # noqa: E402
from ktem.main import App as KtemApp  # noqa: E402


@dataclass
class ApiContext:
    app: KtemApp
    default_settings: dict[str, Any]

    def get_index(self, index_id: int | None = None):
        indices = self.app.index_manager.indices
        if not indices:
            raise ValueError("No indices are configured.")

        if index_id is None:
            return indices[0]

        for index in indices:
            if index.id == index_id:
                return index

        raise ValueError(f"Index with id `{index_id}` was not found.")


PLACEHOLDER_KEYS = {
    "",
    "your-key",
    "<your_openai_key>",
    "changeme",
    "none",
    "null",
}


def _is_placeholder_api_key(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return normalized in PLACEHOLDER_KEYS


def _compatible_llm_env(primary_key: str, legacy_key: str, default: str = "") -> str:
    primary_value = str(config(primary_key, default="") or "").strip()
    if primary_value:
        return primary_value
    legacy_value = str(config(legacy_key, default="") or "").strip()
    if legacy_value:
        return legacy_value
    return default


def _has_explicit_compatible_llm_config(*, require_embeddings: bool = False) -> bool:
    api_key = _compatible_llm_env("MAIA_LLM_API_KEY", "OPENAI_API_KEY", "")
    base_url = _compatible_llm_env("MAIA_LLM_API_BASE", "OPENAI_API_BASE", "")
    model_key = "MAIA_LLM_EMBEDDINGS_MODEL" if require_embeddings else "MAIA_LLM_CHAT_MODEL"
    legacy_model_key = "OPENAI_EMBEDDINGS_MODEL" if require_embeddings else "OPENAI_CHAT_MODEL"
    model = _compatible_llm_env(model_key, legacy_model_key, "")
    if _is_placeholder_api_key(api_key):
        return False
    return bool(base_url and model)


def _default_embedding_uses_placeholder_key() -> bool:
    try:
        default_name = embedding_models_manager.get_default_name()
    except Exception:
        return True

    info = embedding_models_manager.info().get(default_name, {})
    spec = info.get("spec", {}) if isinstance(info, dict) else {}
    if not isinstance(spec, dict):
        return False

    for key in ("api_key", "google_api_key", "cohere_api_key"):
        if key in spec and _is_placeholder_api_key(spec.get(key)):
            return True
    return False


def _llm_uses_placeholder_key(llm_name: str) -> bool:
    name = str(llm_name or "").strip()
    if not name:
        return True
    try:
        all_info = llms.info()
    except Exception:
        return True
    info = all_info.get(name, {})
    spec = info.get("spec", {}) if isinstance(info, dict) else {}
    if not isinstance(spec, dict):
        return False

    has_api_key_field = False
    for key, value in spec.items():
        if not isinstance(key, str):
            continue
        if "api_key" not in key.lower():
            continue
        has_api_key_field = True
        if _is_placeholder_api_key(value):
            return True

    # Local models usually do not expose api_key fields.
    return False if not has_api_key_field else False


def _default_llm_uses_placeholder_key() -> bool:
    try:
        default_name = llms.get_default_name()
    except Exception:
        return True
    return _llm_uses_placeholder_key(default_name)


def _ensure_local_embedding_default() -> None:
    # If current default requires an external key but only placeholder values are
    # configured, switch to a local embedding to keep uploads/indexing functional.
    if not _default_embedding_uses_placeholder_key():
        return

    local_name = "fast_embed_local"
    local_spec = {
        "__type__": "maia.embeddings.FastEmbedEmbeddings",
        "model_name": "BAAI/bge-small-en-v1.5",
    }

    models = embedding_models_manager.options()
    if local_name not in models:
        embedding_models_manager.add(name=local_name, spec=local_spec, default=True)
        return

    existing = embedding_models_manager.info().get(local_name, {})
    existing_spec = existing.get("spec", {}) if isinstance(existing, dict) else {}
    embedding_models_manager.update(
        name=local_name,
        spec=existing_spec if isinstance(existing_spec, dict) and existing_spec else local_spec,
        default=True,
    )


def _ensure_openai_llm_default() -> None:
    if not _has_explicit_compatible_llm_config():
        return
    env_llm_key = _compatible_llm_env("MAIA_LLM_API_KEY", "OPENAI_API_KEY", "")

    openai_name = "openai"
    openai_spec = {
        "__type__": "maia.llms.ChatOpenAI",
        "temperature": 0,
        "base_url": _compatible_llm_env("MAIA_LLM_API_BASE", "OPENAI_API_BASE", ""),
        "api_key": env_llm_key,
        "model": _compatible_llm_env("MAIA_LLM_CHAT_MODEL", "OPENAI_CHAT_MODEL", ""),
        "timeout": 20,
    }

    try:
        all_info = llms.info()
        default_is_placeholder = _default_llm_uses_placeholder_key()
        has_explicit_default = any(
            bool(item.get("default"))
            for item in all_info.values()
            if isinstance(item, dict)
        )
        should_default_if_new = (not has_explicit_default) or default_is_placeholder

        if openai_name not in llms.options():
            llms.add(name=openai_name, spec=openai_spec, default=should_default_if_new)
            return

        existing_info = llms.info().get(openai_name, {})
        existing_spec = existing_info.get("spec", {}) if isinstance(existing_info, dict) else {}
        merged_spec = dict(existing_spec) if isinstance(existing_spec, dict) else {}
        merged_spec.update(openai_spec)
        keep_default = bool(existing_info.get("default")) if isinstance(existing_info, dict) else False
        llms.update(
            name=openai_name,
            spec=merged_spec,
            default=bool(keep_default or default_is_placeholder),
        )
    except Exception:
        # Keep API startup resilient even if model pool update fails.
        return


def _ensure_viable_llm_default() -> None:
    # If current default uses placeholder credentials, promote the first model
    # with non-placeholder credentials (for example OpenAI with real key, or
    # local Ollama entries that use api_key=ollama).
    if not _default_llm_uses_placeholder_key():
        return

    try:
        all_info = llms.info()
    except Exception:
        return

    candidate_names: list[str] = []
    if "openai" in all_info:
        candidate_names.append("openai")
    for name in all_info.keys():
        if name not in candidate_names:
            candidate_names.append(name)

    for name in candidate_names:
        if _llm_uses_placeholder_key(name):
            continue
        info = all_info.get(name, {})
        spec = info.get("spec", {}) if isinstance(info, dict) else {}
        if not isinstance(spec, dict):
            continue
        try:
            llms.update(name=name, spec=dict(spec), default=True)
            return
        except Exception:
            continue


def _ensure_openai_embedding_default() -> None:
    if not _has_explicit_compatible_llm_config(require_embeddings=True):
        return
    env_llm_key = _compatible_llm_env("MAIA_LLM_API_KEY", "OPENAI_API_KEY", "")

    openai_name = "openai"
    openai_spec = {
        "__type__": "maia.embeddings.OpenAIEmbeddings",
        "base_url": _compatible_llm_env("MAIA_LLM_API_BASE", "OPENAI_API_BASE", ""),
        "api_key": env_llm_key,
        "model": _compatible_llm_env("MAIA_LLM_EMBEDDINGS_MODEL", "OPENAI_EMBEDDINGS_MODEL", ""),
        "timeout": 20,
        "context_length": 8191,
    }

    try:
        all_info = embedding_models_manager.info()
        has_explicit_default = any(
            bool(item.get("default"))
            for item in all_info.values()
            if isinstance(item, dict)
        )
        should_default_if_new = not has_explicit_default

        if openai_name not in embedding_models_manager.options():
            embedding_models_manager.add(
                name=openai_name,
                spec=openai_spec,
                default=should_default_if_new,
            )
            return

        existing_info = embedding_models_manager.info().get(openai_name, {})
        existing_spec = existing_info.get("spec", {}) if isinstance(existing_info, dict) else {}
        merged_spec = dict(existing_spec) if isinstance(existing_spec, dict) else {}
        merged_spec.update(openai_spec)
        keep_default = bool(existing_info.get("default")) if isinstance(existing_info, dict) else False
        embedding_models_manager.update(
            name=openai_name,
            spec=merged_spec,
            default=keep_default,
        )
    except Exception:
        return


@lru_cache(maxsize=1)
def get_context() -> ApiContext:
    _ensure_openai_llm_default()
    _ensure_viable_llm_default()
    _ensure_openai_embedding_default()
    _ensure_local_embedding_default()
    app = KtemApp()
    default_settings = app.default_settings.flatten()
    return ApiContext(app=app, default_settings=default_settings)
