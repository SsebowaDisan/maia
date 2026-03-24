import base64
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

from decouple import config
from fsspec import AbstractFileSystem
from llama_index.readers.file import PDFReader
from PIL import Image

from maia.base import Document

PDF_LOADER_DPI = config("PDF_LOADER_DPI", default=40, cast=int)


def _normalize_pdf_unit_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalize_pdf_bbox(
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
    if width < 0.002 or height < 0.002:
        return None
    return {
        "x": round(left, 6),
        "y": round(top, 6),
        "width": round(width, 6),
        "height": round(height, 6),
    }


def _extract_pdf_page_units(file_path: Path) -> dict[str, dict[str, object]]:
    try:
        import fitz
    except ImportError:
        return {}

    doc = fitz.open(file_path)
    page_units: dict[str, dict[str, object]] = {}
    try:
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            page_width = float(page.rect.width or 0.0)
            page_height = float(page.rect.height or 0.0)
            units: list[dict[str, object]] = []
            text_dict = page.get_text("dict")
            for block in list(text_dict.get("blocks") or []):
                if int(block.get("type", 0) or 0) != 0:
                    continue
                for line in list(block.get("lines") or []):
                    spans = list(line.get("spans") or [])
                    line_text = _normalize_pdf_unit_text("".join(str(span.get("text", "") or "") for span in spans))
                    if not line_text:
                        continue
                    bbox = line.get("bbox") or block.get("bbox")
                    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                        continue
                    normalized_box = _normalize_pdf_bbox(
                        x0=float(bbox[0]),
                        y0=float(bbox[1]),
                        x1=float(bbox[2]),
                        y1=float(bbox[3]),
                        page_width=page_width,
                        page_height=page_height,
                    )
                    if not normalized_box:
                        continue
                    units.append(
                        {
                            "text": line_text,
                            "highlight_boxes": [normalized_box],
                        }
                    )
            page_units[str(page_index + 1)] = {
                "page_width": page_width,
                "page_height": page_height,
                "units": units,
            }
    finally:
        doc.close()
    return page_units


def get_page_thumbnails(
    file_path: Path, pages: list[int], dpi: int = PDF_LOADER_DPI
) -> List[Image.Image]:
    """Get image thumbnails of the pages in the PDF file.

    Args:
        file_path (Path): path to the image file
        page_number (list[int]): list of page numbers to extract

    Returns:
        list[Image.Image]: list of page thumbnails
    """

    img: Image.Image
    suffix = file_path.suffix.lower()
    assert suffix == ".pdf", "This function only supports PDF files."
    try:
        import fitz
    except ImportError:
        raise ImportError("Please install PyMuPDF: 'pip install PyMuPDF'")

    doc = fitz.open(file_path)

    output_imgs = []
    for page_number in pages:
        page = doc.load_page(page_number)
        pm = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", [pm.width, pm.height], pm.samples)
        output_imgs.append(convert_image_to_base64(img))

    return output_imgs


def convert_image_to_base64(img: Image.Image) -> str:
    # convert the image into base64
    img_bytes = BytesIO()
    img.save(img_bytes, format="PNG")
    img_base64 = base64.b64encode(img_bytes.getvalue()).decode("utf-8")
    img_base64 = f"data:image/png;base64,{img_base64}"

    return img_base64


class PDFThumbnailReader(PDFReader):
    """PDF parser with thumbnail for each page."""

    def __init__(self) -> None:
        """
        Initialize PDFReader.
        """
        super().__init__(return_full_document=False)

    def load_data(
        self,
        file: Path,
        extra_info: Optional[Dict] = None,
        fs: Optional[AbstractFileSystem] = None,
    ) -> List[Document]:
        """Parse file."""
        documents = super().load_data(file, extra_info, fs)
        page_unit_map = _extract_pdf_page_units(file)

        page_numbers_str = []
        filtered_docs = []
        is_int_page_number: dict[str, bool] = {}

        for doc in documents:
            if "page_label" in doc.metadata:
                page_num_str = doc.metadata["page_label"]
                page_numbers_str.append(page_num_str)
                try:
                    _ = int(page_num_str)
                    is_int_page_number[page_num_str] = True
                    unit_payload = page_unit_map.get(str(page_num_str), {})
                    if unit_payload:
                        if unit_payload.get("units"):
                            doc.metadata["page_units"] = unit_payload.get("units")
                        if unit_payload.get("page_width"):
                            doc.metadata["page_width"] = unit_payload.get("page_width")
                        if unit_payload.get("page_height"):
                            doc.metadata["page_height"] = unit_payload.get("page_height")
                    filtered_docs.append(doc)
                except ValueError:
                    is_int_page_number[page_num_str] = False
                    continue

        documents = filtered_docs
        page_numbers = list(range(len(page_numbers_str)))

        print("Page numbers:", len(page_numbers))
        page_thumbnails = get_page_thumbnails(file, page_numbers)

        documents.extend(
            [
                Document(
                    text="Page thumbnail",
                    metadata={
                        "image_origin": page_thumbnail,
                        "type": "thumbnail",
                        "page_label": page_number,
                        **(extra_info if extra_info is not None else {}),
                    },
                )
                for (page_thumbnail, page_number) in zip(
                    page_thumbnails, page_numbers_str
                )
                if is_int_page_number[page_number]
            ]
        )

        return documents
