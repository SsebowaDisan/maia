import base64
from collections import deque
import logging
import tempfile
from pathlib import Path
from typing import Optional
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from decouple import config

from maia.base import Document

from .base import BaseReader
from .local_ocr_loader import OCRAugmentedPDFReader
from .pdf_loader import PDFThumbnailReader

logger = logging.getLogger(__name__)

JINA_API_KEY = config("JINA_API_KEY", default="")
JINA_URL = config("JINA_URL", default="https://r.jina.ai/")
# 0 means unlimited
WEB_READER_MAX_DEPTH = config("WEB_READER_MAX_DEPTH", default=0, cast=int)
WEB_READER_MAX_PAGES = config("WEB_READER_MAX_PAGES", default=0, cast=int)
WEB_READER_SAME_DOMAIN_ONLY = config(
    "WEB_READER_SAME_DOMAIN_ONLY", default=True, cast=bool
)
WEB_READER_TIMEOUT = config("WEB_READER_TIMEOUT", default=20, cast=int)
WEB_READER_INCLUDE_PDFS = config("WEB_READER_INCLUDE_PDFS", default=True, cast=bool)
WEB_READER_INCLUDE_IMAGES = config(
    "WEB_READER_INCLUDE_IMAGES", default=True, cast=bool
)

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
    ".svg",
}


class WebReader(BaseReader):
    max_depth: int = WEB_READER_MAX_DEPTH
    max_pages: int = WEB_READER_MAX_PAGES
    same_domain_only: bool = WEB_READER_SAME_DOMAIN_ONLY
    request_timeout: int = WEB_READER_TIMEOUT
    include_pdfs: bool = WEB_READER_INCLUDE_PDFS
    include_images: bool = WEB_READER_INCLUDE_IMAGES

    def run(
        self, file_path: str | Path, extra_info: Optional[dict] = None, **kwargs
    ) -> list[Document]:
        return self.load_data(file_path, extra_info=extra_info, **kwargs)

    def _normalize_url(self, url: str) -> str:
        normalized = url.strip()
        if not normalized:
            raise ValueError("Empty URL")

        parsed = urlparse(normalized)
        if not parsed.scheme:
            normalized = f"https://{normalized}"
            parsed = urlparse(normalized)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

        normalized, _ = urldefrag(parsed.geturl())
        return normalized

    def _parse_bool(self, value, fallback: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return fallback

    def fetch_url(self, url: str, timeout: int):
        # Prefer Jina text extraction, then fallback to direct HTTP fetch.
        api_url = f"{JINA_URL.rstrip('/')}/{url}"
        headers = {
            "X-With-Links-Summary": "true",
        }
        if JINA_API_KEY:
            headers["Authorization"] = f"Bearer {JINA_API_KEY}"

        try:
            response = requests.get(api_url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            pass

        direct_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=direct_headers, timeout=timeout)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        if "text/html" in content_type or "application/xhtml+xml" in content_type:
            soup = BeautifulSoup(response.text, "html.parser")
            for element in soup(["script", "style", "noscript"]):
                element.decompose()
            cleaned = soup.get_text(separator="\n", strip=True)
            return cleaned or response.text

        return response.text

    def fetch_binary(self, url: str, timeout: int) -> tuple[bytes, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        return response.content, content_type

    def fetch_html(self, url: str, timeout: int) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            )
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            return ""

        return response.text

    def extract_links(
        self,
        html_content: str,
        current_url: str,
        root_netloc: str,
        same_domain_only: bool,
    ) -> list[str]:
        soup = BeautifulSoup(html_content, "html.parser")
        links: list[str] = []
        seen: set[str] = set()

        def _iter_raw_urls() -> list[str]:
            raw_urls: list[str] = []

            def _collect(attr: str, tags: tuple[str, ...]):
                for tag in tags:
                    for elem in soup.find_all(tag):
                        raw = str(elem.get(attr, "")).strip()
                        if raw:
                            raw_urls.append(raw)

            _collect("href", ("a", "link"))
            _collect("src", ("img", "iframe", "embed", "script", "source"))
            _collect("data", ("object",))

            for elem in soup.find_all(attrs={"srcset": True}):
                srcset = str(elem.get("srcset", "")).strip()
                if not srcset:
                    continue
                for candidate in srcset.split(","):
                    url_part = candidate.strip().split(" ")[0].strip()
                    if url_part:
                        raw_urls.append(url_part)

            return raw_urls

        for href in _iter_raw_urls():
            try:
                absolute_url = self._normalize_url(urljoin(current_url, href))
            except ValueError:
                continue

            parsed = urlparse(absolute_url)
            if same_domain_only and parsed.netloc != root_netloc:
                continue

            if absolute_url in seen:
                continue

            seen.add(absolute_url)
            links.append(absolute_url)

        return links

    def _url_extension(self, url: str) -> str:
        return Path(urlparse(url).path).suffix.lower()

    def _mime_for_image(self, image_url: str, content_type: str) -> str:
        if content_type.startswith("image/"):
            return content_type.split(";")[0]

        ext = self._url_extension(image_url)
        mapping = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
        }
        return mapping.get(ext, "image/png")

    def _get_local_ocr_engine(self):
        if hasattr(self, "_ocr_engine"):
            return getattr(self, "_ocr_engine")
        if hasattr(self, "_ocr_init_error"):
            return None

        try:
            from rapidocr_onnxruntime import RapidOCR

            engine = RapidOCR()
            setattr(self, "_ocr_engine", engine)
            return engine
        except Exception as exc:  # pragma: no cover - dependency dependent
            setattr(self, "_ocr_init_error", exc)
            logger.warning("Web image OCR unavailable: %s", exc)
            return None

    def _ocr_image_bytes(self, image_bytes: bytes) -> str:
        engine = self._get_local_ocr_engine()
        if engine is None:
            return ""
        try:
            result, _elapsed = engine(image_bytes)
        except Exception as exc:  # pragma: no cover - runtime dependent
            logger.warning("Web image OCR failed: %s", exc)
            return ""

        if not result:
            return ""

        lines: list[str] = []
        for item in result:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            text = item[1]
            if not isinstance(text, str):
                continue
            cleaned = " ".join(text.split()).strip()
            if cleaned:
                lines.append(cleaned)

        return "\n".join(lines).strip()

    def extract_pdf_documents(
        self, pdf_bytes: bytes, metadata: dict, timeout: int
    ) -> list[Document]:
        # Use OCR-augmented extraction first, then fallback to plain PDF extraction,
        # and finally Jina text extraction.
        with tempfile.TemporaryDirectory(prefix="maia_web_pdf_") as tmp_dir:
            pdf_path = Path(tmp_dir) / "linked.pdf"
            pdf_path.write_bytes(pdf_bytes)

            try:
                return OCRAugmentedPDFReader().load_data(pdf_path, extra_info=metadata)
            except Exception:
                try:
                    return PDFThumbnailReader().load_data(pdf_path, extra_info=metadata)
                except Exception:
                    pass

        page_url = str(metadata.get("page_url", ""))
        if not page_url:
            return []

        try:
            text = self.fetch_url(page_url, timeout=timeout)
        except requests.RequestException:
            return []

        return [Document(text=text, metadata=metadata)]

    def extract_image_documents(
        self, image_bytes: bytes, image_url: str, metadata: dict, timeout: int, content_type: str
    ) -> list[Document]:
        ocr_text = self._ocr_image_bytes(image_bytes)
        try:
            text = self.fetch_url(image_url, timeout=timeout)
        except requests.RequestException:
            text = ""

        final_text = ocr_text or text or f"Image content from {image_url}"

        mime = self._mime_for_image(image_url, content_type)
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_origin = f"data:{mime};base64,{image_b64}"

        image_metadata = dict(metadata)
        image_metadata["type"] = "image"
        image_metadata["image_origin"] = image_origin
        image_metadata["ocr_applied"] = bool(ocr_text)

        return [
            Document(
                text=final_text,
                metadata=image_metadata,
            )
        ]

    def load_data(
        self, file_path: str | Path, extra_info: Optional[dict] = None, **kwargs
    ) -> list[Document]:
        root_url = self._normalize_url(str(file_path))
        raw_max_depth = int(kwargs.get("max_depth", self.max_depth))
        raw_max_pages = int(kwargs.get("max_pages", self.max_pages))
        max_depth: Optional[int] = raw_max_depth if raw_max_depth > 0 else None
        max_pages: Optional[int] = raw_max_pages if raw_max_pages > 0 else None
        same_domain_only = self._parse_bool(
            kwargs.get("same_domain_only", self.same_domain_only),
            self.same_domain_only,
        )
        include_pdfs = self._parse_bool(
            kwargs.get("include_pdfs", self.include_pdfs),
            self.include_pdfs,
        )
        include_images = self._parse_bool(
            kwargs.get("include_images", self.include_images),
            self.include_images,
        )
        timeout = max(1, int(kwargs.get("request_timeout", self.request_timeout)))

        root_netloc = urlparse(root_url).netloc
        base_metadata = dict(extra_info or {})

        documents: list[Document] = []
        processed_pages = 0
        visited: set[str] = set()
        enqueued: set[str] = {root_url}
        queue: deque[tuple[str, int, Optional[str]]] = deque([(root_url, 0, None)])

        while queue and (max_pages is None or processed_pages < max_pages):
            current_url, depth, parent_url = queue.popleft()
            if current_url in visited:
                continue
            visited.add(current_url)

            metadata = dict(base_metadata)
            metadata["source_url"] = root_url
            metadata["page_url"] = current_url
            metadata["crawl_depth"] = depth
            if parent_url:
                metadata["parent_url"] = parent_url

            ext = self._url_extension(current_url)
            page_documents: list[Document] = []

            try:
                if ext in PDF_EXTENSIONS:
                    if include_pdfs:
                        file_bytes, _ = self.fetch_binary(current_url, timeout=timeout)
                        page_documents = self.extract_pdf_documents(
                            file_bytes, metadata=metadata, timeout=timeout
                        )
                    elif depth == 0:
                        page_text = self.fetch_url(current_url, timeout=timeout)
                        page_documents = [Document(text=page_text, metadata=metadata)]
                    else:
                        continue
                elif ext in IMAGE_EXTENSIONS:
                    if include_images:
                        file_bytes, content_type = self.fetch_binary(
                            current_url, timeout=timeout
                        )
                        page_documents = self.extract_image_documents(
                            image_bytes=file_bytes,
                            image_url=current_url,
                            metadata=metadata,
                            timeout=timeout,
                            content_type=content_type,
                        )
                    elif depth == 0:
                        page_text = self.fetch_url(current_url, timeout=timeout)
                        page_documents = [
                            Document(
                                text=page_text or f"Image content from {current_url}",
                                metadata=metadata,
                            )
                        ]
                    else:
                        continue
                else:
                    page_text = self.fetch_url(current_url, timeout=timeout)
                    page_documents = [Document(text=page_text, metadata=metadata)]
            except requests.RequestException:
                if depth == 0:
                    raise
                continue

            if not page_documents:
                if depth == 0:
                    raise ValueError(f"Unable to extract content from URL: {current_url}")
                continue

            documents.extend(page_documents)
            processed_pages += 1

            if (max_depth is not None and depth >= max_depth) or (
                max_pages is not None and processed_pages >= max_pages
            ):
                continue

            # PDF and image links are terminal nodes in the crawl graph.
            if ext in PDF_EXTENSIONS or ext in IMAGE_EXTENSIONS:
                continue

            try:
                html_content = self.fetch_html(current_url, timeout=timeout)
            except requests.RequestException:
                continue

            if not html_content:
                continue

            for link in self.extract_links(
                html_content=html_content,
                current_url=current_url,
                root_netloc=root_netloc,
                same_domain_only=same_domain_only,
            ):
                if link in visited or link in enqueued:
                    continue
                queue.append((link, depth + 1, current_url))
                enqueued.add(link)

        return documents
