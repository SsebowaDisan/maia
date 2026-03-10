from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user_id
from api.context import get_context
from api.services.llamacpp import (
    LlamaCppError,
    LlamaCppService,
    RECOMMENDED_MODELS,
    active_llamacpp_embedding,
    active_llamacpp_model,
    build_base_url,
    download_model,
    get_model_dir,
    get_server_pid,
    is_llamacpp_installed,
    list_local_models,
    start_llamacpp_server,
    stop_llamacpp_server,
    upsert_llamacpp_embedding,
    upsert_llamacpp_llm,
)
from api.services.settings_service import save_user_settings

from .common import publish_event, tenant_settings
from .schemas import (
    LlamaCppConfigRequest,
    LlamaCppDownloadRequest,
    LlamaCppSelectRequest,
    LlamaCppStartRequest,
)

router = APIRouter(tags=["agent-integrations"])


def _resolve_base_url(settings: dict[str, Any]) -> str:
    port = int(settings.get("agent.llamacpp.port") or 8082)
    return build_base_url(port=port)


def _raise_from_llamacpp(exc: LlamaCppError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.to_detail()) from exc


@router.get("/integrations/llamacpp/status")
def llamacpp_status(user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    _, settings = tenant_settings(user_id)
    base_url = _resolve_base_url(settings)
    port = int(settings.get("agent.llamacpp.port") or 8082)
    installed = is_llamacpp_installed()
    service = LlamaCppService(base_url=base_url)
    reachable = service.is_reachable() if installed else False
    server_models = service.list_models() if reachable else []
    active_model = active_llamacpp_model() or str(settings.get("agent.llamacpp.active_model") or "").strip() or None
    active_embed = (
        active_llamacpp_embedding()
        or str(settings.get("agent.llamacpp.active_embedding") or "").strip()
        or None
    )
    return {
        "installed": installed,
        "reachable": reachable,
        "port": port,
        "pid": get_server_pid(port),
        "base_url": base_url,
        "active_model": active_model,
        "active_embedding": active_embed,
        "server_models": server_models,
    }


@router.get("/integrations/llamacpp/catalog")
def llamacpp_catalog(user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    return {"models": RECOMMENDED_MODELS}


@router.get("/integrations/llamacpp/models")
def list_llamacpp_models(user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    _, settings = tenant_settings(user_id)
    models = list_local_models(settings)
    return {"total": len(models), "models": models}


@router.post("/integrations/llamacpp/download")
def download_llamacpp_model(
    payload: LlamaCppDownloadRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = tenant_settings(user_id)
    run_id = str(payload.run_id or "").strip() or None
    url = str(payload.url or "").strip()
    filename = str(payload.filename or "").strip()

    if not url:
        raise HTTPException(status_code=400, detail="url is required.")
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required.")
    if not filename.endswith(".gguf"):
        raise HTTPException(status_code=400, detail="filename must end with .gguf")

    model_dir = get_model_dir(settings)

    def on_progress(update: dict[str, Any]) -> None:
        publish_event(
            user_id=user_id,
            run_id=run_id,
            event_type="llamacpp.download.progress",
            message=f"Downloading {filename}: {update.get('percent', 0):.1f}%",
            data={"filename": filename, **update},
        )

    publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="llamacpp.download.started",
        message=f"Starting download: {filename}",
        data={"filename": filename, "url": url},
    )

    try:
        result = download_model(url=url, filename=filename, model_dir=model_dir, on_progress=on_progress)
    except LlamaCppError as exc:
        publish_event(
            user_id=user_id,
            run_id=run_id,
            event_type="llamacpp.download.failed",
            message=f"Download failed: {filename}",
            data=exc.to_detail(),
        )
        _raise_from_llamacpp(exc)

    publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="llamacpp.download.completed",
        message=f"Download complete: {filename}",
        data=result,
    )
    return {"status": "downloaded", **result}


@router.post("/integrations/llamacpp/start")
def start_llamacpp(
    payload: LlamaCppStartRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = tenant_settings(user_id)
    run_id = str(payload.run_id or "").strip() or None
    filename = str(payload.model_filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="model_filename is required.")

    port = int(payload.port or settings.get("agent.llamacpp.port") or 8082)
    n_gpu_layers = int(payload.n_gpu_layers if payload.n_gpu_layers is not None else -1)
    model_dir = get_model_dir(settings)
    model_path = model_dir / filename

    publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="llamacpp.server.starting",
        message=f"Starting llama-cpp-python server with {filename}",
        data={"model": filename, "port": port},
    )

    try:
        result = start_llamacpp_server(
            model_path=model_path,
            port=port,
            n_gpu_layers=n_gpu_layers,
            wait_seconds=int(getattr(payload, "wait_seconds", 20)),
        )
    except LlamaCppError as exc:
        publish_event(
            user_id=user_id,
            run_id=run_id,
            event_type="llamacpp.server.start_failed",
            message="Failed to start llama-cpp-python server",
            data=exc.to_detail(),
        )
        _raise_from_llamacpp(exc)

    # Auto-register with ktem when server is reachable
    if result.get("reachable"):
        base_url = str(result.get("base_url") or build_base_url(port=port))
        model_type = _infer_model_type(filename)
        try:
            if model_type == "embedding":
                llm_name = upsert_llamacpp_embedding(model_filename=filename, base_url=base_url, default=True)
            else:
                llm_name = upsert_llamacpp_llm(model_filename=filename, base_url=base_url, default=True)
            result["llm_name"] = llm_name
        except Exception:
            pass

        # Persist active model to settings
        next_settings = deepcopy(settings)
        next_settings["agent.llamacpp.port"] = port
        key = "agent.llamacpp.active_embedding" if model_type == "embedding" else "agent.llamacpp.active_model"
        next_settings[key] = filename
        save_user_settings(context=get_context(), user_id=user_id, values=next_settings)

    publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="llamacpp.server.started",
        message="llama-cpp-python server started",
        data=result,
    )
    return result


@router.post("/integrations/llamacpp/stop")
def stop_llamacpp(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = tenant_settings(user_id)
    port = int(settings.get("agent.llamacpp.port") or 8082)
    try:
        return stop_llamacpp_server(port=port)
    except LlamaCppError as exc:
        _raise_from_llamacpp(exc)


@router.post("/integrations/llamacpp/select")
def select_llamacpp_model(
    payload: LlamaCppSelectRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = tenant_settings(user_id)
    run_id = str(payload.run_id or "").strip() or None
    filename = str(payload.model_filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="model_filename is required.")

    base_url = _resolve_base_url(settings)
    model_type = _infer_model_type(filename)

    try:
        if model_type == "embedding":
            name = upsert_llamacpp_embedding(model_filename=filename, base_url=base_url, default=True)
        else:
            name = upsert_llamacpp_llm(model_filename=filename, base_url=base_url, default=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Persist
    next_settings = deepcopy(settings)
    key = "agent.llamacpp.active_embedding" if model_type == "embedding" else "agent.llamacpp.active_model"
    next_settings[key] = filename
    save_user_settings(context=get_context(), user_id=user_id, values=next_settings)

    publish_event(
        user_id=user_id,
        run_id=run_id,
        event_type="llamacpp.model.selected",
        message=f"Active {'embedding' if model_type == 'embedding' else 'chat'} model: {filename}",
        data={"filename": filename, "llm_name": name, "type": model_type},
    )
    return {"status": "selected", "filename": filename, "llm_name": name, "type": model_type}


@router.post("/integrations/llamacpp/config")
def save_llamacpp_config(
    payload: LlamaCppConfigRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    _, settings = tenant_settings(user_id)
    next_settings = deepcopy(settings)
    next_settings["agent.llamacpp.port"] = int(payload.port or 8082)
    if str(payload.model_dir or "").strip():
        next_settings["agent.llamacpp.model_dir"] = str(payload.model_dir).strip()
    save_user_settings(context=get_context(), user_id=user_id, values=next_settings)
    return {"status": "saved", "port": next_settings["agent.llamacpp.port"]}


def _infer_model_type(filename: str) -> str:
    """Guess if a GGUF file is an embedding model by name."""
    lower = filename.lower()
    embedding_hints = ("embed", "embedding", "bge", "e5-", "minilm", "nomic")
    for hint in embedding_hints:
        if hint in lower:
            return "embedding"
    return "chat"
