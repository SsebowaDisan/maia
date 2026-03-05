from __future__ import annotations

import base64
from copy import deepcopy
from functools import lru_cache
import json
import logging
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Callable
import uuid

from decouple import config
from fastapi import HTTPException
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ktem.db.engine import engine

from api.context import ApiContext
from api.services.ollama.errors import OllamaError
from api.services.ollama.service import DEFAULT_OLLAMA_BASE_URL, OllamaService, normalize_ollama_base_url

from .common import get_index, normalize_ids, normalize_upload_scope

_raw_upload_reader_mode = str(
    config("MAIA_UPLOAD_INDEX_READER_MODE", default="default")
).strip()
UPLOAD_INDEX_READER_MODE = (
    _raw_upload_reader_mode
    if _raw_upload_reader_mode
    in {"default", "ocr", "adobe", "azure-di", "docling", "paddleocr"}
    else "default"
)
UPLOAD_INDEX_QUICK_MODE = bool(
    config("MAIA_UPLOAD_INDEX_QUICK_MODE", default=True, cast=bool)
)
OCR_PREFERRED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".gif",
    ".webp",
}
UPLOAD_PDF_OCR_POLICY = str(
    config("MAIA_UPLOAD_PDF_OCR_POLICY", default="auto")
).strip().lower()
if UPLOAD_PDF_OCR_POLICY not in {"auto", "always", "never"}:
    UPLOAD_PDF_OCR_POLICY = "auto"
UPLOAD_PDF_OCR_SCAN_PAGES = max(
    1, int(config("MAIA_UPLOAD_PDF_OCR_SCAN_PAGES", default=24, cast=int))
)
UPLOAD_PDF_OCR_MIN_TEXT_CHARS_PER_PAGE = max(
    0, int(config("MAIA_UPLOAD_PDF_OCR_MIN_TEXT_CHARS_PER_PAGE", default=40, cast=int))
)
UPLOAD_PDF_OCR_VERY_LOW_TEXT_CHARS_PER_PAGE = max(
    0, int(config("MAIA_UPLOAD_PDF_OCR_VERY_LOW_TEXT_CHARS_PER_PAGE", default=12, cast=int))
)
UPLOAD_PDF_OCR_MIN_LOW_TEXT_PAGE_RATIO = min(
    1.0,
    max(
        0.0,
        float(config("MAIA_UPLOAD_PDF_OCR_MIN_LOW_TEXT_PAGE_RATIO", default=0.25, cast=float)),
    ),
)
UPLOAD_PDF_OCR_MIN_IMAGE_PAGE_RATIO = min(
    1.0,
    max(
        0.0,
        float(config("MAIA_UPLOAD_PDF_OCR_MIN_IMAGE_PAGE_RATIO", default=0.10, cast=float)),
    ),
)
UPLOAD_PDF_OCR_TRIGGER_ON_ANY_IMAGE_LOW_TEXT_PAGE = bool(
    config("MAIA_UPLOAD_PDF_OCR_TRIGGER_ON_ANY_IMAGE_LOW_TEXT_PAGE", default=True, cast=bool)
)
UPLOAD_PDF_OCR_TRIGGER_ON_ANY_VERY_LOW_TEXT_PAGE = bool(
    config("MAIA_UPLOAD_PDF_OCR_TRIGGER_ON_ANY_VERY_LOW_TEXT_PAGE", default=True, cast=bool)
)
UPLOAD_PDF_OCR_MIN_IMAGE_PAGES_FULL_SCAN = max(
    1, int(config("MAIA_UPLOAD_PDF_OCR_MIN_IMAGE_PAGES_FULL_SCAN", default=2, cast=int))
)
UPLOAD_PDF_OCR_TRIGGER_ON_ANY_IMAGE_PAGE_FULL_SCAN = bool(
    config("MAIA_UPLOAD_PDF_OCR_TRIGGER_ON_ANY_IMAGE_PAGE_FULL_SCAN", default=True, cast=bool)
)
UPLOAD_PDF_OCR_SKIP_EDGE_PAGES = max(
    0, int(config("MAIA_UPLOAD_PDF_OCR_SKIP_EDGE_PAGES", default=1, cast=int))
)
UPLOAD_PDF_OCR_MIN_IMAGE_PAGE_RATIO_FULL_SCAN = min(
    1.0,
    max(
        0.0,
        float(
            config(
                "MAIA_UPLOAD_PDF_OCR_MIN_IMAGE_PAGE_RATIO_FULL_SCAN",
                default=0.03,
                cast=float,
            )
        ),
    ),
)
UPLOAD_PDF_HEAVY_MIN_IMAGE_PAGE_RATIO = min(
    1.0,
    max(
        0.0,
        float(config("MAIA_UPLOAD_PDF_HEAVY_MIN_IMAGE_PAGE_RATIO", default=0.03, cast=float)),
    ),
)
UPLOAD_PDF_HEAVY_MIN_LOW_TEXT_PAGE_RATIO = min(
    1.0,
    max(
        0.0,
        float(config("MAIA_UPLOAD_PDF_HEAVY_MIN_LOW_TEXT_PAGE_RATIO", default=0.30, cast=float)),
    ),
)
UPLOAD_PDF_HEAVY_ON_ANY_IMAGE_PAGE = bool(
    config("MAIA_UPLOAD_PDF_HEAVY_ON_ANY_IMAGE_PAGE", default=True, cast=bool)
)
UPLOAD_PADDLEOCR_ENABLED = bool(
    config("MAIA_UPLOAD_PADDLEOCR_ENABLED", default=True, cast=bool)
)
UPLOAD_PADDLEOCR_LANG = str(config("MAIA_UPLOAD_PADDLEOCR_LANG", default="en")).strip() or "en"
UPLOAD_PADDLEOCR_USE_GPU = bool(
    config("MAIA_UPLOAD_PADDLEOCR_USE_GPU", default=False, cast=bool)
)
UPLOAD_PADDLEOCR_RENDER_DPI = max(
    96, int(config("MAIA_UPLOAD_PADDLEOCR_RENDER_DPI", default=220, cast=int))
)
UPLOAD_PADDLEOCR_MAX_PAGES = max(
    0, int(config("MAIA_UPLOAD_PADDLEOCR_MAX_PAGES", default=0, cast=int))
)

_PADDLE_OCR_ENGINE: Any | None = None
_PADDLE_OCR_LOCK = threading.Lock()
UPLOAD_PADDLEOCR_STARTUP_CHECK = bool(
    config("MAIA_UPLOAD_PADDLEOCR_STARTUP_CHECK", default=True, cast=bool)
)
UPLOAD_PADDLEOCR_STARTUP_STRICT = bool(
    config("MAIA_UPLOAD_PADDLEOCR_STARTUP_STRICT", default=False, cast=bool)
)
UPLOAD_PADDLEOCR_STARTUP_WARMUP = bool(
    config("MAIA_UPLOAD_PADDLEOCR_STARTUP_WARMUP", default=False, cast=bool)
)
UPLOAD_PDF_VLM_BASE_URL = normalize_ollama_base_url(
    str(
        config(
            "MAIA_UPLOAD_PDF_VLM_BASE_URL",
            default=config("OLLAMA_BASE_URL", default=DEFAULT_OLLAMA_BASE_URL),
        )
    ).strip()
    or DEFAULT_OLLAMA_BASE_URL
)
UPLOAD_PDF_VLM_REVIEW_ENABLED = bool(
    config("MAIA_UPLOAD_PDF_VLM_REVIEW_ENABLED", default=False, cast=bool)
)
UPLOAD_PDF_VLM_REVIEW_MODEL = (
    str(config("MAIA_UPLOAD_PDF_VLM_REVIEW_MODEL", default="qwen2.5vl:7b")).strip()
    or "qwen2.5vl:7b"
)
UPLOAD_PDF_VLM_REVIEW_TIMEOUT_SECONDS = max(
    1.0,
    float(config("MAIA_UPLOAD_PDF_VLM_REVIEW_TIMEOUT_SECONDS", default=20.0, cast=float)),
)
UPLOAD_PDF_VLM_REVIEW_RENDER_DPI = max(
    96, int(config("MAIA_UPLOAD_PDF_VLM_REVIEW_RENDER_DPI", default=180, cast=int))
)
UPLOAD_PDF_VLM_REVIEW_MAX_PAGES = max(
    0, int(config("MAIA_UPLOAD_PDF_VLM_REVIEW_MAX_PAGES", default=0, cast=int))
)
UPLOAD_PDF_VLM_EXTRACT_ENABLED = bool(
    config("MAIA_UPLOAD_PDF_VLM_EXTRACT_ENABLED", default=False, cast=bool)
)
UPLOAD_PDF_VLM_EXTRACT_MODEL = (
    str(config("MAIA_UPLOAD_PDF_VLM_EXTRACT_MODEL", default="qwen2.5vl:7b")).strip()
    or "qwen2.5vl:7b"
)
UPLOAD_PDF_VLM_EXTRACT_TIMEOUT_SECONDS = max(
    1.0,
    float(config("MAIA_UPLOAD_PDF_VLM_EXTRACT_TIMEOUT_SECONDS", default=45.0, cast=float)),
)
UPLOAD_PDF_VLM_EXTRACT_RENDER_DPI = max(
    96, int(config("MAIA_UPLOAD_PDF_VLM_EXTRACT_RENDER_DPI", default=220, cast=int))
)
UPLOAD_PDF_VLM_EXTRACT_MAX_PAGES = max(
    0, int(config("MAIA_UPLOAD_PDF_VLM_EXTRACT_MAX_PAGES", default=0, cast=int))
)
UPLOAD_PDF_VLM_STARTUP_CHECK = bool(
    config("MAIA_UPLOAD_PDF_VLM_STARTUP_CHECK", default=True, cast=bool)
)
UPLOAD_PDF_VLM_STARTUP_STRICT = bool(
    config("MAIA_UPLOAD_PDF_VLM_STARTUP_STRICT", default=False, cast=bool)
)

logger = logging.getLogger(__name__)


def _is_paddle_runtime_expected() -> bool:
    mode = str(UPLOAD_INDEX_READER_MODE or "default").strip() or "default"
    if mode == "paddleocr":
        return True
    return bool(UPLOAD_PADDLEOCR_ENABLED)


def _is_vlm_runtime_expected() -> bool:
    return bool(UPLOAD_PDF_VLM_REVIEW_ENABLED or UPLOAD_PDF_VLM_EXTRACT_ENABLED)


def _run_vlm_startup_checks() -> list[str]:
    notices: list[str] = []
    if not UPLOAD_PDF_VLM_STARTUP_CHECK:
        return notices
    if not _is_vlm_runtime_expected():
        return notices

    strict = bool(UPLOAD_PDF_VLM_STARTUP_STRICT)
    service = OllamaService(base_url=UPLOAD_PDF_VLM_BASE_URL)
    required_models: set[str] = set()
    if UPLOAD_PDF_VLM_REVIEW_ENABLED:
        review_model = str(UPLOAD_PDF_VLM_REVIEW_MODEL or "").strip()
        if review_model:
            required_models.add(review_model)
    if UPLOAD_PDF_VLM_EXTRACT_ENABLED:
        extract_model = str(UPLOAD_PDF_VLM_EXTRACT_MODEL or "").strip()
        if extract_model:
            required_models.add(extract_model)
    if not required_models:
        return notices

    try:
        models = service.list_models()
    except OllamaError as exc:
        message = (
            "VLM runtime check failed: Ollama is unreachable at "
            f"{UPLOAD_PDF_VLM_BASE_URL}. Details: {exc}"
        )
        if strict:
            raise RuntimeError(message) from exc
        logger.warning(message)
        notices.append(message)
        return notices
    except Exception as exc:
        message = f"VLM runtime check failed unexpectedly: {exc}"
        if strict:
            raise RuntimeError(message) from exc
        logger.warning(message)
        notices.append(message)
        return notices

    available_names = {
        str((row or {}).get("name") or "").strip()
        for row in models
        if isinstance(row, dict)
    }
    missing_models = [model for model in sorted(required_models) if model not in available_names]
    if missing_models:
        message = (
            "VLM runtime check: required model(s) not available in Ollama: "
            + ", ".join(missing_models)
            + ". Pull them with `ollama pull <model>`."
        )
        if strict:
            raise RuntimeError(message)
        logger.warning(message)
        notices.append(message)
        return notices

    notices.append(
        "VLM runtime dependencies are available "
        f"({', '.join(sorted(required_models))} @ {UPLOAD_PDF_VLM_BASE_URL})."
    )
    return notices


def run_upload_startup_checks() -> list[str]:
    notices: list[str] = []
    if UPLOAD_PADDLEOCR_STARTUP_CHECK and _is_paddle_runtime_expected():
        notices.extend(_run_paddle_startup_checks())
    notices.extend(_run_vlm_startup_checks())
    return notices


def _run_paddle_startup_checks() -> list[str]:
    notices: list[str] = []
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

    mode = str(UPLOAD_INDEX_READER_MODE or "default").strip() or "default"
    strict = bool(UPLOAD_PADDLEOCR_STARTUP_STRICT or mode == "paddleocr")
    if missing:
        message = (
            "PDF heavy-route dependencies missing: "
            + ", ".join(missing)
            + ". Heavy PDFs will fall back to the default parser."
        )
        if strict:
            raise RuntimeError(message)
        logger.warning(message)
        notices.append(message)
        return notices

    if UPLOAD_PADDLEOCR_STARTUP_WARMUP:
        try:
            _get_paddle_ocr_engine()
            notices.append("PaddleOCR startup warmup completed.")
        except Exception as exc:
            message = f"PaddleOCR startup warmup failed: {exc}"
            if strict:
                raise RuntimeError(message) from exc
            logger.warning(message)
            notices.append(message)
            return notices

    notices.append("PaddleOCR runtime dependencies are available.")
    return notices


def _page_has_images(page: Any) -> bool:
    images = getattr(page, "images", None)
    if images is not None:
        try:
            if len(images) > 0:
                return True
        except Exception:
            pass
    try:
        resources = page.get("/Resources")
        if not resources:
            return False
        xobjects = resources.get("/XObject")
        if not xobjects:
            return False
        objects = xobjects.get_object()
        for obj in objects.values():
            try:
                target = obj.get_object()
                if str(target.get("/Subtype", "")) == "/Image":
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def _sample_page_indexes(total_pages: int, sample_size: int) -> list[int]:
    total = max(0, int(total_pages or 0))
    if total <= 0:
        return []
    size = max(1, min(total, int(sample_size or 1)))
    if size >= total:
        return list(range(total))
    last = total - 1
    return sorted({(last * i) // max(1, size - 1) for i in range(size)})


def _count_image_pages(
    pages: list[Any],
    page_indexes: list[int] | None = None,
    skip_edge_pages: int = 0,
) -> int:
    total_pages = len(pages)
    if total_pages <= 0:
        return 0
    skip = max(0, int(skip_edge_pages or 0))
    first_allowed = skip
    last_allowed = total_pages - skip - 1
    if first_allowed > last_allowed:
        first_allowed = 0
        last_allowed = total_pages - 1
    if page_indexes is None:
        iter_indexes = range(first_allowed, last_allowed + 1)
    else:
        iter_indexes = [
            idx
            for idx in page_indexes
            if isinstance(idx, int) and first_allowed <= idx <= last_allowed
        ]
    count = 0
    for page_index in iter_indexes:
        if _page_has_images(pages[page_index]):
            count += 1
    return count


def _normalize_page_indexes(
    *,
    total_pages: int,
    page_indexes: list[int] | None,
    skip_edge_pages: int,
) -> list[int]:
    total = max(0, int(total_pages or 0))
    if total <= 0:
        return []
    skip = max(0, int(skip_edge_pages or 0))
    first_allowed = skip
    last_allowed = total - skip - 1
    if first_allowed > last_allowed:
        first_allowed = 0
        last_allowed = total - 1
    if page_indexes is None:
        return list(range(first_allowed, last_allowed + 1))
    return sorted(
        {
            idx
            for idx in page_indexes
            if isinstance(idx, int) and first_allowed <= idx <= last_allowed
        }
    )


def _detect_pdf_images_with_pymupdf(
    path: Path,
    *,
    page_indexes: list[int] | None = None,
    skip_edge_pages: int = 0,
) -> tuple[set[int], int]:
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception:
        return set(), 0

    image_pages: set[int] = set()
    total_pages = 0
    doc = None
    try:
        doc = fitz.open(str(path))
        total_pages = int(getattr(doc, "page_count", 0) or 0)
        indexes = _normalize_page_indexes(
            total_pages=total_pages,
            page_indexes=page_indexes,
            skip_edge_pages=skip_edge_pages,
        )
        for page_index in indexes:
            page = doc.load_page(page_index)
            has_image = False
            try:
                has_image = bool(page.get_images(full=True))
            except Exception:
                has_image = False
            if not has_image:
                try:
                    blocks = page.get_text("dict").get("blocks", [])
                    has_image = any(
                        isinstance(block, dict) and int(block.get("type", -1)) == 1
                        for block in blocks
                    )
                except Exception:
                    has_image = False
            if has_image:
                image_pages.add(page_index)
    except Exception:
        return set(), 0
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
    return image_pages, total_pages


def _ollama_timeout(timeout_seconds: float) -> httpx.Timeout:
    timeout_value = max(1.0, float(timeout_seconds))
    return httpx.Timeout(timeout=timeout_value, connect=min(10.0, timeout_value))


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    candidates = [raw]
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


def _parse_vlm_classifier_response(text: str) -> dict[str, Any]:
    payload = _extract_json_object(text)
    if isinstance(payload, dict):
        for key in ("needs_ocr", "heavy", "route_to_heavy"):
            if key in payload:
                value = payload.get(key)
                if isinstance(value, bool):
                    return {
                        "needs_ocr": bool(value),
                        "reason": str(payload.get("reason") or "").strip(),
                    }
                if isinstance(value, (int, float)):
                    return {
                        "needs_ocr": bool(value),
                        "reason": str(payload.get("reason") or "").strip(),
                    }
                text_value = str(value or "").strip().lower()
                if text_value in {"true", "yes", "1", "y"}:
                    return {
                        "needs_ocr": True,
                        "reason": str(payload.get("reason") or "").strip(),
                    }
                if text_value in {"false", "no", "0", "n"}:
                    return {
                        "needs_ocr": False,
                        "reason": str(payload.get("reason") or "").strip(),
                    }

    normalized = str(text or "").strip().lower()
    if "needs_ocr" in normalized and "true" in normalized:
        return {"needs_ocr": True, "reason": "vlm-fallback-text"}
    if '"route":"heavy"' in normalized or "route: heavy" in normalized:
        return {"needs_ocr": True, "reason": "vlm-fallback-text"}
    if '"route":"normal"' in normalized or "route: normal" in normalized:
        return {"needs_ocr": False, "reason": "vlm-fallback-text"}
    return {"needs_ocr": False, "reason": "vlm-unparseable"}


def _dedupe_text_lines(lines: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        normalized = " ".join(str(line or "").split()).strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _extract_text_lines_from_vlm_response(text: str) -> list[str]:
    content = str(text or "").strip()
    if not content:
        return []
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        content = content.strip()

    payload = _extract_json_object(content)
    if isinstance(payload, dict):
        for key in ("text", "content", "output", "transcript"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                content = value.strip()
                break
        else:
            lines_payload = payload.get("lines")
            if isinstance(lines_payload, list):
                return _dedupe_text_lines([str(item) for item in lines_payload if item])

    return _dedupe_text_lines(content.splitlines())


def _merge_text_lines(primary: list[str], extra: list[str]) -> list[str]:
    return _dedupe_text_lines([*list(primary or []), *list(extra or [])])


def _run_ollama_vlm_for_image(
    *,
    client: httpx.Client,
    model: str,
    prompt: str,
    image_path: Path,
) -> str:
    image_bytes = image_path.read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": str(model or "").strip(),
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }
        ],
    }
    url = f"{UPLOAD_PDF_VLM_BASE_URL}/api/chat"
    response = client.post(url, json=payload)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise RuntimeError("Ollama returned an invalid response payload.")
    message = body.get("message")
    if isinstance(message, dict):
        content = str(message.get("content") or "").strip()
        if content:
            return content
    fallback = str(body.get("response") or "").strip()
    if fallback:
        return fallback
    raise RuntimeError("Ollama returned an empty VLM response.")


def _review_pdf_route_with_vlm(
    path: Path,
    *,
    total_pages_hint: int,
    sampled_indexes: list[int] | None = None,
) -> dict[str, Any]:
    if not UPLOAD_PDF_VLM_REVIEW_ENABLED:
        return {"enabled": False, "upgrade": False, "checked_pages": 0}
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception as exc:
        return {
            "enabled": True,
            "upgrade": False,
            "checked_pages": 0,
            "error": f"fitz-unavailable: {exc}",
        }

    doc = None
    image_paths: list[Path] = []
    work_dir = Path(tempfile.mkdtemp(prefix="vlm-review-", dir=str(path.parent)))
    checked_pages = 0
    try:
        doc = fitz.open(str(path))
        total_pages = max(int(getattr(doc, "page_count", 0) or 0), int(total_pages_hint or 0))
        page_indexes = _normalize_page_indexes(
            total_pages=total_pages,
            page_indexes=sampled_indexes,
            skip_edge_pages=0,
        )
        if not page_indexes:
            page_indexes = list(range(total_pages))
        if UPLOAD_PDF_VLM_REVIEW_MAX_PAGES > 0 and len(page_indexes) > UPLOAD_PDF_VLM_REVIEW_MAX_PAGES:
            sampled_positions = _sample_page_indexes(len(page_indexes), UPLOAD_PDF_VLM_REVIEW_MAX_PAGES)
            page_indexes = [page_indexes[pos] for pos in sampled_positions if 0 <= pos < len(page_indexes)]

        prompt = (
            "You are classifying a PDF page for ingestion routing. "
            "Return JSON only with keys needs_ocr (boolean) and reason (short string). "
            "needs_ocr must be true when this page contains scanned text, text embedded in images, "
            "equations/charts/diagrams where plain PDF text extraction may miss important content."
        )
        with httpx.Client(timeout=_ollama_timeout(UPLOAD_PDF_VLM_REVIEW_TIMEOUT_SECONDS)) as client:
            for page_index in page_indexes:
                page = doc.load_page(page_index)
                image_path = work_dir / f"review-page-{page_index + 1}.png"
                image_paths.append(image_path)
                pix = page.get_pixmap(dpi=UPLOAD_PDF_VLM_REVIEW_RENDER_DPI, alpha=False)
                pix.save(str(image_path))
                raw = _run_ollama_vlm_for_image(
                    client=client,
                    model=UPLOAD_PDF_VLM_REVIEW_MODEL,
                    prompt=prompt,
                    image_path=image_path,
                )
                verdict = _parse_vlm_classifier_response(raw)
                checked_pages += 1
                if bool(verdict.get("needs_ocr")):
                    return {
                        "enabled": True,
                        "upgrade": True,
                        "checked_pages": checked_pages,
                        "reason": str(verdict.get("reason") or "vlm-review-upgrade"),
                    }
        return {
            "enabled": True,
            "upgrade": False,
            "checked_pages": checked_pages,
            "reason": "vlm-review-kept-normal",
        }
    except Exception as exc:
        return {
            "enabled": True,
            "upgrade": False,
            "checked_pages": checked_pages,
            "error": str(exc),
        }
    finally:
        for image_path in image_paths:
            try:
                image_path.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            work_dir.rmdir()
        except Exception:
            pass
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass


def _apply_vlm_review_upgrade(
    path: Path,
    classification: dict[str, Any],
    *,
    sampled_indexes: list[int] | None = None,
) -> dict[str, Any]:
    result = dict(classification or {})
    if not UPLOAD_PDF_VLM_REVIEW_ENABLED:
        return result
    if str(result.get("route") or "normal") != "normal":
        result["vlm_review"] = "skipped-non-normal"
        return result

    review = _review_pdf_route_with_vlm(
        path,
        total_pages_hint=int(result.get("total_pages", 0) or 0),
        sampled_indexes=sampled_indexes,
    )
    checked_pages = int(review.get("checked_pages", 0) or 0)
    if checked_pages > 0:
        result["vlm_review_checked_pages"] = checked_pages
    if review.get("error"):
        result["vlm_review_error"] = str(review.get("error"))
        return result
    if bool(review.get("upgrade")):
        result["route"] = "heavy"
        result["use_ocr"] = True
        reason = str(review.get("reason") or "vlm-review-upgrade").strip()
        result["reason"] = reason or "vlm-review-upgrade"
        result["vlm_review"] = "upgraded-to-heavy"
        return result
    result["vlm_review"] = "kept-normal"
    return result


@lru_cache(maxsize=256)
def _classify_pdf_ingestion_route_cached(
    resolved_path: str,
    modified_ns: int,
    file_size: int,
) -> dict[str, Any]:
    _ = modified_ns
    _ = file_size
    path = Path(resolved_path)
    if UPLOAD_PDF_OCR_POLICY == "always":
        return {
            "route": "heavy",
            "use_ocr": True,
            "reason": "ocr-policy-always",
            "total_pages": 0,
            "image_pages_all": 0,
            "image_ratio_all": 0.0,
            "low_text_ratio_sampled": 0.0,
        }
    if UPLOAD_PDF_OCR_POLICY == "never":
        return {
            "route": "normal",
            "use_ocr": False,
            "reason": "ocr-policy-never",
            "total_pages": 0,
            "image_pages_all": 0,
            "image_ratio_all": 0.0,
            "low_text_ratio_sampled": 0.0,
        }

    try:
        from pypdf import PdfReader
    except Exception:
        return {
            "route": "normal",
            "use_ocr": False,
            "reason": "pypdf-unavailable",
            "total_pages": 0,
            "image_pages_all": 0,
            "image_ratio_all": 0.0,
            "low_text_ratio_sampled": 0.0,
        }

    try:
        reader = PdfReader(str(path))
        pages = list(getattr(reader, "pages", []))
    except Exception:
        # If PDF probing fails, classify as heavy to use OCR-safe path.
        return {
            "route": "heavy",
            "use_ocr": True,
            "reason": "pdf-probe-failed",
            "total_pages": 0,
            "image_pages_all": 0,
            "image_ratio_all": 0.0,
            "low_text_ratio_sampled": 1.0,
        }

    total_pages = len(pages)
    if total_pages <= 0:
        return {
            "route": "heavy",
            "use_ocr": True,
            "reason": "empty-pdf-pages",
            "total_pages": 0,
            "image_pages_all": 0,
            "image_ratio_all": 0.0,
            "low_text_ratio_sampled": 1.0,
        }

    sampled_indexes = _sample_page_indexes(total_pages, UPLOAD_PDF_OCR_SCAN_PAGES)
    sampled_pages = 0
    sample_image_pages = 0
    low_text_pages = 0
    very_low_text_detected = False
    image_and_low_text_detected = False

    for page_index in sampled_indexes:
        page = pages[page_index]
        sampled_pages += 1
        has_images = _page_has_images(page)
        if has_images:
            sample_image_pages += 1
        extracted = ""
        try:
            extracted = str(page.extract_text() or "")
        except Exception:
            extracted = ""
        compact_len = len("".join(extracted.split()))
        if compact_len < UPLOAD_PDF_OCR_MIN_TEXT_CHARS_PER_PAGE:
            low_text_pages += 1
        if compact_len < UPLOAD_PDF_OCR_VERY_LOW_TEXT_CHARS_PER_PAGE:
            very_low_text_detected = True
        if has_images and compact_len < UPLOAD_PDF_OCR_MIN_TEXT_CHARS_PER_PAGE:
            image_and_low_text_detected = True

    sampled_pages = max(1, sampled_pages)
    low_text_ratio = low_text_pages / float(sampled_pages)
    sample_image_ratio = sample_image_pages / float(sampled_pages)
    image_pages_all = _count_image_pages(
        pages,
        skip_edge_pages=UPLOAD_PDF_OCR_SKIP_EDGE_PAGES,
    )
    image_pages_pymupdf, pymupdf_total_pages = _detect_pdf_images_with_pymupdf(
        path,
        skip_edge_pages=UPLOAD_PDF_OCR_SKIP_EDGE_PAGES,
    )
    # High-recall image detection: union pypdf and PyMuPDF scans.
    image_pages_all = max(image_pages_all, len(image_pages_pymupdf))
    effective_total_pages = max(total_pages, pymupdf_total_pages or 0)
    image_ratio_all = image_pages_all / float(max(1, effective_total_pages))

    force_heavy_any_image = (
        UPLOAD_PDF_HEAVY_ON_ANY_IMAGE_PAGE and UPLOAD_PDF_OCR_TRIGGER_ON_ANY_IMAGE_PAGE_FULL_SCAN
    )
    should_use_ocr = (
        (UPLOAD_PDF_OCR_TRIGGER_ON_ANY_VERY_LOW_TEXT_PAGE and very_low_text_detected)
        or (
            UPLOAD_PDF_OCR_TRIGGER_ON_ANY_IMAGE_LOW_TEXT_PAGE
            and image_and_low_text_detected
        )
        or (
            UPLOAD_PDF_OCR_TRIGGER_ON_ANY_IMAGE_PAGE_FULL_SCAN
            and image_pages_all > 0
        )
        or (low_text_ratio >= UPLOAD_PDF_OCR_MIN_LOW_TEXT_PAGE_RATIO)
        or (sample_image_ratio >= UPLOAD_PDF_OCR_MIN_IMAGE_PAGE_RATIO)
        or (
            image_pages_all >= UPLOAD_PDF_OCR_MIN_IMAGE_PAGES_FULL_SCAN
            and image_ratio_all >= UPLOAD_PDF_OCR_MIN_IMAGE_PAGE_RATIO_FULL_SCAN
        )
    )
    heavy = bool(should_use_ocr) and (
        force_heavy_any_image
        or image_ratio_all >= UPLOAD_PDF_HEAVY_MIN_IMAGE_PAGE_RATIO
        or low_text_ratio >= UPLOAD_PDF_HEAVY_MIN_LOW_TEXT_PAGE_RATIO
    )

    reason = "normal"
    if force_heavy_any_image and image_pages_all > 0:
        reason = "heavy-any-image-page"
    elif low_text_ratio >= UPLOAD_PDF_HEAVY_MIN_LOW_TEXT_PAGE_RATIO and should_use_ocr:
        reason = "heavy-low-text-ratio"
    elif image_ratio_all >= UPLOAD_PDF_HEAVY_MIN_IMAGE_PAGE_RATIO and should_use_ocr:
        reason = "heavy-image-ratio"
    elif should_use_ocr:
        reason = "ocr-required"

    classification = {
        "route": "heavy" if heavy else "normal",
        "use_ocr": bool(should_use_ocr),
        "reason": reason,
        "total_pages": int(effective_total_pages),
        "image_pages_all": int(image_pages_all),
        "image_ratio_all": float(image_ratio_all),
        "low_text_ratio_sampled": float(low_text_ratio),
        "sampled_pages": int(sampled_pages),
    }
    return _apply_vlm_review_upgrade(
        path,
        classification,
        sampled_indexes=sampled_indexes,
    )


def _classify_pdf_ingestion_route(path: Path) -> dict[str, Any]:
    try:
        resolved = str(path.resolve())
    except Exception:
        resolved = str(path)
    modified_ns = 0
    file_size = 0
    try:
        stat = path.stat()
        modified_ns = int(getattr(stat, "st_mtime_ns", 0) or 0)
        file_size = int(getattr(stat, "st_size", 0) or 0)
    except Exception:
        modified_ns = 0
        file_size = 0
    return _classify_pdf_ingestion_route_cached(resolved, modified_ns, file_size)


def _pdf_should_use_ocr(path: Path) -> bool:
    classification = _classify_pdf_ingestion_route(path)
    return bool(classification.get("use_ocr"))


def _get_paddle_ocr_engine() -> Any:
    global _PADDLE_OCR_ENGINE
    with _PADDLE_OCR_LOCK:
        if _PADDLE_OCR_ENGINE is not None:
            return _PADDLE_OCR_ENGINE
        try:
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError("PaddleOCR package is not installed.") from exc

        kwargs: dict[str, Any] = {
            "use_angle_cls": True,
            "lang": UPLOAD_PADDLEOCR_LANG,
            "show_log": False,
        }
        if UPLOAD_PADDLEOCR_USE_GPU:
            kwargs["use_gpu"] = True
        else:
            kwargs["use_gpu"] = False
        try:
            _PADDLE_OCR_ENGINE = PaddleOCR(**kwargs)
        except TypeError:
            kwargs.pop("show_log", None)
            _PADDLE_OCR_ENGINE = PaddleOCR(**kwargs)
        return _PADDLE_OCR_ENGINE


def _extract_text_lines_from_paddle_result(raw_result: Any) -> list[str]:
    lines: list[str] = []

    def _visit(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                _visit(value)
            return
        if isinstance(node, (list, tuple)):
            # Common PaddleOCR line shape: [bbox, [text, score]]
            if len(node) >= 2 and isinstance(node[1], (list, tuple)):
                candidate = node[1]
                if candidate:
                    text_value = " ".join(str(candidate[0] or "").split()).strip()
                    if text_value:
                        lines.append(text_value)
                        return
            for value in node:
                _visit(value)
            return

    _visit(raw_result)
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        normalized = line.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def _extract_text_lines_from_vlm_page(
    *,
    client: httpx.Client,
    image_path: Path,
    page_number: int,
) -> list[str]:
    prompt = (
        "Extract all meaningful visible text from this page image, including text in diagrams, "
        "tables, formulas, and chart labels. Return plain text only with one logical line per line. "
        f"Page number: {page_number}."
    )
    raw = _run_ollama_vlm_for_image(
        client=client,
        model=UPLOAD_PDF_VLM_EXTRACT_MODEL,
        prompt=prompt,
        image_path=image_path,
    )
    return _extract_text_lines_from_vlm_response(raw)


def _extract_pdf_text_with_paddleocr(
    file_path: Path,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[Path, list[str]]:
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError("PyMuPDF (fitz) is required for PaddleOCR PDF routing.") from exc

    ocr_engine = _get_paddle_ocr_engine()
    work_dir = Path(tempfile.mkdtemp(prefix="paddleocr-", dir=str(file_path.parent)))
    text_path = work_dir / f"{file_path.stem}-{uuid.uuid4().hex[:8]}.txt"
    debug_rows: list[str] = []
    doc = None
    image_paths: list[Path] = []
    vlm_client: httpx.Client | None = None
    vlm_pages_processed = 0
    vlm_pages_failed = 0
    try:
        doc = fitz.open(str(file_path))
        total_pages = int(getattr(doc, "page_count", 0) or 0)
        max_pages = (
            total_pages
            if UPLOAD_PADDLEOCR_MAX_PAGES <= 0
            else min(total_pages, int(UPLOAD_PADDLEOCR_MAX_PAGES))
        )
        vlm_extract_page_limit = (
            max_pages
            if UPLOAD_PDF_VLM_EXTRACT_MAX_PAGES <= 0
            else min(max_pages, int(UPLOAD_PDF_VLM_EXTRACT_MAX_PAGES))
        )
        use_vlm_extract = bool(UPLOAD_PDF_VLM_EXTRACT_ENABLED and vlm_extract_page_limit > 0)
        render_dpi = int(UPLOAD_PADDLEOCR_RENDER_DPI)
        if use_vlm_extract:
            render_dpi = max(render_dpi, int(UPLOAD_PDF_VLM_EXTRACT_RENDER_DPI))
        if use_vlm_extract:
            vlm_client = httpx.Client(timeout=_ollama_timeout(UPLOAD_PDF_VLM_EXTRACT_TIMEOUT_SECONDS))
        page_blocks: list[str] = []
        for page_index in range(max_pages):
            if should_cancel and should_cancel():
                raise IndexingCanceledError("Ingestion canceled by user.")
            page = doc.load_page(page_index)
            image_path = work_dir / f"page-{page_index + 1}.png"
            image_paths.append(image_path)
            pix = page.get_pixmap(dpi=render_dpi, alpha=False)
            pix.save(str(image_path))
            raw_result = ocr_engine.ocr(str(image_path), cls=True)
            lines = _extract_text_lines_from_paddle_result(raw_result)
            if use_vlm_extract and vlm_client is not None and page_index < vlm_extract_page_limit:
                try:
                    vlm_lines = _extract_text_lines_from_vlm_page(
                        client=vlm_client,
                        image_path=image_path,
                        page_number=page_index + 1,
                    )
                    lines = _merge_text_lines(lines, vlm_lines)
                    vlm_pages_processed += 1
                except Exception as exc:
                    vlm_pages_failed += 1
                    debug_rows.append(
                        f"VLM page extraction failed on page {page_index + 1}: {exc}"
                    )
            if lines:
                page_blocks.append(f"# Page {page_index + 1}\n" + "\n".join(lines))
            else:
                page_blocks.append(f"# Page {page_index + 1}\n")
        text_path.write_text("\n\n".join(page_blocks).strip() + "\n", encoding="utf-8")
        debug_rows.append(
            f"PaddleOCR extracted text for {max_pages}/{total_pages} page(s) at {render_dpi} DPI."
        )
        if use_vlm_extract:
            debug_rows.append(
                "VLM extraction merged on "
                f"{vlm_pages_processed}/{vlm_extract_page_limit} page(s)"
                + (f", failures={vlm_pages_failed}." if vlm_pages_failed else ".")
            )
    finally:
        if vlm_client is not None:
            try:
                vlm_client.close()
            except Exception:
                pass
        for image_path in image_paths:
            try:
                image_path.unlink(missing_ok=True)
            except Exception:
                pass
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass
    return text_path, debug_rows


def _build_target_uploaded_meta(
    *,
    target_path: Path,
    source_path: Path,
    uploaded_file_meta: dict[str, dict[str, Any]] | None,
    route: str,
    reader_mode: str,
) -> dict[str, dict[str, Any]]:
    meta_map = deepcopy(uploaded_file_meta or {})
    raw_source_key = str(source_path)
    try:
        source_key = str(source_path.resolve())
    except Exception:
        source_key = raw_source_key
    source_meta = dict(meta_map.get(source_key) or meta_map.get(raw_source_key) or {})
    if not source_meta:
        source_meta = {"name": source_path.name}
    try:
        target_key = str(target_path.resolve())
    except Exception:
        target_key = str(target_path)
    target_meta = dict(source_meta)
    target_meta["name"] = str(source_meta.get("name") or source_path.name)
    target_meta["source_original_name"] = source_path.name
    target_meta["source_original_path"] = source_key
    target_meta["ingestion_route"] = route
    target_meta["ingestion_reader_mode"] = reader_mode
    meta_map[target_key] = target_meta
    return meta_map


def _run_index_pipeline_for_file(
    *,
    index: Any,
    user_id: str,
    source_path: Path,
    target_path: Path,
    reindex: bool,
    base_settings: dict[str, Any],
    prefix: str,
    reader_mode: str,
    uploaded_file_meta: dict[str, dict[str, Any]] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    route: str = "normal",
) -> dict[str, Any]:
    request_settings = deepcopy(base_settings)
    request_settings[f"{prefix}reader_mode"] = str(reader_mode or "default")
    request_settings.setdefault(f"{prefix}quick_index_mode", UPLOAD_INDEX_QUICK_MODE)
    indexing_pipeline = index.get_indexing_pipeline(request_settings, user_id)
    effective_meta = _build_target_uploaded_meta(
        target_path=target_path,
        source_path=source_path,
        uploaded_file_meta=uploaded_file_meta,
        route=route,
        reader_mode=str(reader_mode or "default"),
    )
    stream = indexing_pipeline.stream(
        [target_path],
        reindex=reindex,
        uploaded_file_meta=effective_meta,
    )
    file_ids, errors, items, debug = collect_index_stream(
        stream,
        should_cancel=should_cancel,
    )
    return {
        "file_ids": file_ids,
        "errors": errors,
        "items": items,
        "debug": debug,
    }


def _index_pdf_with_paddleocr_route(
    *,
    index: Any,
    user_id: str,
    file_path: Path,
    reindex: bool,
    base_settings: dict[str, Any],
    prefix: str,
    uploaded_file_meta: dict[str, dict[str, Any]] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    extracted_text_path, route_debug = _extract_pdf_text_with_paddleocr(
        file_path=file_path,
        should_cancel=should_cancel,
    )
    try:
        response = _run_index_pipeline_for_file(
            index=index,
            user_id=user_id,
            source_path=file_path,
            target_path=extracted_text_path,
            reindex=reindex,
            base_settings=base_settings,
            prefix=prefix,
            reader_mode="default",
            uploaded_file_meta=uploaded_file_meta,
            should_cancel=should_cancel,
            route="heavy-pdf-paddleocr",
        )
        response["debug"] = [*route_debug, *list(response.get("debug") or [])]
        return response
    finally:
        try:
            extracted_text_path.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            parent_dir = extracted_text_path.parent
            if parent_dir.exists() and parent_dir.is_dir():
                parent_dir.rmdir()
        except Exception:
            pass


def _select_reader_mode_for_file(
    *,
    configured_mode: str,
    file_path: Path,
) -> str:
    mode = str(configured_mode or "").strip() or "default"
    if mode == "paddleocr":
        # PaddleOCR route is handled explicitly for heavy PDFs.
        mode = "default"
    if mode != "default":
        return mode
    ext = str(file_path.suffix or "").lower()
    if ext in OCR_PREFERRED_EXTENSIONS:
        # Image-first formats are more reliably parsed with OCR mode.
        return "ocr"
    if ext == ".pdf" and _pdf_should_use_ocr(file_path):
        # OCRAugmentedPDFReader preserves text layer while adding OCR-only regions.
        return "ocr"
    return "default"


def _fallback_reader_mode_for_pdf(
    file_path: Path,
    configured_mode: str,
    *,
    classification: dict[str, Any] | None = None,
) -> str:
    mode = str(configured_mode or "").strip() or "default"
    if mode in {"ocr", "adobe", "azure-di", "docling"}:
        return mode
    if classification is None:
        return "ocr" if _pdf_should_use_ocr(file_path) else "default"
    return "ocr" if bool(classification.get("use_ocr")) else "default"


def _should_route_pdf_to_paddle(
    *,
    configured_mode: str,
    classification: dict[str, Any],
) -> bool:
    mode = str(configured_mode or "").strip() or "default"
    if mode == "paddleocr":
        return True
    if mode != "default":
        return False
    return str(classification.get("route") or "normal") == "heavy"


class IndexingCanceledError(RuntimeError):
    def __init__(
        self,
        message: str = "Ingestion canceled by user.",
        *,
        file_ids: list[str] | None = None,
        errors: list[str] | None = None,
        items: list[dict[str, Any]] | None = None,
        debug: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.file_ids = list(file_ids or [])
        self.errors = list(errors or [])
        self.items = list(items or [])
        self.debug = list(debug or [])


def collect_index_stream(
    output_stream,
    should_cancel: Callable[[], bool] | None = None,
) -> tuple[list[str], list[str], list[dict], list[str]]:
    items: list[dict] = []
    debug: list[str] = []
    file_ids_raw: list[str | None] = []
    errors_raw: list[str | None] = []
    streamed_file_ids: list[str] = []

    def _raise_if_canceled() -> None:
        if not should_cancel or not should_cancel():
            return
        merged_file_ids = [
            file_id
            for file_id in [*streamed_file_ids, *file_ids_raw]
            if file_id
        ]
        dedup_file_ids = list(dict.fromkeys(merged_file_ids))
        raise IndexingCanceledError(
            file_ids=dedup_file_ids,
            errors=[str(error) for error in errors_raw if error],
            items=[dict(item) for item in items],
            debug=[str(message) for message in debug],
        )

    try:
        while True:
            _raise_if_canceled()
            response = next(output_stream)
            if response is None or response.channel is None:
                continue
            if response.channel == "index":
                content = response.content or {}
                file_id = content.get("file_id")
                file_id_text = str(file_id).strip() if file_id else ""
                if file_id_text:
                    streamed_file_ids.append(file_id_text)
                items.append(
                    {
                        "file_name": str(content.get("file_name", "")),
                        "status": str(content.get("status", "unknown")),
                        "message": content.get("message"),
                        "file_id": content.get("file_id"),
                    }
                )
            elif response.channel == "debug":
                text = response.text if response.text else str(response.content)
                debug.append(text)
            _raise_if_canceled()
    except StopIteration as stop:
        file_ids_raw, errors_raw, _docs = stop.value

    file_ids = [file_id for file_id in [*streamed_file_ids, *file_ids_raw] if file_id]
    file_ids = list(dict.fromkeys(file_ids))
    errors = [error for error in errors_raw if error]
    return file_ids, errors, items, debug


def apply_upload_scope_to_sources(
    index: Any,
    user_id: str,
    file_ids: list[str],
    scope: str,
) -> None:
    normalized_ids = normalize_ids(file_ids)
    if not normalized_ids:
        return

    Source = index._resources["Source"]
    is_private = bool(index.config.get("private", False))
    normalized_scope = normalize_upload_scope(scope)

    with Session(engine) as session:
        statement = select(Source).where(Source.id.in_(normalized_ids))
        if is_private:
            statement = statement.where(Source.user == user_id)
        rows = session.execute(statement).all()
        for row in rows:
            source = row[0]
            note = dict(source.note or {})
            note["upload_scope"] = normalized_scope
            source.note = note
            session.add(source)
        session.commit()


def index_files(
    context: ApiContext,
    user_id: str,
    file_paths: list[Path],
    index_id: int | None,
    reindex: bool,
    settings: dict[str, Any],
    scope: str = "persistent",
    uploaded_file_meta: dict[str, dict[str, Any]] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if not file_paths:
        raise HTTPException(status_code=400, detail="No files were provided.")

    index = get_index(context, index_id)
    prefix = f"index.options.{index.id}."
    base_settings = deepcopy(settings)
    configured_reader_mode = str(
        base_settings.get(f"{prefix}reader_mode", UPLOAD_INDEX_READER_MODE)
    ).strip() or UPLOAD_INDEX_READER_MODE
    all_file_ids: list[str] = []
    all_errors: list[str] = []
    all_items: list[dict[str, Any]] = []
    all_debug: list[str] = []
    for file_path in file_paths:
        ext = str(file_path.suffix or "").lower()
        is_pdf = ext == ".pdf"
        classification: dict[str, Any] = {}
        if is_pdf:
            classification = _classify_pdf_ingestion_route(file_path)
            all_debug.append(
                (
                    f"{file_path.name}: pdf route={classification.get('route', 'normal')} "
                    f"(reason={classification.get('reason', 'n/a')}, "
                    f"image_ratio={float(classification.get('image_ratio_all', 0.0)):.3f}, "
                    f"low_text_ratio={float(classification.get('low_text_ratio_sampled', 0.0)):.3f})."
                )
            )

        route_to_paddle = is_pdf and _should_route_pdf_to_paddle(
            configured_mode=configured_reader_mode,
            classification=classification,
        )

        response: dict[str, Any]
        try:
            if route_to_paddle:
                if not UPLOAD_PADDLEOCR_ENABLED:
                    raise RuntimeError("PaddleOCR routing is disabled by configuration.")
                response = _index_pdf_with_paddleocr_route(
                    index=index,
                    user_id=user_id,
                    file_path=file_path,
                    reindex=reindex,
                    base_settings=base_settings,
                    prefix=prefix,
                    uploaded_file_meta=uploaded_file_meta,
                    should_cancel=should_cancel,
                )
            else:
                if is_pdf:
                    selected_mode = _fallback_reader_mode_for_pdf(
                        file_path,
                        configured_reader_mode,
                        classification=classification,
                    )
                    route_name = "normal-pdf"
                else:
                    selected_mode = _select_reader_mode_for_file(
                        configured_mode=configured_reader_mode,
                        file_path=file_path,
                    )
                    route_name = "normal"
                response = _run_index_pipeline_for_file(
                    index=index,
                    user_id=user_id,
                    source_path=file_path,
                    target_path=file_path,
                    reindex=reindex,
                    base_settings=base_settings,
                    prefix=prefix,
                    reader_mode=selected_mode,
                    uploaded_file_meta=uploaded_file_meta,
                    should_cancel=should_cancel,
                    route=route_name,
                )
        except IndexingCanceledError:
            raise
        except Exception as exc:
            if not route_to_paddle:
                raise
            fallback_mode = _fallback_reader_mode_for_pdf(
                file_path,
                configured_reader_mode,
                classification=classification,
            )
            all_debug.append(
                f"{file_path.name}: PaddleOCR failed ({exc}); falling back to {fallback_mode}."
            )
            response = _run_index_pipeline_for_file(
                index=index,
                user_id=user_id,
                source_path=file_path,
                target_path=file_path,
                reindex=reindex,
                base_settings=base_settings,
                prefix=prefix,
                reader_mode=fallback_mode,
                uploaded_file_meta=uploaded_file_meta,
                should_cancel=should_cancel,
                route="heavy-pdf-fallback",
            )

        file_ids = list(response.get("file_ids") or [])
        errors = list(response.get("errors") or [])
        items = list(response.get("items") or [])
        debug = [str(msg) for msg in list(response.get("debug") or [])]
        all_file_ids.extend(file_ids)
        all_errors.extend(errors)
        all_items.extend(items)
        all_debug.extend(debug)
    apply_upload_scope_to_sources(
        index=index,
        user_id=user_id,
        file_ids=all_file_ids,
        scope=scope,
    )
    return {
        "index_id": index.id,
        "file_ids": all_file_ids,
        "errors": all_errors,
        "items": all_items,
        "debug": all_debug,
    }


def index_urls(
    context: ApiContext,
    user_id: str,
    urls: list[str],
    index_id: int | None,
    reindex: bool,
    settings: dict[str, Any],
    web_crawl_depth: int,
    web_crawl_max_pages: int,
    web_crawl_same_domain_only: bool,
    include_pdfs: bool,
    include_images: bool,
    scope: str = "persistent",
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    cleaned_urls = [url.strip() for url in urls if url and url.strip()]
    if not cleaned_urls:
        raise HTTPException(status_code=400, detail="No URLs were provided.")

    for url in cleaned_urls:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise HTTPException(status_code=400, detail=f"Invalid URL: {url}")

    index = get_index(context, index_id)
    request_settings = deepcopy(settings)
    prefix = f"index.options.{index.id}."
    request_settings.setdefault(f"{prefix}reader_mode", UPLOAD_INDEX_READER_MODE)
    request_settings.setdefault(f"{prefix}quick_index_mode", UPLOAD_INDEX_QUICK_MODE)
    request_settings[f"{prefix}web_crawl_depth"] = max(0, int(web_crawl_depth))
    request_settings[f"{prefix}web_crawl_max_pages"] = max(0, int(web_crawl_max_pages))
    request_settings[f"{prefix}web_crawl_same_domain_only"] = bool(
        web_crawl_same_domain_only
    )
    request_settings[f"{prefix}web_crawl_include_pdfs"] = bool(include_pdfs)
    request_settings[f"{prefix}web_crawl_include_images"] = bool(include_images)

    indexing_pipeline = index.get_indexing_pipeline(request_settings, user_id)
    stream = indexing_pipeline.stream(cleaned_urls, reindex=reindex)
    file_ids, errors, items, debug = collect_index_stream(
        stream,
        should_cancel=should_cancel,
    )
    apply_upload_scope_to_sources(
        index=index,
        user_id=user_id,
        file_ids=file_ids,
        scope=scope,
    )
    return {
        "index_id": index.id,
        "file_ids": file_ids,
        "errors": errors,
        "items": items,
        "debug": debug,
    }


def list_indexed_files(
    context: ApiContext,
    user_id: str,
    index_id: int | None,
    include_chat_temp: bool = False,
) -> dict[str, Any]:
    index = get_index(context, index_id)
    Source = index._resources["Source"]

    with Session(engine) as session:
        statement = select(Source)
        if index.config.get("private", False):
            statement = statement.where(Source.user == user_id)
        rows = session.execute(statement).all()

    files = []
    for row in rows:
        note = row[0].note or {}
        scope = normalize_upload_scope(str(note.get("upload_scope", "persistent")))
        if not include_chat_temp and scope == "chat_temp":
            continue
        files.append(
            {
                "id": row[0].id,
                "name": row[0].name,
                "size": int(row[0].size or 0),
                "note": note,
                "date_created": row[0].date_created,
            }
        )

    files = sorted(files, key=lambda item: item["date_created"], reverse=True)
    return {"index_id": index.id, "files": files}


def resolve_indexed_file_path(
    context: ApiContext,
    user_id: str,
    file_id: str,
    index_id: int | None,
) -> tuple[Path, str]:
    index = get_index(context, index_id)
    Source = index._resources["Source"]
    fs_path = Path(index._resources["FileStoragePath"])

    with Session(engine) as session:
        source = session.execute(select(Source).where(Source.id == file_id)).first()
        if not source:
            raise HTTPException(status_code=404, detail="File not found.")
        row = source[0]
        if index.config.get("private", False) and str(row.user or "") != user_id:
            raise HTTPException(status_code=403, detail="Access denied.")

        stored_name = str(row.name or "file")
        stored_path = str(row.path or "").strip()

    if not stored_path:
        raise HTTPException(status_code=404, detail="Indexed file path is missing.")

    candidate = Path(stored_path)
    if not candidate.is_absolute():
        candidate = fs_path / candidate
    candidate = candidate.resolve()

    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(
            status_code=404,
            detail="Stored file is not available on disk (likely URL-only source).",
        )

    return candidate, stored_name
