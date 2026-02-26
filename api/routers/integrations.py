from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth import get_current_user_id
from api.context import get_context
from api.services.agent.auth.credentials import get_credential_store
from api.services.agent.live_events import get_live_event_broker
from api.services.ingestion_service import get_ingestion_manager
from api.services.ollama import (
    DEFAULT_OLLAMA_BASE_URL,
    OLLAMA_RECOMMENDED_EMBEDDINGS,
    OLLAMA_RECOMMENDED_MODELS,
    OllamaError,
    OllamaService,
    apply_embedding_to_all_indices,
    active_ollama_embedding_model,
    active_ollama_model,
    normalize_ollama_base_url,
    quickstart_payload,
    start_local_ollama,
    upsert_ollama_embedding,
    upsert_ollama_llm,
)
from api.services.search.brave_search import BraveSearchService
from api.services.search.errors import BraveSearchError
from api.services.settings_service import load_user_settings, save_user_settings

router = APIRouter(prefix="/api/agent", tags=["agent-integrations"])

MAPS_CONNECTOR_ID = "google_maps"
BRAVE_CONNECTOR_ID = "brave_search"


class MapsSaveRequest(BaseModel):
    api_key: str = Field(min_length=16, max_length=512)


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    count: int = Field(default=10, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=200)
    country: str = Field(default="BE", min_length=2, max_length=2)
    safesearch: str = Field(default="moderate", min_length=2, max_length=20)
    domain: str | None = Field(default=None, max_length=255)
    run_id: str | None = Field(default=None, max_length=120)


class OllamaConfigRequest(BaseModel):
    base_url: str = Field(default=DEFAULT_OLLAMA_BASE_URL, min_length=8, max_length=256)


class OllamaPullRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=8, max_length=256)
    auto_select: bool = True
    run_id: str | None = Field(default=None, max_length=120)


class OllamaSelectRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=8, max_length=256)
    run_id: str | None = Field(default=None, max_length=120)


class OllamaEmbeddingSelectRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=8, max_length=256)
    run_id: str | None = Field(default=None, max_length=120)


class OllamaStartRequest(BaseModel):
    base_url: str | None = Field(default=None, min_length=8, max_length=256)
    wait_seconds: int = Field(default=10, ge=2, le=30)
    run_id: str | None = Field(default=None, max_length=120)


class OllamaEmbeddingApplyAllRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    base_url: str | None = Field(default=None, min_length=8, max_length=256)
    run_id: str | None = Field(default=None, max_length=120)


def _tenant_settings(user_id: str) -> tuple[str, dict[str, Any]]:
    settings = load_user_settings(get_context(), user_id)
    tenant_id = str(settings.get("agent.tenant_id") or user_id)
    return tenant_id, settings


def _resolve_maps_env_key() -> str:
    return (
        str(os.getenv("GOOGLE_MAPS_API_KEY", "")).strip()
        or str(os.getenv("GOOGLE_PLACES_API_KEY", "")).strip()
        or str(os.getenv("GOOGLE_GEO_API_KEY", "")).strip()
    )


def _resolve_brave_env_key() -> str:
    return str(os.getenv("BRAVE_SEARCH_API_KEY", "")).strip()


def _resolve_ollama_base_url(
    *,
    settings: dict[str, Any],
    override: str | None = None,
) -> str:
    candidate = (
        str(override or "").strip()
        or str(settings.get("agent.ollama.base_url") or "").strip()
        or str(os.getenv("OLLAMA_BASE_URL", "")).strip()
        or DEFAULT_OLLAMA_BASE_URL
    )
    return normalize_ollama_base_url(candidate)


def _stored_secret(tenant_id: str, connector_id: str, key_name: str) -> str:
    record = get_credential_store().get(tenant_id=tenant_id, connector_id=connector_id)
    if record is None:
        return ""
    return str(record.values.get(key_name) or "").strip()


def _publish_event(
    *,
    user_id: str,
    run_id: str | None,
    event_type: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    payload = {
        "type": event_type,
        "message": message,
        "data": dict(data or {}),
    }
    get_live_event_broker().publish(user_id=user_id, run_id=run_id, event=payload)


def _raise_http_from_ollama(exc: OllamaError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


def _save_ollama_settings(
    *,
    user_id: str,
    existing_settings: dict[str, Any],
    base_url: str,
    default_model: str | None = None,
    embedding_model: str | None = None,
) -> None:
    next_settings = deepcopy(existing_settings)
    next_settings["agent.ollama.base_url"] = normalize_ollama_base_url(base_url)
    if default_model is not None:
        next_settings["agent.ollama.default_model"] = str(default_model).strip()
    if embedding_model is not None:
        next_settings["agent.ollama.embedding_model"] = str(embedding_model).strip()
    save_user_settings(
        context=get_context(),
        user_id=user_id,
        values=next_settings,
    )


@router.get("/integrations/maps/status")
def maps_integration_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id, _ = _tenant_settings(user_id)
    env_key = _resolve_maps_env_key()
    stored_key = _stored_secret(tenant_id, MAPS_CONNECTOR_ID, "GOOGLE_MAPS_API_KEY")
    source: str | None = None
    if env_key:
        source = "env"
    elif stored_key:
        source = "stored"
    return {
        "configured": bool(source),
        "source": source,
    }


@router.post("/integrations/maps/save")
def save_maps_integration_key(
    payload: MapsSaveRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    api_key = str(payload.api_key or "").strip()
    if len(api_key) < 16:
        raise HTTPException(
            status_code=400,
            detail={"code": "maps_api_key_invalid", "message": "Maps API key is invalid."},
        )
    tenant_id, _ = _tenant_settings(user_id)
    get_credential_store().set(
        tenant_id=tenant_id,
        connector_id=MAPS_CONNECTOR_ID,
        values={"GOOGLE_MAPS_API_KEY": api_key},
    )
    _publish_event(
        user_id=user_id,
        run_id=None,
        event_type="integrations.maps.saved",
        message="Maps API key saved to secure server store",
    )
    return {"status": "saved", "configured": True}


@router.post("/integrations/maps/clear")
def clear_maps_integration_key(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id, _ = _tenant_settings(user_id)
    deleted = get_credential_store().delete(tenant_id=tenant_id, connector_id=MAPS_CONNECTOR_ID)
    _publish_event(
        user_id=user_id,
        run_id=None,
        event_type="integrations.maps.cleared",
        message="Stored Maps API key cleared",
    )
    return {"status": "cleared", "cleared": bool(deleted)}


@router.get("/integrations/ollama/status")
def ollama_integration_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = _tenant_settings(user_id)
    base_url = _resolve_ollama_base_url(settings=settings)
    active_model = active_ollama_model() or str(settings.get("agent.ollama.default_model") or "").strip() or None
    active_embedding_model = (
        active_ollama_embedding_model()
        or str(settings.get("agent.ollama.embedding_model") or "").strip()
        or None
    )
    service = OllamaService(base_url=base_url)
    try:
        version = service.get_version()
        models = service.list_models()
        return {
            "configured": True,
            "reachable": True,
            "base_url": base_url,
            "version": version,
            "active_model": active_model,
            "active_embedding_model": active_embedding_model,
            "models": models,
            "recommended_models": OLLAMA_RECOMMENDED_MODELS,
            "recommended_embedding_models": OLLAMA_RECOMMENDED_EMBEDDINGS,
        }
    except OllamaError as exc:
        return {
            "configured": False,
            "reachable": False,
            "base_url": base_url,
            "version": None,
            "active_model": active_model,
            "active_embedding_model": active_embedding_model,
            "models": [],
            "recommended_models": OLLAMA_RECOMMENDED_MODELS,
            "recommended_embedding_models": OLLAMA_RECOMMENDED_EMBEDDINGS,
            "error": exc.to_detail(),
        }


@router.get("/integrations/ollama/quickstart")
def ollama_quickstart(
    base_url: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = _tenant_settings(user_id)
    resolved_base_url = _resolve_ollama_base_url(settings=settings, override=base_url)
    return quickstart_payload(base_url=resolved_base_url)


@router.post("/integrations/ollama/start")
def start_ollama(
    payload: OllamaStartRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = _tenant_settings(user_id)
    run_id = str(payload.run_id or "").strip() or None
    base_url = _resolve_ollama_base_url(settings=settings, override=payload.base_url)

    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="ollama.start.requested",
        message="Starting local Ollama server",
        data={"base_url": base_url},
    )
    try:
        result = start_local_ollama(
            base_url=base_url,
            wait_seconds=payload.wait_seconds,
        )
    except OllamaError as exc:
        _publish_event(
            user_id=user_id,
            run_id=run_id,
            event_type="ollama.start.failed",
            message="Failed to start Ollama",
            data=exc.to_detail(),
        )
        _raise_http_from_ollama(exc)

    _save_ollama_settings(
        user_id=user_id,
        existing_settings=settings,
        base_url=base_url,
    )
    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="ollama.start.completed",
        message="Ollama startup command executed",
        data=result,
    )
    return {
        "base_url": base_url,
        **result,
    }


@router.post("/integrations/ollama/config")
def save_ollama_config(
    payload: OllamaConfigRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = _tenant_settings(user_id)
    base_url = normalize_ollama_base_url(payload.base_url)
    _save_ollama_settings(
        user_id=user_id,
        existing_settings=settings,
        base_url=base_url,
    )
    _publish_event(
        user_id=user_id,
        run_id=None,
        event_type="integrations.ollama.config.saved",
        message="Saved Ollama base URL",
        data={"base_url": base_url},
    )
    return {"status": "saved", "base_url": base_url}


@router.get("/integrations/ollama/models")
def list_ollama_models(
    base_url: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = _tenant_settings(user_id)
    resolved_base_url = _resolve_ollama_base_url(settings=settings, override=base_url)
    service = OllamaService(base_url=resolved_base_url)
    try:
        models = service.list_models()
    except OllamaError as exc:
        _raise_http_from_ollama(exc)

    return {
        "base_url": resolved_base_url,
        "total": len(models),
        "models": models,
    }


@router.post("/integrations/ollama/pull")
def pull_ollama_model(
    payload: OllamaPullRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = _tenant_settings(user_id)
    run_id = str(payload.run_id or "").strip() or None
    model = " ".join(str(payload.model or "").split()).strip()
    if not model:
        raise HTTPException(
            status_code=400,
            detail={"code": "ollama_model_missing", "message": "Model name is required."},
        )

    base_url = _resolve_ollama_base_url(settings=settings, override=payload.base_url)
    service = OllamaService(base_url=base_url)
    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="ollama.pull.started",
        message=f"Downloading Ollama model `{model}`",
        data={"model": model, "base_url": base_url},
    )

    latest_percent = -1.0
    latest_status = ""

    def _on_progress(update: dict[str, Any]) -> None:
        nonlocal latest_percent, latest_status
        status = str(update.get("status") or "").strip()
        percent = float(update.get("percent") or 0.0)
        rounded_percent = round(percent, 1)
        if status == latest_status and rounded_percent == latest_percent:
            return
        latest_status = status
        latest_percent = rounded_percent
        _publish_event(
            user_id=user_id,
            run_id=run_id,
            event_type="ollama.pull.progress",
            message=f"{status or 'downloading'} ({rounded_percent}%)",
            data={
                "model": model,
                "status": status,
                "percent": rounded_percent,
                "completed": int(update.get("completed") or 0),
                "total": int(update.get("total") or 0),
            },
        )

    try:
        pull_result = service.pull_model(model=model, on_progress=_on_progress)
        models = service.list_models()
    except OllamaError as exc:
        _publish_event(
            user_id=user_id,
            run_id=run_id,
            event_type="ollama.pull.failed",
            message=f"Download failed for `{model}`",
            data=exc.to_detail(),
        )
        _raise_http_from_ollama(exc)

    model_exists = any(str(item.get("name") or "") == model for item in models)
    selected_llm_name: str | None = None
    if payload.auto_select and model_exists:
        try:
            selected_llm_name = upsert_ollama_llm(model=model, base_url=base_url, default=True)
            _save_ollama_settings(
                user_id=user_id,
                existing_settings=settings,
                base_url=base_url,
                default_model=model,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "ollama_model_activate_failed",
                    "message": "Model downloaded but failed to activate in Maia.",
                    "details": {"error": str(exc), "model": model},
                },
            ) from exc

    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="ollama.pull.completed",
        message=f"Ollama model `{model}` is ready",
        data={
            "model": model,
            "selected_llm_name": selected_llm_name,
            "total_models": len(models),
        },
    )
    return {
        "status": "ok",
        "base_url": base_url,
        "pull": pull_result,
        "selected_llm_name": selected_llm_name,
        "models": models,
        "active_model": model if selected_llm_name else active_ollama_model(),
    }


@router.post("/integrations/ollama/select")
def select_ollama_model(
    payload: OllamaSelectRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = _tenant_settings(user_id)
    run_id = str(payload.run_id or "").strip() or None
    model = " ".join(str(payload.model or "").split()).strip()
    if not model:
        raise HTTPException(
            status_code=400,
            detail={"code": "ollama_model_missing", "message": "Model name is required."},
        )
    base_url = _resolve_ollama_base_url(settings=settings, override=payload.base_url)
    service = OllamaService(base_url=base_url)
    try:
        models = service.list_models()
    except OllamaError as exc:
        _raise_http_from_ollama(exc)

    model_names = {str(item.get("name") or "") for item in models}
    if model not in model_names:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ollama_model_not_found",
                "message": f"Model `{model}` is not downloaded locally.",
                "details": {"base_url": base_url},
            },
        )

    try:
        llm_name = upsert_ollama_llm(model=model, base_url=base_url, default=True)
        _save_ollama_settings(
            user_id=user_id,
            existing_settings=settings,
            base_url=base_url,
            default_model=model,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "ollama_model_select_failed",
                "message": "Failed to select Ollama model in Maia.",
                "details": {"error": str(exc), "model": model},
            },
        ) from exc

    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="ollama.model.selected",
        message=f"Selected Ollama model `{model}` for chat",
        data={"model": model, "llm_name": llm_name},
    )
    return {
        "status": "selected",
        "model": model,
        "llm_name": llm_name,
        "base_url": base_url,
    }


@router.post("/integrations/ollama/embeddings/select")
def select_ollama_embedding_model(
    payload: OllamaEmbeddingSelectRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = _tenant_settings(user_id)
    run_id = str(payload.run_id or "").strip() or None
    model = " ".join(str(payload.model or "").split()).strip()
    if not model:
        raise HTTPException(
            status_code=400,
            detail={"code": "ollama_embedding_model_missing", "message": "Embedding model name is required."},
        )
    base_url = _resolve_ollama_base_url(settings=settings, override=payload.base_url)
    service = OllamaService(base_url=base_url)
    try:
        models = service.list_models()
    except OllamaError as exc:
        _raise_http_from_ollama(exc)

    model_names = {str(item.get("name") or "") for item in models}
    if model not in model_names:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ollama_embedding_model_not_found",
                "message": f"Model `{model}` is not downloaded locally.",
                "details": {"base_url": base_url},
            },
        )

    try:
        embedding_name = upsert_ollama_embedding(model=model, base_url=base_url, default=True)
        _save_ollama_settings(
            user_id=user_id,
            existing_settings=settings,
            base_url=base_url,
            embedding_model=model,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "ollama_embedding_select_failed",
                "message": "Failed to select Ollama embedding model in Maia.",
                "details": {"error": str(exc), "model": model},
            },
        ) from exc

    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="ollama.embedding.selected",
        message=f"Selected Ollama embedding model `{model}`",
        data={"model": model, "embedding_name": embedding_name},
    )
    return {
        "status": "selected",
        "model": model,
        "embedding_name": embedding_name,
        "base_url": base_url,
    }


@router.post("/integrations/ollama/embeddings/apply-all")
def apply_ollama_embedding_to_all_collections(
    payload: OllamaEmbeddingApplyAllRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    context = get_context()
    _, settings = _tenant_settings(user_id)
    run_id = str(payload.run_id or "").strip() or None
    model = " ".join(str(payload.model or "").split()).strip()
    if not model:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "ollama_embedding_model_missing",
                "message": "Embedding model name is required.",
            },
        )

    base_url = _resolve_ollama_base_url(settings=settings, override=payload.base_url)
    service = OllamaService(base_url=base_url)
    try:
        models = service.list_models()
    except OllamaError as exc:
        _raise_http_from_ollama(exc)

    model_names = {str(item.get("name") or "") for item in models}
    if model not in model_names:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ollama_embedding_model_not_found",
                "message": f"Model `{model}` is not downloaded locally.",
                "details": {"base_url": base_url},
            },
        )

    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="ollama.embedding.apply_all.started",
        message=f"Applying embedding model `{model}` to all collections",
        data={"model": model, "base_url": base_url},
    )

    try:
        embedding_name = upsert_ollama_embedding(model=model, base_url=base_url, default=True)
        _save_ollama_settings(
            user_id=user_id,
            existing_settings=settings,
            base_url=base_url,
            embedding_model=model,
        )
        summary = apply_embedding_to_all_indices(
            context=context,
            user_id=user_id,
            embedding_name=embedding_name,
            ingestion_manager=get_ingestion_manager(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        _publish_event(
            user_id=user_id,
            run_id=run_id,
            event_type="ollama.embedding.apply_all.failed",
            message="Failed to apply embedding model to all collections",
            data={"model": model, "error": str(exc)},
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "ollama_embedding_apply_all_failed",
                "message": "Failed to apply embedding model and queue reindex jobs.",
                "details": {"error": str(exc), "model": model},
            },
        ) from exc

    for index_summary in summary["indexes"]:
        _publish_event(
            user_id=user_id,
            run_id=run_id,
            event_type="ollama.embedding.apply_all.index",
            message=(
                f"Collection `{index_summary['index_name']}` queued "
                f"{index_summary['files_queued']} file(s), {index_summary['urls_queued']} URL(s)"
            ),
            data={
                "index_id": index_summary["index_id"],
                "embedding_updated": index_summary["embedding_updated"],
                "files_queued": index_summary["files_queued"],
                "urls_queued": index_summary["urls_queued"],
                "file_job_id": index_summary["file_job_id"],
                "url_job_id": index_summary["url_job_id"],
            },
        )

    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="ollama.embedding.apply_all.completed",
        message=(
            "Embedding applied across collections and reindex jobs queued "
            f"({summary['jobs_total']} job(s))"
        ),
        data={
            "model": model,
            "embedding_name": embedding_name,
            "jobs_total": summary["jobs_total"],
            "indexes_total": summary["indexes_total"],
            "indexes_updated": summary["indexes_updated"],
        },
    )

    return {
        "status": "queued",
        "model": model,
        "embedding_name": embedding_name,
        "base_url": base_url,
        **summary,
    }


@router.get("/integrations/brave/status")
def brave_integration_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id, _ = _tenant_settings(user_id)
    env_key = _resolve_brave_env_key()
    stored_key = _stored_secret(tenant_id, BRAVE_CONNECTOR_ID, "BRAVE_SEARCH_API_KEY")
    source: str | None = None
    if env_key:
        source = "env"
    elif stored_key:
        source = "stored"
    return {
        "configured": bool(source),
        "source": source,
    }


@router.post("/tools/web_search")
def run_web_search(
    payload: WebSearchRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    tenant_id, _ = _tenant_settings(user_id)
    key = _resolve_brave_env_key() or _stored_secret(tenant_id, BRAVE_CONNECTOR_ID, "BRAVE_SEARCH_API_KEY")
    if not key:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "brave_api_key_missing",
                "message": "BRAVE_SEARCH_API_KEY is not configured.",
            },
        )

    run_id = str(payload.run_id or "").strip() or None
    query = " ".join(str(payload.query or "").split())
    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="status",
        message="Searching web...",
        data={"provider": "brave"},
    )
    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="brave.search.query",
        message="Running Brave search query",
        data={"query": query, "domain": payload.domain or None},
    )

    try:
        service = BraveSearchService(api_key=key)
        if payload.domain:
            result = service.site_search(
                domain=payload.domain,
                query=query,
                count=payload.count,
                offset=payload.offset,
                country=payload.country,
                safesearch=payload.safesearch,
            )
        else:
            result = service.web_search(
                query=query,
                count=payload.count,
                offset=payload.offset,
                country=payload.country,
                safesearch=payload.safesearch,
            )
    except BraveSearchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "brave_search_failed",
                "message": "Brave search request failed.",
                "details": {"error": str(exc)},
            },
        ) from exc

    rows = result.get("results")
    results = rows if isinstance(rows, list) else []
    top_urls = [str(item.get("url") or "") for item in results if isinstance(item, dict)][:5]
    _publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="brave.search.results",
        message=f"Brave search returned {len(results)} result(s)",
        data={"top_urls": top_urls},
    )
    return result
