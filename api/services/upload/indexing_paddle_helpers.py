from __future__ import annotations

import base64
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Callable
import uuid

import httpx
from sqlalchemy import select
from sqlmodel import Session

from ktem.db.engine import engine

from api.services.observability.citation_trace import record_trace_event


def get_paddle_ocr_engine_impl(
    *,
    paddle_ocr_engine_ref: dict[str, Any],
    paddle_ocr_lock: Any,
    paddleocr_lang: str,
    paddleocr_use_gpu: bool,
) -> Any:
    with paddle_ocr_lock:
        if paddle_ocr_engine_ref.get("engine") is not None:
            return paddle_ocr_engine_ref.get("engine")
        try:
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]
        except Exception as exc:
            raise RuntimeError("PaddleOCR package is not installed.") from exc

        kwargs: dict[str, Any] = {
            "use_angle_cls": True,
            "lang": paddleocr_lang,
            "show_log": False,
        }
        kwargs["use_gpu"] = bool(paddleocr_use_gpu)
        try:
            paddle_ocr_engine_ref["engine"] = PaddleOCR(**kwargs)
        except TypeError:
            kwargs.pop("show_log", None)
            paddle_ocr_engine_ref["engine"] = PaddleOCR(**kwargs)
        return paddle_ocr_engine_ref.get("engine")


def extract_text_lines_from_paddle_result_impl(raw_result: Any) -> list[str]:
    lines: list[str] = []

    def _visit(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                _visit(value)
            return
        if isinstance(node, (list, tuple)):
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


def extract_text_lines_from_vlm_page_impl(
    *,
    client: httpx.Client,
    image_path: Path,
    page_number: int,
    extract_model: str,
    run_ollama_vlm_for_image_fn: Callable[..., str],
    extract_text_lines_from_vlm_response_fn: Callable[[str], list[str]],
    base_url: str,
) -> list[str]:
    prompt = (
        "Extract all meaningful visible text from this page image, including text in diagrams, "
        "tables, formulas, equations, and chart labels. "
        "For mathematical formulas and equations, preserve them in LaTeX notation "
        "(e.g., $x^2 + y^2 = z^2$, $\\sum_{t=1}^{n} \\frac{CF_t}{(1+r)^t}$). "
        "For Greek letters use LaTeX: alpha→$\\alpha$, sigma→$\\sigma$, etc. "
        "Return one logical line per line. "
        f"Page number: {page_number}."
    )
    raw = run_ollama_vlm_for_image_fn(
        client=client,
        model=extract_model,
        prompt=prompt,
        image_path=image_path,
        base_url=base_url,
    )
    return extract_text_lines_from_vlm_response_fn(raw)


def extract_pdf_text_with_paddleocr_impl(
    file_path: Path,
    *,
    should_cancel: Callable[[], bool] | None,
    get_paddle_ocr_engine_fn: Callable[[], Any],
    extract_text_lines_from_paddle_result_fn: Callable[[Any], list[str]],
    merge_text_lines_fn: Callable[[list[str], list[str]], list[str]],
    extract_text_lines_from_vlm_page_fn: Callable[..., list[str]],
    indexing_canceled_error_cls: type[Exception],
    paddleocr_max_pages: int,
    paddleocr_render_dpi: int,
    vlm_extract_enabled: bool,
    vlm_extract_max_pages: int,
    vlm_extract_render_dpi: int,
    vlm_extract_timeout_seconds: float,
    ollama_timeout_fn: Callable[[float], httpx.Timeout],
    paddleocr_vl_api_enabled: bool,
    paddleocr_vl_api_url: str,
    paddleocr_vl_api_token: str,
    paddleocr_vl_api_timeout_seconds: float,
    paddleocr_vl_api_file_type: int,
    paddleocr_vl_api_use_doc_orientation_classify: bool,
    paddleocr_vl_api_use_doc_unwarping: bool,
    paddleocr_vl_api_use_chart_recognition: bool,
    paddleocr_vl_api_verify_ssl: bool,
    paddleocr_vl_api_ca_bundle: str,
) -> tuple[Path, list[str]]:
    remote_configured = bool(
        str(paddleocr_vl_api_url or "").strip() and str(paddleocr_vl_api_token or "").strip()
    )
    record_trace_event(
        "index.ocr_started",
        {
            "file_name": file_path.name,
            "route": "heavy-pdf-paddleocr-vl-api"
            if bool(paddleocr_vl_api_enabled) and remote_configured
            else "heavy-pdf-paddleocr",
        },
    )
    if bool(paddleocr_vl_api_enabled) and remote_configured:
        return _extract_pdf_text_with_paddleocr_vl_api_impl(
            file_path=file_path,
            should_cancel=should_cancel,
            indexing_canceled_error_cls=indexing_canceled_error_cls,
            api_url=paddleocr_vl_api_url,
            api_token=paddleocr_vl_api_token,
            timeout_seconds=paddleocr_vl_api_timeout_seconds,
            file_type=paddleocr_vl_api_file_type,
            use_doc_orientation_classify=paddleocr_vl_api_use_doc_orientation_classify,
            use_doc_unwarping=paddleocr_vl_api_use_doc_unwarping,
            use_chart_recognition=paddleocr_vl_api_use_chart_recognition,
            verify_ssl=paddleocr_vl_api_verify_ssl,
            ca_bundle=paddleocr_vl_api_ca_bundle,
        )

    try:
        import fitz  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError("PyMuPDF (fitz) is required for PaddleOCR PDF routing.") from exc

    ocr_engine = get_paddle_ocr_engine_fn()
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
            if paddleocr_max_pages <= 0
            else min(total_pages, int(paddleocr_max_pages))
        )
        vlm_extract_page_limit = (
            max_pages
            if vlm_extract_max_pages <= 0
            else min(max_pages, int(vlm_extract_max_pages))
        )
        use_vlm_extract = bool(vlm_extract_enabled and vlm_extract_page_limit > 0)
        render_dpi = int(paddleocr_render_dpi)
        if use_vlm_extract:
            render_dpi = max(render_dpi, int(vlm_extract_render_dpi))
        if use_vlm_extract:
            vlm_client = httpx.Client(timeout=ollama_timeout_fn(vlm_extract_timeout_seconds))
        record_trace_event(
            "index.ocr_page_plan",
            {
                "file_name": file_path.name,
                "total_pages": total_pages,
                "pages_to_process": max_pages,
                "render_dpi": render_dpi,
                "vlm_extract_enabled": use_vlm_extract,
                "vlm_extract_page_limit": vlm_extract_page_limit,
            },
        )
        page_blocks: list[str] = []
        for page_index in range(max_pages):
            if should_cancel and should_cancel():
                raise indexing_canceled_error_cls("Ingestion canceled by user.")
            page = doc.load_page(page_index)
            image_path = work_dir / f"page-{page_index + 1}.png"
            image_paths.append(image_path)
            pix = page.get_pixmap(dpi=render_dpi, alpha=False)
            pix.save(str(image_path))
            raw_result = ocr_engine.ocr(str(image_path), cls=True)
            lines = extract_text_lines_from_paddle_result_fn(raw_result)
            if use_vlm_extract and vlm_client is not None and page_index < vlm_extract_page_limit:
                try:
                    vlm_lines = extract_text_lines_from_vlm_page_fn(
                        client=vlm_client,
                        image_path=image_path,
                        page_number=page_index + 1,
                    )
                    lines = merge_text_lines_fn(lines, vlm_lines)
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
        record_trace_event(
            "index.ocr_completed",
            {
                "file_name": file_path.name,
                "pages_processed": max_pages,
                "total_pages": total_pages,
                "output_path": str(text_path),
                "vlm_pages_processed": vlm_pages_processed,
                "vlm_pages_failed": vlm_pages_failed,
            },
        )
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


def _extract_pdf_text_with_paddleocr_vl_api_impl(
    *,
    file_path: Path,
    should_cancel: Callable[[], bool] | None,
    indexing_canceled_error_cls: type[Exception],
    api_url: str,
    api_token: str,
    timeout_seconds: float,
    file_type: int,
    use_doc_orientation_classify: bool,
    use_doc_unwarping: bool,
    use_chart_recognition: bool,
    verify_ssl: bool,
    ca_bundle: str,
) -> tuple[Path, list[str]]:
    if should_cancel and should_cancel():
        raise indexing_canceled_error_cls("Ingestion canceled by user.")
    if not str(api_url or "").strip():
        raise RuntimeError("PaddleOCR-VL API URL is not configured.")
    if not str(api_token or "").strip():
        raise RuntimeError("PaddleOCR-VL API token is not configured.")

    work_dir = Path(tempfile.mkdtemp(prefix="paddleocr-vl-api-", dir=str(file_path.parent)))
    text_path = work_dir / f"{file_path.stem}-{uuid.uuid4().hex[:8]}.txt"
    debug_rows: list[str] = []

    file_bytes = file_path.read_bytes()
    if not file_bytes:
        raise RuntimeError("Uploaded file is empty.")
    encoded_file = base64.b64encode(file_bytes).decode("ascii")

    payload: dict[str, Any] = {
        "file": encoded_file,
        "fileType": int(max(0, min(1, file_type))),
        "useDocOrientationClassify": bool(use_doc_orientation_classify),
        "useDocUnwarping": bool(use_doc_unwarping),
        "useChartRecognition": bool(use_chart_recognition),
    }
    headers = {
        "Authorization": f"token {api_token}",
        "Content-Type": "application/json",
    }
    verify: bool | str = bool(verify_ssl)
    if verify and str(ca_bundle or "").strip():
        verify = str(ca_bundle).strip()

    try:
        timeout = httpx.Timeout(max(10.0, float(timeout_seconds)))
        with httpx.Client(timeout=timeout, verify=verify) as client:
            response = client.post(str(api_url).strip(), json=payload, headers=headers)
    except Exception as exc:
        raise RuntimeError(f"PaddleOCR-VL API request failed: {exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(
            "PaddleOCR-VL API returned non-200 status "
            f"{response.status_code}: {response.text[:300]}"
        )

    try:
        body = response.json()
    except Exception as exc:
        raise RuntimeError("PaddleOCR-VL API returned non-JSON response.") from exc

    result = body.get("result") if isinstance(body, dict) else None
    layout_results = (
        result.get("layoutParsingResults")
        if isinstance(result, dict)
        else None
    )
    if not isinstance(layout_results, list) or not layout_results:
        raise RuntimeError("PaddleOCR-VL API response did not include layoutParsingResults.")

    page_blocks: dict[str, list[str]] = {}
    markdown_docs = 0
    for idx, row in enumerate(layout_results, start=1):
        if should_cancel and should_cancel():
            raise indexing_canceled_error_cls("Ingestion canceled by user.")
        if not isinstance(row, dict):
            continue
        markdown_text = ""
        markdown_obj = row.get("markdown")
        if isinstance(markdown_obj, dict):
            markdown_text = str(markdown_obj.get("text") or "").strip()
        if not markdown_text:
            markdown_text = str(row.get("text") or "").strip()
        if not markdown_text:
            continue
        markdown_docs += 1
        page_value = (
            row.get("pageNumber")
            or row.get("page_number")
            or row.get("pageNo")
            or row.get("page_no")
            or idx
        )
        page_label = str(page_value).strip() or str(idx)
        page_blocks.setdefault(page_label, []).append(markdown_text)

    if not page_blocks:
        raise RuntimeError("PaddleOCR-VL API response contained no markdown/text content.")

    ordered_blocks: list[str] = []
    for page_label in sorted(
        page_blocks.keys(),
        key=lambda value: (0, int(value)) if str(value).isdigit() else (1, str(value)),
    ):
        joined = "\n\n".join(
            str(block).strip()
            for block in page_blocks.get(page_label, [])
            if str(block).strip()
        ).strip()
        if not joined:
            continue
        ordered_blocks.append(f"# Page {page_label}\n{joined}")

    if not ordered_blocks:
        raise RuntimeError("PaddleOCR-VL API response contained no markdown/text content.")

    text_path.write_text("\n\n".join(ordered_blocks).strip() + "\n", encoding="utf-8")
    record_trace_event(
        "index.ocr_completed",
        {
            "file_name": file_path.name,
            "pages_processed": len(ordered_blocks),
            "total_layout_results": len(layout_results),
            "markdown_docs": markdown_docs,
            "output_path": str(text_path),
            "api_route": "paddleocr-vl-api",
        },
    )
    debug_rows.append(
        "PaddleOCR-VL API extracted markdown text for "
        f"{markdown_docs}/{len(layout_results)} parsed layout result(s)."
    )
    return text_path, debug_rows


def build_target_uploaded_meta_impl(
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


def preserve_original_pdf_for_indexed_source_impl(
    *,
    index: Any,
    file_id: str,
    source_path: Path,
) -> None:
    if str(source_path.suffix or "").lower() != ".pdf":
        return
    if not source_path.exists() or not source_path.is_file():
        return

    Source = index._resources["Source"]
    fs_path = Path(index._resources["FileStoragePath"])
    with Session(engine) as session:
        source_row = session.execute(select(Source).where(Source.id == file_id)).first()
        if not source_row:
            return
        row = source_row[0]
        stored_name = str(row.path or "").strip()
        if not stored_name:
            return
        stored_path = fs_path / stored_name
        if not stored_path.exists():
            return

        pdf_storage_name = f"{stored_path.name}.pdf"
        pdf_storage_path = stored_path.with_name(pdf_storage_name)
        if not pdf_storage_path.exists():
            try:
                os.link(source_path, pdf_storage_path)
            except Exception:
                shutil.copy2(source_path, pdf_storage_path)

        note = row.note
        if isinstance(note, str):
            try:
                note = json.loads(note)
            except Exception:
                note = {}
        if not isinstance(note, dict):
            note = {}
        note["indexed_text_storage_name"] = stored_path.name
        note["indexed_text_storage_path"] = str(stored_path)
        note["source_original_pdf_storage_name"] = pdf_storage_name
        note["source_original_pdf_storage_path"] = str(pdf_storage_path)
        note["source_original_pdf_name"] = source_path.name
        row.note = note
        row.name = source_path.name
        row.path = pdf_storage_name
        row.size = int(source_path.stat().st_size)
        session.add(row)
        session.commit()

    record_trace_event(
        "index.original_pdf_preserved",
        {
            "file_id": file_id,
            "source_name": source_path.name,
            "pdf_storage_name": pdf_storage_name,
        },
    )


def run_index_pipeline_for_file_impl(
    *,
    index: Any,
    user_id: str,
    source_path: Path,
    target_path: Path,
    reindex: bool,
    base_settings: dict[str, Any],
    prefix: str,
    reader_mode: str,
    uploaded_file_meta: dict[str, dict[str, Any]] | None,
    should_cancel: Callable[[], bool] | None,
    route: str,
    collect_index_stream_fn: Callable[..., tuple[list[str], list[str], list[dict], list[str]]],
    build_target_uploaded_meta_fn: Callable[..., dict[str, dict[str, Any]]],
    upload_index_quick_mode: bool,
) -> dict[str, Any]:
    request_settings = deepcopy(base_settings)
    request_settings[f"{prefix}reader_mode"] = str(reader_mode or "default")
    request_settings.setdefault(f"{prefix}quick_index_mode", upload_index_quick_mode)
    indexing_pipeline = index.get_indexing_pipeline(request_settings, user_id)
    record_trace_event(
        "index.pipeline_prepared",
        {
            "source_name": source_path.name,
            "target_name": target_path.name,
            "reader_mode": str(reader_mode or "default"),
            "route": route,
        },
    )
    effective_meta = build_target_uploaded_meta_fn(
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
    file_ids, errors, items, debug = collect_index_stream_fn(
        stream,
        should_cancel=should_cancel,
    )
    record_trace_event(
        "index.pipeline_completed",
        {
            "source_name": source_path.name,
            "target_name": target_path.name,
            "route": route,
            "file_ids": list(file_ids),
            "error_count": len(errors),
            "item_count": len(items),
        },
    )
    return {
        "file_ids": file_ids,
        "errors": errors,
        "items": items,
        "debug": debug,
    }


def index_pdf_with_paddleocr_route_impl(
    *,
    index: Any,
    user_id: str,
    file_path: Path,
    reindex: bool,
    base_settings: dict[str, Any],
    prefix: str,
    uploaded_file_meta: dict[str, dict[str, Any]] | None,
    should_cancel: Callable[[], bool] | None,
    extract_pdf_text_with_paddleocr_fn: Callable[..., tuple[Path, list[str]]],
    run_index_pipeline_for_file_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    extracted_text_path, route_debug = extract_pdf_text_with_paddleocr_fn(
        file_path=file_path,
        should_cancel=should_cancel,
    )
    record_trace_event(
        "index.ocr_routed_file_ready",
        {
            "file_name": file_path.name,
            "extracted_text_path": str(extracted_text_path),
        },
    )
    try:
        response = run_index_pipeline_for_file_fn(
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
        for file_id in list(response.get("file_ids") or []):
            try:
                preserve_original_pdf_for_indexed_source_impl(
                    index=index,
                    file_id=str(file_id),
                    source_path=file_path,
                )
            except Exception as exc:
                record_trace_event(
                    "index.original_pdf_preserve_failed",
                    {
                        "file_id": str(file_id),
                        "source_name": file_path.name,
                        "error": str(exc),
                    },
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
