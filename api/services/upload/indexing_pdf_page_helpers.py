from __future__ import annotations

import base64
import json
from pathlib import Path
import re
from typing import Any, Callable

import httpx


def page_has_images_impl(page: Any) -> bool:
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


def sample_page_indexes_impl(total_pages: int, sample_size: int) -> list[int]:
    total = max(0, int(total_pages or 0))
    if total <= 0:
        return []
    size = max(1, min(total, int(sample_size or 1)))
    if size >= total:
        return list(range(total))
    last = total - 1
    return sorted({(last * i) // max(1, size - 1) for i in range(size)})


def count_image_pages_impl(
    pages: list[Any],
    *,
    page_has_images_fn: Callable[[Any], bool],
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
        if page_has_images_fn(pages[page_index]):
            count += 1
    return count


def normalize_page_indexes_impl(
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


def detect_pdf_images_with_pymupdf_impl(
    path: Path,
    *,
    normalize_page_indexes_fn: Callable[..., list[int]],
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
        indexes = normalize_page_indexes_fn(
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


def ollama_timeout_impl(timeout_seconds: float) -> httpx.Timeout:
    timeout_value = max(1.0, float(timeout_seconds))
    return httpx.Timeout(timeout=timeout_value, connect=min(10.0, timeout_value))


def extract_json_object_impl(text: str) -> dict[str, Any] | None:
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


def parse_vlm_classifier_response_impl(
    text: str,
    *,
    extract_json_object_fn: Callable[[str], dict[str, Any] | None],
) -> dict[str, Any]:
    payload = extract_json_object_fn(text)
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


def dedupe_text_lines_impl(lines: list[str]) -> list[str]:
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


def extract_text_lines_from_vlm_response_impl(
    text: str,
    *,
    extract_json_object_fn: Callable[[str], dict[str, Any] | None],
    dedupe_text_lines_fn: Callable[[list[str]], list[str]],
) -> list[str]:
    content = str(text or "").strip()
    if not content:
        return []
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        content = content.strip()

    payload = extract_json_object_fn(content)
    if isinstance(payload, dict):
        for key in ("text", "content", "output", "transcript"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                content = value.strip()
                break
        else:
            lines_payload = payload.get("lines")
            if isinstance(lines_payload, list):
                return dedupe_text_lines_fn([str(item) for item in lines_payload if item])

    return dedupe_text_lines_fn(content.splitlines())


def merge_text_lines_impl(
    primary: list[str],
    extra: list[str],
    *,
    dedupe_text_lines_fn: Callable[[list[str]], list[str]],
) -> list[str]:
    return dedupe_text_lines_fn([*list(primary or []), *list(extra or [])])


def run_ollama_vlm_for_image_impl(
    *,
    client: httpx.Client,
    model: str,
    prompt: str,
    image_path: Path,
    base_url: str,
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
    url = f"{base_url}/api/chat"
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
