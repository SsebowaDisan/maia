from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from decouple import config
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ktem.db.engine import engine

from api.context import ApiContext

from .common import get_index, normalize_ids, normalize_upload_scope

_raw_upload_reader_mode = str(
    config("MAIA_UPLOAD_INDEX_READER_MODE", default="default")
).strip()
UPLOAD_INDEX_READER_MODE = (
    _raw_upload_reader_mode
    if _raw_upload_reader_mode in {"default", "ocr", "adobe", "azure-di", "docling"}
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


def _pdf_should_use_ocr(path: Path) -> bool:
    if UPLOAD_PDF_OCR_POLICY == "always":
        return True
    if UPLOAD_PDF_OCR_POLICY == "never":
        return False

    try:
        from pypdf import PdfReader
    except Exception:
        return False

    try:
        reader = PdfReader(str(path))
        pages = list(getattr(reader, "pages", []))
    except Exception:
        # If PDF text probing fails, OCR is the safer fallback.
        return True

    total_pages = len(pages)
    if total_pages <= 0:
        return True

    sampled_indexes = _sample_page_indexes(total_pages, UPLOAD_PDF_OCR_SCAN_PAGES)
    if not sampled_indexes:
        return True
    low_text_pages = 0
    image_pages = 0
    sampled_pages = 0

    for page_index in sampled_indexes:
        page = pages[page_index]
        sampled_pages += 1
        has_images = _page_has_images(page)
        if has_images:
            image_pages += 1
        extracted = ""
        try:
            extracted = str(page.extract_text() or "")
        except Exception:
            extracted = ""
        compact_len = len("".join(extracted.split()))
        if compact_len < UPLOAD_PDF_OCR_MIN_TEXT_CHARS_PER_PAGE:
            low_text_pages += 1
        if (
            UPLOAD_PDF_OCR_TRIGGER_ON_ANY_VERY_LOW_TEXT_PAGE
            and compact_len < UPLOAD_PDF_OCR_VERY_LOW_TEXT_CHARS_PER_PAGE
        ):
            return True
        if (
            UPLOAD_PDF_OCR_TRIGGER_ON_ANY_IMAGE_LOW_TEXT_PAGE
            and has_images
            and compact_len < UPLOAD_PDF_OCR_MIN_TEXT_CHARS_PER_PAGE
        ):
            return True

    if sampled_pages <= 0:
        return True

    low_text_ratio = low_text_pages / float(sampled_pages)
    image_ratio = image_pages / float(sampled_pages)
    # Full-document image scan catches sparse formula/image sections that
    # might be missed by sampled page text probes in long technical PDFs.
    image_pages_all = _count_image_pages(
        pages,
        skip_edge_pages=UPLOAD_PDF_OCR_SKIP_EDGE_PAGES,
    )
    image_ratio_all = image_pages_all / float(total_pages)
    if UPLOAD_PDF_OCR_TRIGGER_ON_ANY_IMAGE_PAGE_FULL_SCAN and image_pages_all > 0:
        return True
    return (
        low_text_ratio >= UPLOAD_PDF_OCR_MIN_LOW_TEXT_PAGE_RATIO
        or image_ratio >= UPLOAD_PDF_OCR_MIN_IMAGE_PAGE_RATIO
        or (
            image_pages_all >= UPLOAD_PDF_OCR_MIN_IMAGE_PAGES_FULL_SCAN
            and image_ratio_all >= UPLOAD_PDF_OCR_MIN_IMAGE_PAGE_RATIO_FULL_SCAN
        )
    )


def _select_reader_mode_for_file(
    *,
    configured_mode: str,
    file_path: Path,
) -> str:
    mode = str(configured_mode or "").strip() or "default"
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


def collect_index_stream(output_stream) -> tuple[list[str], list[str], list[dict], list[str]]:
    items: list[dict] = []
    debug: list[str] = []
    file_ids_raw: list[str | None] = []
    errors_raw: list[str | None] = []

    try:
        while True:
            response = next(output_stream)
            if response is None or response.channel is None:
                continue
            if response.channel == "index":
                content = response.content or {}
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
    except StopIteration as stop:
        file_ids_raw, errors_raw, _docs = stop.value

    file_ids = [file_id for file_id in file_ids_raw if file_id]
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
        request_settings = deepcopy(base_settings)
        request_settings[f"{prefix}reader_mode"] = _select_reader_mode_for_file(
            configured_mode=configured_reader_mode,
            file_path=file_path,
        )
        request_settings.setdefault(f"{prefix}quick_index_mode", UPLOAD_INDEX_QUICK_MODE)
        indexing_pipeline = index.get_indexing_pipeline(request_settings, user_id)
        stream = indexing_pipeline.stream(
            [file_path],
            reindex=reindex,
            uploaded_file_meta=uploaded_file_meta or {},
        )
        file_ids, errors, items, debug = collect_index_stream(stream)
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
    file_ids, errors, items, debug = collect_index_stream(stream)
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
