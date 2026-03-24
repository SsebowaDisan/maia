from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

import httpx

from .indexing_pdf_page_helpers import (
    detect_pdf_images_with_pymupdf_impl,
    normalize_page_indexes_impl,
)


def review_pdf_route_with_vlm_impl(
    path: Path,
    *,
    total_pages_hint: int,
    sampled_indexes: list[int] | None,
    review_enabled: bool,
    review_max_pages: int,
    review_render_dpi: int,
    review_timeout_seconds: float,
    review_model: str,
    base_url: str,
    normalize_page_indexes_fn: Callable[..., list[int]],
    sample_page_indexes_fn: Callable[[int, int], list[int]],
    ollama_timeout_fn: Callable[[float], httpx.Timeout],
    run_ollama_vlm_for_image_fn: Callable[..., str],
    parse_vlm_classifier_response_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    if not review_enabled:
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

    import tempfile

    doc = None
    image_paths: list[Path] = []
    work_dir = Path(tempfile.mkdtemp(prefix="vlm-review-", dir=str(path.parent)))
    checked_pages = 0
    try:
        doc = fitz.open(str(path))
        total_pages = max(int(getattr(doc, "page_count", 0) or 0), int(total_pages_hint or 0))
        page_indexes = normalize_page_indexes_fn(
            total_pages=total_pages,
            page_indexes=sampled_indexes,
            skip_edge_pages=0,
        )
        if not page_indexes:
            page_indexes = list(range(total_pages))
        if review_max_pages > 0 and len(page_indexes) > review_max_pages:
            sampled_positions = sample_page_indexes_fn(len(page_indexes), review_max_pages)
            page_indexes = [page_indexes[pos] for pos in sampled_positions if 0 <= pos < len(page_indexes)]

        prompt = (
            "You are classifying a PDF page for ingestion routing. "
            "Return JSON only with keys needs_ocr (boolean) and reason (short string). "
            "needs_ocr must be true when this page contains scanned text, text embedded in images, "
            "equations/charts/diagrams where plain PDF text extraction may miss important content."
        )
        # Phase 1: render pages serially — fitz document is not thread-safe.
        rendered: list[Path] = []
        for page_index in page_indexes:
            page = doc.load_page(page_index)
            image_path = work_dir / f"review-page-{page_index + 1}.png"
            image_paths.append(image_path)
            pix = page.get_pixmap(dpi=review_render_dpi, alpha=False)
            pix.save(str(image_path))
            rendered.append(image_path)

        if not rendered:
            return {"enabled": True, "upgrade": False, "checked_pages": 0, "reason": "vlm-review-kept-normal"}

        # Phase 2: run VLM inference concurrently across rendered page images.
        # httpx.Client is thread-safe; each thread reuses the same connection pool.
        with httpx.Client(timeout=ollama_timeout_fn(review_timeout_seconds)) as client:
            def _infer(img_path: Path) -> dict[str, Any]:
                raw = run_ollama_vlm_for_image_fn(
                    client=client,
                    model=review_model,
                    prompt=prompt,
                    image_path=img_path,
                    base_url=base_url,
                )
                return parse_vlm_classifier_response_fn(raw)

            max_workers = min(max(1, len(rendered)), 4)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                verdicts = list(executor.map(_infer, rendered))

        checked_pages = len(verdicts)
        for verdict in verdicts:
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


def apply_vlm_review_upgrade_impl(
    path: Path,
    classification: dict[str, Any],
    *,
    sampled_indexes: list[int] | None,
    review_enabled: bool,
    review_pdf_route_with_vlm_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    result = dict(classification or {})
    if not review_enabled:
        return result
    if str(result.get("route") or "normal") != "normal":
        result["vlm_review"] = "skipped-non-normal"
        return result

    review = review_pdf_route_with_vlm_fn(
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


def classify_pdf_ingestion_route_cached_impl(
    resolved_path: str,
    modified_ns: int,
    file_size: int,
    *,
    policy: str,
    scan_pages: int,
    min_text_chars_per_page: int,
    very_low_text_chars_per_page: int,
    min_low_text_page_ratio: float,
    min_image_page_ratio: float,
    trigger_any_image_low_text_page: bool,
    trigger_any_very_low_text_page: bool,
    min_image_pages_full_scan: int,
    trigger_any_image_page_full_scan: bool,
    skip_edge_pages: int,
    min_image_page_ratio_full_scan: float,
    heavy_min_image_page_ratio: float,
    heavy_min_low_text_page_ratio: float,
    heavy_on_any_image_page: bool,
    sample_page_indexes_fn: Callable[[int, int], list[int]],
    page_has_images_fn: Callable[[Any], bool],
    detect_pdf_images_with_pymupdf_fn: Callable[..., tuple[set[int], int]],
    apply_vlm_review_upgrade_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    _ = modified_ns
    _ = file_size
    path = Path(resolved_path)
    if policy == "always":
        return {
            "route": "heavy",
            "use_ocr": True,
            "reason": "ocr-policy-always",
            "total_pages": 0,
            "image_pages_all": 0,
            "image_ratio_all": 0.0,
            "low_text_ratio_sampled": 0.0,
        }
    if policy == "never":
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

    sampled_indexes = sample_page_indexes_fn(total_pages, scan_pages)
    sampled_pages = 0
    sample_image_pages = 0
    low_text_pages = 0
    very_low_text_detected = False
    image_and_low_text_detected = False
    sampled_page_metrics: list[dict[str, Any]] = []

    for page_index in sampled_indexes:
        page = pages[page_index]
        sampled_pages += 1
        has_images = page_has_images_fn(page)
        if has_images:
            sample_image_pages += 1
        extracted = ""
        try:
            extracted = str(page.extract_text() or "")
        except Exception:
            extracted = ""
        compact_len = len("".join(extracted.split()))
        if compact_len < min_text_chars_per_page:
            low_text_pages += 1
        if compact_len < very_low_text_chars_per_page:
            very_low_text_detected = True
        if has_images and compact_len < min_text_chars_per_page:
            image_and_low_text_detected = True
        sampled_page_metrics.append(
            {
                "page_index": int(page_index),
                "has_images": bool(has_images),
                "compact_len": int(compact_len),
            }
        )

    fitz_native_text_pages = 0
    fitz_probe_error = ""
    if sampled_page_metrics and low_text_pages > 0:
        try:
            import fitz  # type: ignore[import-not-found]

            doc = fitz.open(str(path))
            try:
                adjusted_low_text_pages = 0
                adjusted_very_low_text_detected = False
                adjusted_image_and_low_text_detected = False
                for page_metric in sampled_page_metrics:
                    compact_len = int(page_metric.get("compact_len", 0) or 0)
                    page_index = int(page_metric.get("page_index", 0) or 0)
                    has_images = bool(page_metric.get("has_images"))
                    fitz_compact_len = compact_len
                    if compact_len < min_text_chars_per_page and 0 <= page_index < int(
                        getattr(doc, "page_count", 0) or 0
                    ):
                        try:
                            fitz_text = str(doc.load_page(page_index).get_text("text") or "")
                        except Exception:
                            fitz_text = ""
                        fitz_compact_len = len("".join(fitz_text.split()))
                    if fitz_compact_len >= min_text_chars_per_page:
                        fitz_native_text_pages += 1
                        continue
                    adjusted_low_text_pages += 1
                    if fitz_compact_len < very_low_text_chars_per_page:
                        adjusted_very_low_text_detected = True
                    if has_images and fitz_compact_len < min_text_chars_per_page:
                        adjusted_image_and_low_text_detected = True

                low_text_pages = adjusted_low_text_pages
                very_low_text_detected = adjusted_very_low_text_detected
                image_and_low_text_detected = adjusted_image_and_low_text_detected
            finally:
                doc.close()
        except Exception as exc:
            fitz_probe_error = str(exc)

    sampled_pages = max(1, sampled_pages)
    low_text_ratio = low_text_pages / float(sampled_pages)
    sample_image_ratio = sample_image_pages / float(sampled_pages)
    # Use fitz (PyMuPDF) as the single authoritative image-page scanner.
    # The prior pypdf count_image_pages full pass was redundant — fitz already
    # walks every page and returns a superset of what pypdf detects.
    image_pages_pymupdf, pymupdf_total_pages = detect_pdf_images_with_pymupdf_fn(
        path,
        skip_edge_pages=skip_edge_pages,
    )
    image_pages_all = len(image_pages_pymupdf)
    effective_total_pages = max(total_pages, pymupdf_total_pages or 0)
    image_ratio_all = image_pages_all / float(max(1, effective_total_pages))

    force_heavy_any_image = (
        heavy_on_any_image_page and trigger_any_image_page_full_scan
    )
    should_use_ocr = (
        (trigger_any_very_low_text_page and very_low_text_detected)
        or (
            trigger_any_image_low_text_page
            and image_and_low_text_detected
        )
        or (
            trigger_any_image_page_full_scan
            and image_pages_all > 0
        )
        or (low_text_ratio >= min_low_text_page_ratio)
        or (sample_image_ratio >= min_image_page_ratio)
        or (
            image_pages_all >= min_image_pages_full_scan
            and image_ratio_all >= min_image_page_ratio_full_scan
        )
    )
    heavy = bool(should_use_ocr) and (
        force_heavy_any_image
        or image_ratio_all >= heavy_min_image_page_ratio
        or low_text_ratio >= heavy_min_low_text_page_ratio
    )

    reason = "normal"
    if force_heavy_any_image and image_pages_all > 0:
        reason = "heavy-any-image-page"
    elif low_text_ratio >= heavy_min_low_text_page_ratio and should_use_ocr:
        reason = "heavy-low-text-ratio"
    elif image_ratio_all >= heavy_min_image_page_ratio and should_use_ocr:
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
        "fitz_native_text_pages_sampled": int(fitz_native_text_pages),
    }
    if fitz_probe_error:
        classification["fitz_probe_error"] = fitz_probe_error
    return apply_vlm_review_upgrade_fn(
        path,
        classification,
        sampled_indexes=sampled_indexes,
    )


def classify_pdf_ingestion_route_impl(
    path: Path,
    *,
    classify_pdf_ingestion_route_cached_fn: Callable[[str, int, int], dict[str, Any]],
) -> dict[str, Any]:
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
    return classify_pdf_ingestion_route_cached_fn(resolved, modified_ns, file_size)


def pdf_should_use_ocr_impl(
    path: Path,
    *,
    classify_pdf_ingestion_route_fn: Callable[[Path], dict[str, Any]],
) -> bool:
    classification = classify_pdf_ingestion_route_fn(path)
    return bool(classification.get("use_ocr"))


def select_reader_mode_for_file_impl(
    *,
    configured_mode: str,
    file_path: Path,
    ocr_preferred_extensions: set[str],
    pdf_should_use_ocr_fn: Callable[[Path], bool],
) -> str:
    mode = str(configured_mode or "").strip() or "default"
    if mode == "paddleocr":
        mode = "default"
    if mode != "default":
        return mode
    ext = str(file_path.suffix or "").lower()
    if ext in ocr_preferred_extensions:
        return "ocr"
    if ext == ".pdf" and pdf_should_use_ocr_fn(file_path):
        return "ocr"
    return "default"


def fallback_reader_mode_for_pdf_impl(
    file_path: Path,
    configured_mode: str,
    *,
    classification: dict[str, Any] | None,
    pdf_should_use_ocr_fn: Callable[[Path], bool],
) -> str:
    mode = str(configured_mode or "").strip() or "default"
    if mode in {"ocr", "adobe", "azure-di", "docling"}:
        return mode
    if classification is None:
        return "ocr" if pdf_should_use_ocr_fn(file_path) else "default"
    return "ocr" if bool(classification.get("use_ocr")) else "default"


def should_route_pdf_to_paddle_impl(
    *,
    configured_mode: str,
    classification: dict[str, Any],
    paddleocr_vl_api_enabled: bool,
    paddleocr_vl_api_url: str,
    paddleocr_vl_api_token: str,
) -> bool:
    mode = str(configured_mode or "").strip() or "default"
    if mode == "paddleocr":
        return True
    if mode != "default":
        return False
    remote_configured = bool(
        paddleocr_vl_api_enabled
        and str(paddleocr_vl_api_url or "").strip()
        and str(paddleocr_vl_api_token or "").strip()
    )
    if not remote_configured:
        return str(classification.get("route") or "normal") == "heavy"

    route = str(classification.get("route") or "normal")
    if route != "heavy" or not bool(classification.get("use_ocr")):
        return False

    image_pages_all = int(classification.get("image_pages_all", 0) or 0)
    reason = str(classification.get("reason") or "").strip().lower()
    if image_pages_all > 0:
        return True
    if "image" in reason:
        return True
    if reason in {"pdf-probe-failed", "empty-pdf-pages"}:
        return True
    return False
