from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user_id
from api.context import get_context
from api.services.ingestion_service import get_ingestion_manager
from api.services.ollama import (
    OLLAMA_RECOMMENDED_EMBEDDINGS,
    OLLAMA_RECOMMENDED_MODELS,
    OllamaError,
    OllamaService,
    active_ollama_embedding_model,
    active_ollama_model,
    apply_embedding_to_all_indices,
    quickstart_payload,
    start_local_ollama,
    upsert_ollama_embedding,
    upsert_ollama_llm,
)

from .common import (
    publish_event,
    raise_http_from_ollama,
    resolve_ollama_base_url,
    save_ollama_settings,
    tenant_settings,
)
from .schemas import (
    OllamaConfigRequest,
    OllamaEmbeddingApplyAllRequest,
    OllamaEmbeddingSelectRequest,
    OllamaPullRequest,
    OllamaSelectRequest,
    OllamaStartRequest,
)

router = APIRouter(tags=["agent-integrations"])


@router.get("/integrations/ollama/status")
def ollama_integration_status(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = tenant_settings(user_id)
    base_url = resolve_ollama_base_url(settings=settings)
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
    _, settings = tenant_settings(user_id)
    resolved_base_url = resolve_ollama_base_url(settings=settings, override=base_url)
    return quickstart_payload(base_url=resolved_base_url)


@router.post("/integrations/ollama/start")
def start_ollama(
    payload: OllamaStartRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = tenant_settings(user_id)
    run_id = str(payload.run_id or "").strip() or None
    base_url = resolve_ollama_base_url(settings=settings, override=payload.base_url)

    publish_event(
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
        publish_event(
            user_id=user_id,
            run_id=run_id,
            event_type="ollama.start.failed",
            message="Failed to start Ollama",
            data=exc.to_detail(),
        )
        raise_http_from_ollama(exc)

    save_ollama_settings(
        user_id=user_id,
        existing_settings=settings,
        base_url=base_url,
    )
    publish_event(
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
    _, settings = tenant_settings(user_id)
    base_url = resolve_ollama_base_url(settings=settings, override=payload.base_url)
    save_ollama_settings(
        user_id=user_id,
        existing_settings=settings,
        base_url=base_url,
    )
    publish_event(
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
    _, settings = tenant_settings(user_id)
    resolved_base_url = resolve_ollama_base_url(settings=settings, override=base_url)
    service = OllamaService(base_url=resolved_base_url)
    try:
        models = service.list_models()
    except OllamaError as exc:
        raise_http_from_ollama(exc)

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
    _, settings = tenant_settings(user_id)
    run_id = str(payload.run_id or "").strip() or None
    model = " ".join(str(payload.model or "").split()).strip()
    if not model:
        raise HTTPException(
            status_code=400,
            detail={"code": "ollama_model_missing", "message": "Model name is required."},
        )

    base_url = resolve_ollama_base_url(settings=settings, override=payload.base_url)
    service = OllamaService(base_url=base_url)
    publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="ollama.pull.started",
        message=f"Downloading Ollama model `{model}`",
        data={"model": model, "base_url": base_url},
    )

    latest_percent = -1.0
    latest_status = ""

    def on_progress(update: dict[str, Any]) -> None:
        nonlocal latest_percent, latest_status
        status = str(update.get("status") or "").strip()
        percent = float(update.get("percent") or 0.0)
        rounded_percent = round(percent, 1)
        if status == latest_status and rounded_percent == latest_percent:
            return
        latest_status = status
        latest_percent = rounded_percent
        publish_event(
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
        pull_result = service.pull_model(model=model, on_progress=on_progress)
        models = service.list_models()
    except OllamaError as exc:
        publish_event(
            user_id=user_id,
            run_id=run_id,
            event_type="ollama.pull.failed",
            message=f"Download failed for `{model}`",
            data=exc.to_detail(),
        )
        raise_http_from_ollama(exc)

    model_exists = any(str(item.get("name") or "") == model for item in models)
    selected_llm_name: str | None = None
    if payload.auto_select and model_exists:
        try:
            selected_llm_name = upsert_ollama_llm(model=model, base_url=base_url, default=True)
            save_ollama_settings(
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

    publish_event(
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
    _, settings = tenant_settings(user_id)
    run_id = str(payload.run_id or "").strip() or None
    model = " ".join(str(payload.model or "").split()).strip()
    if not model:
        raise HTTPException(
            status_code=400,
            detail={"code": "ollama_model_missing", "message": "Model name is required."},
        )
    base_url = resolve_ollama_base_url(settings=settings, override=payload.base_url)
    service = OllamaService(base_url=base_url)
    try:
        models = service.list_models()
    except OllamaError as exc:
        raise_http_from_ollama(exc)

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
        save_ollama_settings(
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

    publish_event(
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
    _, settings = tenant_settings(user_id)
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
    base_url = resolve_ollama_base_url(settings=settings, override=payload.base_url)
    service = OllamaService(base_url=base_url)
    try:
        models = service.list_models()
    except OllamaError as exc:
        raise_http_from_ollama(exc)

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
        save_ollama_settings(
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

    publish_event(
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
    _, settings = tenant_settings(user_id)
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

    base_url = resolve_ollama_base_url(settings=settings, override=payload.base_url)
    service = OllamaService(base_url=base_url)
    try:
        models = service.list_models()
    except OllamaError as exc:
        raise_http_from_ollama(exc)

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

    publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="ollama.embedding.apply_all.started",
        message=f"Applying embedding model `{model}` to all collections",
        data={"model": model, "base_url": base_url},
    )

    try:
        embedding_name = upsert_ollama_embedding(model=model, base_url=base_url, default=True)
        save_ollama_settings(
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
        publish_event(
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
        publish_event(
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

    publish_event(
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
