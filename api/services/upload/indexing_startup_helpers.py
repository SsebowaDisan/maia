from __future__ import annotations

from typing import Any, Callable

from api.services.ollama.errors import OllamaError
from api.services.ollama.service import OllamaService


def is_paddle_runtime_expected_impl(
    *,
    reader_mode: str,
    paddleocr_enabled: bool,
    paddleocr_vl_api_enabled: bool,
) -> bool:
    mode = str(reader_mode or "default").strip() or "default"
    if mode == "paddleocr":
        return True
    return bool(paddleocr_enabled or paddleocr_vl_api_enabled)


def is_vlm_runtime_expected_impl(*, review_enabled: bool, extract_enabled: bool) -> bool:
    return bool(review_enabled or extract_enabled)


def run_vlm_startup_checks_impl(
    *,
    startup_check: bool,
    startup_strict: bool,
    review_enabled: bool,
    extract_enabled: bool,
    review_model: str,
    extract_model: str,
    base_url: str,
    logger_warning: Callable[[str], None],
) -> list[str]:
    notices: list[str] = []
    if not startup_check:
        return notices
    if not is_vlm_runtime_expected_impl(review_enabled=review_enabled, extract_enabled=extract_enabled):
        return notices

    strict = bool(startup_strict)
    service = OllamaService(base_url=base_url)
    required_models: set[str] = set()
    if review_enabled:
        model = str(review_model or "").strip()
        if model:
            required_models.add(model)
    if extract_enabled:
        model = str(extract_model or "").strip()
        if model:
            required_models.add(model)
    if not required_models:
        return notices

    try:
        models = service.list_models()
    except OllamaError as exc:
        message = (
            "VLM runtime check failed: Ollama is unreachable at "
            f"{base_url}. Details: {exc}"
        )
        if strict:
            raise RuntimeError(message) from exc
        logger_warning(message)
        notices.append(message)
        return notices
    except Exception as exc:
        message = f"VLM runtime check failed unexpectedly: {exc}"
        if strict:
            raise RuntimeError(message) from exc
        logger_warning(message)
        notices.append(message)
        return notices

    available_names = {
        str((row or {}).get("name") or "").strip()
        for row in models
        if isinstance(row, dict)
    }
    missing_models = [model for model in sorted(required_models) if model not in available_names]
    if missing_models:
        model_list = ", ".join(missing_models)
        message = (
            "VLM runtime check failed: required model(s) not available in Ollama: "
            f"{model_list}. Pull them with `ollama pull <model>`."
        )
        if strict:
            raise RuntimeError(message)
        logger_warning(message)
        notices.append(message)
    return notices


def run_paddle_startup_checks_impl(
    *,
    startup_check: bool,
    startup_strict: bool,
    startup_warmup: bool,
    reader_mode: str,
    is_paddle_runtime_expected: bool,
    paddleocr_vl_api_enabled: bool,
    paddleocr_vl_api_url: str,
    paddleocr_vl_api_token: str,
    paddleocr_vl_api_verify_ssl: bool,
    paddleocr_vl_api_ca_bundle: str,
    get_paddle_ocr_engine_fn: Callable[[], Any],
    logger_warning: Callable[[str], None],
) -> list[str]:
    notices: list[str] = []
    if not startup_check:
        return notices
    if not is_paddle_runtime_expected:
        return notices
    mode = str(reader_mode or "default").strip() or "default"
    strict = bool(startup_strict or mode == "paddleocr")

    remote_configured = bool(
        str(paddleocr_vl_api_url or "").strip() and str(paddleocr_vl_api_token or "").strip()
    )
    if bool(paddleocr_vl_api_enabled) and remote_configured:
        notices.append("PaddleOCR-VL API mode is enabled and configured.")
        if not bool(paddleocr_vl_api_verify_ssl):
            message = (
                "PaddleOCR-VL API SSL verification is disabled. "
                "Use this only when the remote OCR endpoint is behind a trusted internal certificate."
            )
            logger_warning(message)
            notices.append(message)
        elif str(paddleocr_vl_api_ca_bundle or "").strip():
            notices.append("PaddleOCR-VL API will use a custom CA bundle for TLS verification.")
        return notices
    if bool(paddleocr_vl_api_enabled) and not remote_configured:
        missing_remote: list[str] = []
        if not str(paddleocr_vl_api_url or "").strip():
            missing_remote.append("MAIA_UPLOAD_PADDLEOCR_VL_API_URL")
        if not str(paddleocr_vl_api_token or "").strip():
            missing_remote.append("MAIA_UPLOAD_PADDLEOCR_VL_API_TOKEN")
        if missing_remote:
            message = (
                "PaddleOCR-VL API mode is enabled but required settings are missing: "
                + ", ".join(missing_remote)
                + ". Falling back to local PaddleOCR runtime."
            )
            logger_warning(message)
            notices.append(message)

    missing: list[str] = []
    try:
        import fitz  # type: ignore[import-not-found]
        _ = fitz
    except Exception:
        missing.append("PyMuPDF (fitz)")

    try:
        from paddleocr import PaddleOCR  # type: ignore[import-not-found]
        _ = PaddleOCR
    except Exception:
        missing.append("paddleocr")

    if missing:
        message = (
            "PDF heavy-route dependencies missing: "
            + ", ".join(missing)
            + ". Heavy PDFs will fall back to the default parser."
        )
        if strict:
            raise RuntimeError(message)
        logger_warning(message)
        notices.append(message)
        return notices

    if startup_warmup:
        try:
            get_paddle_ocr_engine_fn()
        except Exception as exc:
            message = (
                "PaddleOCR runtime check failed during engine warmup. "
                f"Details: {exc}"
            )
            if strict:
                raise RuntimeError(message) from exc
            logger_warning(message)
            notices.append(message)
            return notices

    notices.append("PaddleOCR runtime dependencies are available.")
    return notices
