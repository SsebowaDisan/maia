import re
from pathlib import Path
from typing import Optional

from maia.base import Document
from api.services.observability.citation_trace import record_trace_event

from .base import BaseReader


_PAGE_BLOCK_RE = re.compile(
    r"(?ms)^\#\s*(?:Page|Layout Result)\s+(\d+)\s*$\n?(.*?)(?=^\#\s*(?:Page|Layout Result)\s+\d+\s*$|\Z)"
)


def _should_split_ocr_page_blocks(*, file_path: Path, metadata: dict) -> bool:
    route = str(metadata.get("ingestion_route") or "").strip().lower()
    original_name = str(metadata.get("source_original_name") or "").strip().lower()
    if route == "heavy-pdf-paddleocr":
        return True
    if file_path.suffix.lower() in {".txt", ".md"} and original_name.endswith(".pdf"):
        return True
    return False


def _load_page_block_documents(text: str, metadata: dict) -> list[Document]:
    matches = list(_PAGE_BLOCK_RE.finditer(text))
    if len(matches) < 2:
        return []

    docs: list[Document] = []
    for match in matches:
        page_label = str(match.group(1) or "").strip()
        body = str(match.group(2) or "").strip()
        if not body:
            continue
        page_metadata = dict(metadata)
        page_metadata["page_label"] = page_label
        docs.append(Document(text=body, metadata=page_metadata))
    return docs


class TxtReader(BaseReader):
    def run(
        self, file_path: str | Path, extra_info: Optional[dict] = None, **kwargs
    ) -> list[Document]:
        return self.load_data(Path(file_path), extra_info=extra_info, **kwargs)

    def load_data(
        self, file_path: Path, extra_info: Optional[dict] = None, **kwargs
    ) -> list[Document]:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()

        metadata = dict(extra_info or {})
        if _should_split_ocr_page_blocks(file_path=file_path, metadata=metadata):
            page_docs = _load_page_block_documents(text, metadata)
            if page_docs:
                record_trace_event(
                    "index.ocr_page_blocks_split",
                    {
                        "file_name": file_path.name,
                        "page_doc_count": len(page_docs),
                        "source_original_name": str(metadata.get("source_original_name") or ""),
                    },
                )
                return page_docs

        return [Document(text=text, metadata=metadata)]
