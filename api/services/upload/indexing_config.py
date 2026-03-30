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
    1, int(config("MAIA_UPLOAD_PDF_OCR_SCAN_PAGES", default=12, cast=int))
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
    96, int(config("MAIA_UPLOAD_PADDLEOCR_RENDER_DPI", default=150, cast=int))
)
UPLOAD_PADDLEOCR_MAX_PAGES = max(
    0, int(config("MAIA_UPLOAD_PADDLEOCR_MAX_PAGES", default=0, cast=int))
)  # 0 = all pages (no cap). Set to a positive number to limit OCR pages.
UPLOAD_PADDLEOCR_VL_API_ENABLED = bool(
    config("MAIA_UPLOAD_PADDLEOCR_VL_API_ENABLED", default=True, cast=bool)
)
UPLOAD_PADDLEOCR_VL_API_URL = str(
    config("MAIA_UPLOAD_PADDLEOCR_VL_API_URL", default="")
).strip()
UPLOAD_PADDLEOCR_VL_API_TOKEN = str(
    config("MAIA_UPLOAD_PADDLEOCR_VL_API_TOKEN", default="")
).strip()
UPLOAD_PADDLEOCR_VL_API_TIMEOUT_SECONDS = max(
    10.0,
    float(config("MAIA_UPLOAD_PADDLEOCR_VL_API_TIMEOUT_SECONDS", default=120.0, cast=float)),
)
UPLOAD_PADDLEOCR_VL_API_FILE_TYPE = max(
    0, min(1, int(config("MAIA_UPLOAD_PADDLEOCR_VL_API_FILE_TYPE", default=0, cast=int)))
)
UPLOAD_PADDLEOCR_VL_API_USE_DOC_ORIENTATION_CLASSIFY = bool(
    config("MAIA_UPLOAD_PADDLEOCR_VL_API_USE_DOC_ORIENTATION_CLASSIFY", default=False, cast=bool)
)
UPLOAD_PADDLEOCR_VL_API_USE_DOC_UNWARPING = bool(
    config("MAIA_UPLOAD_PADDLEOCR_VL_API_USE_DOC_UNWARPING", default=False, cast=bool)
)
UPLOAD_PADDLEOCR_VL_API_USE_CHART_RECOGNITION = bool(
    config("MAIA_UPLOAD_PADDLEOCR_VL_API_USE_CHART_RECOGNITION", default=False, cast=bool)
)
UPLOAD_PADDLEOCR_VL_API_VERIFY_SSL = bool(
    config("MAIA_UPLOAD_PADDLEOCR_VL_API_VERIFY_SSL", default=True, cast=bool)
)
UPLOAD_PADDLEOCR_VL_API_CA_BUNDLE = str(
    config("MAIA_UPLOAD_PADDLEOCR_VL_API_CA_BUNDLE", default="")
).strip()

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
    0, int(config("MAIA_UPLOAD_PDF_VLM_REVIEW_MAX_PAGES", default=3, cast=int))
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
