from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from fsspec import AbstractFileSystem

from maia.base import Document

from .pdf_loader import PDFThumbnailReader

logger = logging.getLogger(__name__)


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip().lower()


def _join_ocr_lines(ocr_result: Optional[list]) -> str:
    if not ocr_result:
        return ""

    lines: list[str] = []
    for item in ocr_result:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        text = item[1]
        if not isinstance(text, str):
            continue
        cleaned = " ".join(text.split()).strip()
        if cleaned:
            lines.append(cleaned)

    return "\n".join(lines).strip()


class RapidOCRMixin:
    """Shared local OCR engine helpers."""

    def __init__(self) -> None:
        self._ocr_engine = None
        self._ocr_init_error: Exception | None = None
        super().__init__()

    def _get_ocr_engine(self):
        if self._ocr_engine is not None:
            return self._ocr_engine
        if self._ocr_init_error is not None:
            return None

        try:
            from rapidocr_onnxruntime import RapidOCR

            self._ocr_engine = RapidOCR()
        except Exception as exc:  # pragma: no cover - environment dependent
            self._ocr_init_error = exc
            logger.warning("Local OCR engine unavailable: %s", exc)
            return None

        return self._ocr_engine

    def _extract_text(self, image_input: str | Path | bytes) -> str:
        engine = self._get_ocr_engine()
        if engine is None:
            return ""

        try:
            ocr_result, _elapsed = engine(image_input)
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.warning("Local OCR failed: %s", exc)
            return ""

        return _join_ocr_lines(ocr_result)


class OCRImageReader(RapidOCRMixin):
    """Local OCR for image files."""

    def __init__(self) -> None:
        super().__init__()

    def load_data(
        self,
        file: Path,
        extra_info: Optional[Dict] = None,
        fs: Optional[AbstractFileSystem] = None,
    ) -> List[Document]:
        file_path = Path(file)
        metadata = dict(extra_info or {})

        image_bytes: bytes | None = None
        if fs:
            with fs.open(path=file_path) as f:
                image_bytes = f.read()

        text = self._extract_text(image_bytes if image_bytes is not None else file_path)
        if not text:
            # Keep a lightweight placeholder so file attachment still appears in context.
            text = f"OCR found no readable text in image: {file_path.name}"

        metadata.setdefault("type", "image")
        metadata.setdefault("file_name", file_path.name)
        return [Document(text=text, metadata=metadata)]

    def run(self, file: Path, **kwargs) -> List[Document]:
        return self.load_data(file=file, **kwargs)


class OCRAugmentedPDFReader(PDFThumbnailReader, RapidOCRMixin):
    """PDF reader that keeps normal extraction and adds per-page local OCR text."""

    def __init__(self, ocr_dpi: int = 220) -> None:
        self.ocr_dpi = max(120, int(ocr_dpi))
        PDFThumbnailReader.__init__(self)
        RapidOCRMixin.__init__(self)

    def _page_ocr_documents(
        self, file_path: Path, extra_info: Optional[dict] = None
    ) -> list[Document]:
        engine = self._get_ocr_engine()
        if engine is None:
            return []

        try:
            import fitz
        except Exception as exc:  # pragma: no cover - dependency dependent
            logger.warning("PyMuPDF unavailable for OCR-augmented PDF parsing: %s", exc)
            return []

        docs: list[Document] = []
        metadata_base = dict(extra_info or {})
        pdf_doc = fitz.open(file_path)
        try:
            for page_index in range(pdf_doc.page_count):
                page = pdf_doc.load_page(page_index)
                pixmap = page.get_pixmap(dpi=self.ocr_dpi)
                page_png = pixmap.tobytes("png")
                ocr_text = self._extract_text(page_png)
                if not ocr_text:
                    continue
                page_label = str(page_index + 1)
                docs.append(
                    Document(
                        text=ocr_text,
                        metadata={
                            **metadata_base,
                            "type": "ocr",
                            "page_label": page_label,
                        },
                    )
                )
        finally:
            pdf_doc.close()

        return docs

    def load_data(
        self,
        file: Path,
        extra_info: Optional[Dict] = None,
        fs: Optional[AbstractFileSystem] = None,
    ) -> List[Document]:
        base_docs = super().load_data(file=file, extra_info=extra_info, fs=fs)
        ocr_docs = self._page_ocr_documents(Path(file), extra_info=extra_info)
        if not ocr_docs:
            return base_docs

        existing_page_text: dict[str, str] = {}
        for doc in base_docs:
            metadata = doc.metadata or {}
            if metadata.get("type") == "thumbnail":
                continue
            page_label = str(metadata.get("page_label", "")).strip()
            if not page_label:
                continue
            existing_page_text[page_label] = (
                f"{existing_page_text.get(page_label, '')}\n{doc.text or ''}".strip()
            )

        filtered_ocr_docs: list[Document] = []
        for ocr_doc in ocr_docs:
            page_label = str((ocr_doc.metadata or {}).get("page_label", "")).strip()
            ocr_norm = _normalize_text(ocr_doc.text or "")
            existing_norm = _normalize_text(existing_page_text.get(page_label, ""))
            if not ocr_norm:
                continue
            if existing_norm and ocr_norm in existing_norm:
                continue
            filtered_ocr_docs.append(ocr_doc)

        return base_docs + filtered_ocr_docs

