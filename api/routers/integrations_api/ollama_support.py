from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from api.services.ollama import OllamaError, OllamaService

from .common import raise_http_from_ollama


def normalize_required_model(
    raw_model: Any,
    *,
    missing_code: str,
    missing_message: str,
) -> str:
    model = " ".join(str(raw_model or "").split()).strip()
    if model:
        return model
    raise HTTPException(
        status_code=400,
        detail={"code": missing_code, "message": missing_message},
    )


def list_service_models(base_url: str) -> list[dict[str, Any]]:
    service = OllamaService(base_url=base_url)
    try:
        return service.list_models()
    except OllamaError as exc:
        raise_http_from_ollama(exc)


def ensure_model_exists(
    *,
    model: str,
    models: list[dict[str, Any]],
    not_found_code: str,
    base_url: str,
    resource_label: str = "Model",
) -> None:
    model_names = {str(item.get("name") or "") for item in models}
    if model in model_names:
        return
    raise HTTPException(
        status_code=404,
        detail={
            "code": not_found_code,
            "message": f"{resource_label} `{model}` is not downloaded locally.",
            "details": {"base_url": base_url},
        },
    )
