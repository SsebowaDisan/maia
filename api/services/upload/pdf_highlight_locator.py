from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache
import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Any


_PAGE_UNIT_CACHE_VERSION = "v1"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_bbox(
    *,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    page_width: float,
    page_height: float,
) -> dict[str, float] | None:
    if page_width <= 0 or page_height <= 0:
        return None
    left = max(0.0, min(1.0, float(x0) / float(page_width)))
    top = max(0.0, min(1.0, float(y0) / float(page_height)))
    right = max(left, min(1.0, float(x1) / float(page_width)))
    bottom = max(top, min(1.0, float(y1) / float(page_height)))
    width = max(0.0, right - left)
    height = max(0.0, bottom - top)
    if width < 0.0015 or height < 0.0015:
        return None
    return {
        "x": round(left, 6),
        "y": round(top, 6),
        "width": round(width, 6),
        "height": round(height, 6),
    }


def _tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", str(value or "").lower())


def _page_unit_cache_dir() -> Path:
    return Path(tempfile.gettempdir()) / "maia_pdf_page_units" / _PAGE_UNIT_CACHE_VERSION


def _page_unit_cache_path(file_path: Path, page_number: int) -> Path:
    try:
        stat = file_path.stat()
        signature = f"{file_path.resolve()}::{int(stat.st_size)}::{int(stat.st_mtime_ns)}::{int(page_number)}"
    except Exception:
        signature = f"{file_path}::{int(page_number)}"
    digest = hashlib.sha1(signature.encode("utf-8", errors="ignore")).hexdigest()
    return _page_unit_cache_dir() / f"{digest}.json"


def _load_cached_page_units(file_path: Path, page_number: int) -> dict[str, Any] | None:
    cache_path = _page_unit_cache_path(file_path, page_number)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if str(payload.get("page", "")) != str(page_number):
        return None
    units = payload.get("units")
    if not isinstance(units, list):
        return None
    return {
        "page": page_number,
        "page_width": float(payload.get("page_width", 0.0) or 0.0),
        "page_height": float(payload.get("page_height", 0.0) or 0.0),
        "units": units,
    }


def _store_cached_page_units(file_path: Path, page_number: int, payload: dict[str, Any]) -> None:
    cache_path = _page_unit_cache_path(file_path, page_number)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    except Exception:
        return


@lru_cache(maxsize=1)
def _get_rapidocr_engine() -> Any | None:
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        return RapidOCR()
    except Exception:
        return None


def _build_candidates(*, text: str, claim_text: str = "") -> list[str]:
    raw_candidates = [_normalize_text(text), _normalize_text(claim_text)]
    split_parts: list[str] = []
    for raw in raw_candidates:
        if not raw:
            continue
        split_parts.extend(re.split(r"(?<=[.!?])\s+|\s*[;:\u2014\u2013]\s*", raw))
    all_candidates = raw_candidates + split_parts
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in all_candidates:
        normalized = _normalize_text(candidate)
        if len(normalized) < 18:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(normalized)
        if len(deduped) >= 12:
            break
    return deduped


@lru_cache(maxsize=256)
def _extract_page_units_cached(file_path_str: str, page_number: int) -> dict[str, Any]:
    file_path = Path(file_path_str)
    cached_payload = _load_cached_page_units(file_path, page_number)
    if cached_payload is not None:
        return cached_payload
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception:
        return {"page": page_number, "page_width": 0.0, "page_height": 0.0, "units": []}

    doc = fitz.open(str(file_path))
    try:
        if page_number < 1 or page_number > int(getattr(doc, "page_count", 0) or 0):
            return {"page": page_number, "page_width": 0.0, "page_height": 0.0, "units": []}
        page = doc.load_page(page_number - 1)
        page_width = float(page.rect.width or 0.0)
        page_height = float(page.rect.height or 0.0)
        units: list[dict[str, Any]] = []
        cursor = 0
        text_dict = page.get_text("dict")
        for block in list(text_dict.get("blocks") or []):
            if int(block.get("type", 0) or 0) != 0:
                continue
            for line in list(block.get("lines") or []):
                spans = list(line.get("spans") or [])
                line_text = _normalize_text("".join(str(span.get("text", "") or "") for span in spans))
                if not line_text:
                    continue
                bbox = line.get("bbox") or block.get("bbox")
                if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                    continue
                normalized_box = _normalize_bbox(
                    x0=float(bbox[0]),
                    y0=float(bbox[1]),
                    x1=float(bbox[2]),
                    y1=float(bbox[3]),
                    page_width=page_width,
                    page_height=page_height,
                )
                if not normalized_box:
                    continue
                start = cursor
                end = start + len(line_text)
                units.append(
                    {
                        "text": line_text,
                        "char_start": start,
                        "char_end": end,
                        "highlight_boxes": [normalized_box],
                    }
                )
                cursor = end + 1
        if not units:
            try:
                engine = _get_rapidocr_engine()
                if engine is None:
                    raise RuntimeError("rapidocr engine unavailable")
                pixmap = page.get_pixmap(dpi=180)
                ocr_result, _elapsed = engine(pixmap.tobytes("png"))
                for item in list(ocr_result or []):
                    if not isinstance(item, (list, tuple)) or len(item) < 2:
                        continue
                    points = item[0]
                    line_text = _normalize_text(str(item[1] or ""))
                    if not line_text or not isinstance(points, (list, tuple)):
                        continue
                    xs: list[float] = []
                    ys: list[float] = []
                    for point in points:
                        if not isinstance(point, (list, tuple)) or len(point) < 2:
                            continue
                        xs.append(float(point[0]))
                        ys.append(float(point[1]))
                    if not xs or not ys:
                        continue
                    normalized_box = _normalize_bbox(
                        x0=min(xs),
                        y0=min(ys),
                        x1=max(xs),
                        y1=max(ys),
                        page_width=page_width,
                        page_height=page_height,
                    )
                    if not normalized_box:
                        continue
                    start = cursor
                    end = start + len(line_text)
                    units.append(
                        {
                            "text": line_text,
                            "char_start": start,
                            "char_end": end,
                            "highlight_boxes": [normalized_box],
                            "ocr": True,
                        }
                    )
                    cursor = end + 1
            except Exception:
                pass
        payload = {
            "page": page_number,
            "page_width": page_width,
            "page_height": page_height,
            "units": units,
        }
        _store_cached_page_units(file_path, page_number, payload)
        return payload
    finally:
        try:
            doc.close()
        except Exception:
            pass


def _extract_page_units(file_path: Path, page_number: int) -> dict[str, Any]:
    return _extract_page_units_cached(str(file_path), page_number)


def precompute_page_units_for_pdf(
    file_path: Path,
    *,
    max_pages: int = 0,
) -> dict[str, Any]:
    """Pre-extract and cache page units for ALL pages of a PDF.

    Runs in the background after indexing completes. Handles math-heavy
    and image-heavy PDFs by processing every page (OCR fallback included).
    Results are cached to disk so citation clicks are instant.

    For large PDFs (100+ pages), this may take minutes — call from a
    background thread, never from the upload request handler.

    Args:
        file_path: Path to the PDF file.
        max_pages: 0 = all pages (default). Set a limit only for testing.

    Returns summary: {pages_processed, pages_cached, pages_with_ocr, total_pages}
    """
    try:
        import fitz  # pymupdf
    except ImportError:
        return {"pages_processed": 0, "pages_cached": 0, "pages_with_ocr": 0,
                "total_pages": 0, "error": "pymupdf not installed"}

    if not file_path.exists():
        return {"pages_processed": 0, "pages_cached": 0, "pages_with_ocr": 0,
                "total_pages": 0, "error": "file not found"}

    try:
        doc = fitz.open(str(file_path))
        doc_page_count = doc.page_count
        total_pages = min(doc_page_count, max_pages) if max_pages > 0 else doc_page_count
        doc.close()
    except Exception as exc:
        return {"pages_processed": 0, "pages_cached": 0, "pages_with_ocr": 0,
                "total_pages": 0, "error": str(exc)[:200]}

    pages_processed = 0
    pages_with_ocr = 0
    for page_num in range(1, total_pages + 1):
        try:
            result = _extract_page_units_cached(str(file_path), page_num)
            pages_processed += 1
            units = result.get("units", [])
            if units and any(u.get("ocr") for u in units):
                pages_with_ocr += 1
        except Exception:
            continue

    return {
        "pages_processed": pages_processed,
        "pages_cached": pages_processed,
        "pages_with_ocr": pages_with_ocr,
        "total_pages": doc_page_count,
    }


def precompute_page_units_background(file_path: Path) -> None:
    """Fire-and-forget background precomputation.

    Call this after indexing a PDF. Spawns a daemon thread that
    pre-caches all page units (text + OCR). The user's upload
    returns immediately — precomputation happens in the background.
    """
    import threading

    def _run() -> None:
        try:
            precompute_page_units_for_pdf(file_path)
        except Exception:
            pass  # background — never crash the server

    thread = threading.Thread(
        target=_run,
        daemon=True,
        name=f"precompute-pages-{file_path.stem}",
    )
    thread.start()


def _score_window(candidate_tokens: list[str], candidate_text: str, window_text: str) -> float:
    if not candidate_tokens:
        return 0.0
    candidate_set = set(candidate_tokens)
    window_tokens = set(_tokenize(window_text))
    if not window_tokens:
        return 0.0
    overlap = len(candidate_set & window_tokens)
    coverage = overlap / max(1, len(candidate_set))
    density = overlap / max(1, len(window_tokens))
    lowered_window = window_text.lower()
    phrase_bonus = 0.0
    if len(candidate_tokens) >= 4:
        joined = " ".join(candidate_tokens[: min(12, len(candidate_tokens))])
        if joined and joined in lowered_window:
            phrase_bonus = 0.2
    normalized_candidate = _normalize_text(candidate_text).lower()
    fuzzy_bonus = 0.0
    if normalized_candidate:
        fuzzy_bonus = SequenceMatcher(None, normalized_candidate[:280], lowered_window[:420]).ratio() * 0.32
    return coverage * 0.68 + density * 0.18 + phrase_bonus + fuzzy_bonus


def _unit_box_metrics(unit: dict[str, Any]) -> tuple[float, float, float, float] | None:
    boxes = list(unit.get("highlight_boxes") or [])
    if not boxes:
        return None
    box = boxes[0]
    try:
        left = float(box.get("x", 0.0) or 0.0)
        top = float(box.get("y", 0.0) or 0.0)
        width = float(box.get("width", 0.0) or 0.0)
        height = float(box.get("height", 0.0) or 0.0)
    except Exception:
        return None
    return left, top, width, height


def _is_same_paragraph(left_unit: dict[str, Any], right_unit: dict[str, Any]) -> bool:
    left_metrics = _unit_box_metrics(left_unit)
    right_metrics = _unit_box_metrics(right_unit)
    if not left_metrics or not right_metrics:
        return False
    left_x, left_y, _left_w, left_h = left_metrics
    right_x, right_y, _right_w, right_h = right_metrics
    left_bottom = left_y + left_h
    vertical_gap = right_y - left_bottom
    if vertical_gap > max(left_h, right_h) * 1.8 + 0.014:
        return False
    indent_delta = abs(left_x - right_x)
    return indent_delta <= 0.11


def _looks_like_heading(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if len(normalized) <= 80 and normalized.rstrip(":").istitle():
        return True
    if len(normalized) <= 64 and normalized.isupper():
        return True
    return False


def _has_terminal_punctuation(text: str) -> bool:
    return bool(re.search(r"[.!?]\s*$", str(text or "").strip()))


def _expand_selection(units: list[dict[str, Any]], indexes: list[int]) -> list[int]:
    if not units or not indexes:
        return indexes
    start = min(indexes)
    end = max(indexes)
    max_units = min(12, len(units))

    while start > 0 and (end - start + 1) < max_units:
        previous = units[start - 1]
        current = units[start]
        current_text = str(current.get("text", "") or "")
        if not _is_same_paragraph(previous, current):
            break
        if _looks_like_heading(str(previous.get("text", "") or "")):
            break
        if _has_terminal_punctuation(str(previous.get("text", "") or "")) and current_text[:1].isupper():
            break
        start -= 1

    while end < len(units) - 1 and (end - start + 1) < max_units:
        current = units[end]
        following = units[end + 1]
        if not _is_same_paragraph(current, following):
            break
        if _looks_like_heading(str(following.get("text", "") or "")):
            break
        end += 1
        combined_text = " ".join(str(unit.get("text", "") or "") for unit in units[start : end + 1]).strip()
        if len(combined_text) >= 180 and _has_terminal_punctuation(str(units[end].get("text", "") or "")):
            break

    return list(range(start, end + 1))


def locate_pdf_highlight_target(
    *,
    file_path: Path,
    page: int | str,
    text: str,
    claim_text: str = "",
) -> dict[str, Any]:
    try:
        page_number = max(1, int(page))
    except Exception:
        page_number = 1
    page_payload = _extract_page_units(file_path, page_number)
    units = list(page_payload.get("units") or [])
    if not units:
        return {
            "page": str(page_number),
            "highlight_boxes": [],
            "evidence_units": [],
        }

    candidates = _build_candidates(text=text, claim_text=claim_text)
    if not candidates:
        return {
            "page": str(page_number),
            "highlight_boxes": [],
            "evidence_units": [],
        }

    best_indexes: list[int] = []
    best_score = 0.0
    max_window = min(9, len(units))
    for candidate in candidates:
        candidate_lower = candidate.lower()
        candidate_tokens = _tokenize(candidate)
        if not candidate_tokens:
            continue
        for start in range(len(units)):
            for width in range(1, max_window + 1):
                end = start + width
                if end > len(units):
                    break
                window_units = units[start:end]
                window_text = " ".join(str(item.get("text", "") or "") for item in window_units).strip()
                if not window_text:
                    continue
                window_lower = window_text.lower()
                score = _score_window(candidate_tokens, candidate, window_text)
                if candidate_lower in window_lower:
                    score += 0.45
                elif window_lower in candidate_lower and len(window_lower) >= 24:
                    score += 0.25
                if score > best_score:
                    best_score = score
                    best_indexes = list(range(start, end))

    if best_score < 0.21 or not best_indexes:
        return {
            "page": str(page_number),
            "highlight_boxes": [],
            "evidence_units": [],
        }

    expanded_indexes = _expand_selection(units, best_indexes)
    selected_units = [units[index] for index in expanded_indexes]
    highlight_boxes: list[dict[str, float]] = []
    evidence_units: list[dict[str, Any]] = []
    for unit in selected_units:
        boxes = list(unit.get("highlight_boxes") or [])
        if boxes:
            highlight_boxes.extend(boxes)
        evidence_units.append(
            {
                "text": str(unit.get("text", "") or "")[:320],
                "char_start": unit.get("char_start"),
                "char_end": unit.get("char_end"),
                "highlight_boxes": boxes,
            }
        )

    highlight_boxes = _merge_adjacent_boxes(highlight_boxes)

    return {
        "page": str(page_number),
        "highlight_boxes": highlight_boxes,
        "evidence_units": evidence_units,
    }


def _merge_adjacent_boxes(boxes: list[dict[str, float]]) -> list[dict[str, float]]:
    """Merge overlapping or vertically adjacent highlight boxes into larger regions.

    This prevents tiny clipped highlight islands by combining boxes that
    are on the same line (similar y) and overlap or touch horizontally.
    """
    if len(boxes) <= 1:
        return boxes

    # Sort by y (top), then x (left)
    sorted_boxes = sorted(boxes, key=lambda b: (b.get("y", 0), b.get("x", 0)))
    merged: list[dict[str, float]] = []
    current = dict(sorted_boxes[0])

    for box in sorted_boxes[1:]:
        curr_y = current.get("y", 0)
        curr_h = current.get("height", 0)
        curr_x = current.get("x", 0)
        curr_w = current.get("width", 0)
        next_y = box.get("y", 0)
        next_h = box.get("height", 0)
        next_x = box.get("x", 0)
        next_w = box.get("width", 0)

        # Same line: y values within 0.008 of each other (normalized coords)
        same_line = abs(curr_y - next_y) < 0.008
        # Horizontally adjacent or overlapping: next box starts before current ends + small gap
        h_adjacent = next_x <= (curr_x + curr_w + 0.015)

        if same_line and h_adjacent:
            # Merge: extend current box to cover both
            new_x = min(curr_x, next_x)
            new_right = max(curr_x + curr_w, next_x + next_w)
            new_y = min(curr_y, next_y)
            new_bottom = max(curr_y + curr_h, next_y + next_h)
            current = {
                "x": round(new_x, 6),
                "y": round(new_y, 6),
                "width": round(new_right - new_x, 6),
                "height": round(new_bottom - new_y, 6),
            }
        else:
            merged.append(current)
            current = dict(box)

    merged.append(current)
    return merged
