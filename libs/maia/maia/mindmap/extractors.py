from __future__ import annotations

import re
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone
from hashlib import sha1
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

try:
    from pypdf import PdfReader  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None


MAX_DEFAULT_NODES = 260
_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(seed: str, prefix: str = "node") -> str:
    return f"{prefix}_{sha1(seed.encode('utf-8')).hexdigest()[:14]}"


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def truncate(text: str, limit: int = 320) -> str:
    value = clean_text(text)
    if len(value) <= limit:
        return value
    clipped = value[:limit]
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.strip()


def tokenize(text: str) -> set[str]:
    lowered = clean_text(text).lower()
    return {token for token in _TOKEN_RE.findall(lowered) if len(token) >= 3}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return float(len(left & right)) / float(len(union))


def first_sentences(text: str, limit: int = 2) -> list[str]:
    rows = [row.strip() for row in _SENTENCE_SPLIT_RE.split(clean_text(text)) if row.strip()]
    return rows[: max(1, limit)]


def coerce_page_label(value: Any) -> str:
    raw = clean_text(value)
    if not raw:
        return ""
    matched = re.search(r"\d{1,5}", raw)
    return matched.group(0) if matched else raw[:24]


def sort_page_key(label: str) -> tuple[int, str]:
    if label.isdigit():
        return (int(label), label)
    matched = re.search(r"\d{1,5}", label)
    if matched:
        return (int(matched.group(0)), label)
    return (10**9, label)


def normalize_records(documents: list[Any] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(documents or []):
        metadata: dict[str, Any] = {}
        text = ""
        doc_id = f"doc_{index + 1}"
        if isinstance(row, dict):
            metadata = dict(row.get("metadata", {}) or {})
            text = str(row.get("text", "") or "")
            doc_id = str(row.get("doc_id", "") or doc_id)
            if not metadata:
                metadata = dict(row)
        else:
            metadata = dict(getattr(row, "metadata", {}) or {})
            text = str(getattr(row, "text", "") or "")
            doc_id = str(getattr(row, "doc_id", "") or doc_id)
        source_name = clean_text(
            metadata.get("source_name")
            or metadata.get("file_name")
            or metadata.get("url")
            or ""
        )
        source_id = clean_text(metadata.get("source_id") or "")
        if not source_id:
            source_id = stable_id(source_name or doc_id, prefix="src")
        page_label = coerce_page_label(metadata.get("page_label"))
        media_type = clean_text(metadata.get("type") or metadata.get("doc_type") or "").lower()
        normalized.append(
            {
                "doc_id": doc_id,
                "source_id": source_id,
                "source_name": source_name or "Indexed source",
                "page_label": page_label,
                "text": clean_text(text),
                "unit_id": clean_text(metadata.get("unit_id") or ""),
                "url": clean_text(metadata.get("url") or source_name if source_name.startswith("http") else ""),
                "media_type": media_type,
                "image_origin": metadata.get("image_origin"),
                "links": metadata.get("links") or metadata.get("out_links") or metadata.get("outbound_links") or [],
                "metadata": metadata,
            }
        )
    return normalized


def heading_level(line: str) -> int | None:
    text = line.strip()
    if not text:
        return None
    markdown = re.match(r"^(#{1,6})\s+.+$", text)
    if markdown:
        return min(6, len(markdown.group(1)))
    numbered = re.match(r"^(\d+(?:\.\d+){0,4})\s+[A-Za-z].*$", text)
    if numbered:
        return min(6, numbered.group(1).count(".") + 1)
    if text.endswith(":") and len(text.split()) <= 12:
        return 2
    if len(text) <= 70 and re.match(r"^[A-Z][A-Z0-9\s,&/-]{4,}$", text):
        return 1
    return None


def extract_page_outline(text: str, max_depth: int) -> list[dict[str, Any]]:
    lines = [line.strip() for line in str(text or "").splitlines()]
    rows: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for line in lines:
        if not line or len(line) > 180:
            continue
        level = heading_level(line)
        if level is None:
            bullet_match = re.match(r"^[-*]\s+(.+)$", line)
            if bullet_match:
                label = truncate(bullet_match.group(1), 120)
                key = f"b:{label.lower()}"
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                rows.append({"kind": "bullet", "level": min(max_depth, 5), "title": label})
            continue
        title = truncate(re.sub(r"^#{1,6}\s*", "", line), 120)
        key = f"h:{title.lower()}"
        if key in seen_titles:
            continue
        seen_titles.add(key)
        rows.append({"kind": "heading", "level": max(1, min(max_depth, level)), "title": title})
    return rows[:48]


def extract_multimodal_nodes(
    rows: list[Any],
    *,
    max_nodes: int = 24,
) -> list[dict[str, Any]]:
    records = normalize_records(rows)
    multimodal: list[dict[str, Any]] = []
    for row in records:
        media_type = str(row.get("media_type", "")).lower()
        if media_type not in {"image", "table", "chart", "figure", "thumbnail"}:
            continue
        title = row.get("source_name") or "Asset"
        page = row.get("page_label", "")
        if page:
            title = f"{title} - page {page}"
        multimodal.append(
            {
                "id": stable_id(f"{row.get('source_id')}|{row.get('doc_id')}|{media_type}", prefix="asset"),
                "title": truncate(str(title), 120),
                "text": truncate(row.get("text", ""), 240),
                "page_ref": page or None,
                "node_type": media_type,
                "thumbnail": row.get("image_origin") if isinstance(row.get("image_origin"), str) else None,
                "source_id": row.get("source_id", ""),
                "source_name": row.get("source_name", ""),
                "children": [],
                "related": [],
            }
        )
        if len(multimodal) >= max_nodes:
            break
    return multimodal


def parse_pdf_to_tree(
    pdf_file: str | Path,
    *,
    max_depth: int = 4,
    node_limit: int = MAX_DEFAULT_NODES,
) -> dict[str, Any]:
    from .indexer import build_knowledge_map  # avoid cycle at import time

    file_path = Path(pdf_file)
    if not file_path.exists():
        return {
            "version": 1,
            "kind": "tree",
            "title": f"PDF map: {file_path.name}",
            "root_id": "",
            "nodes": [],
            "edges": [],
            "error": f"File does not exist: {file_path}",
            "created_at": utc_now_iso(),
        }
    if PdfReader is None:
        return {
            "version": 1,
            "kind": "tree",
            "title": f"PDF map: {file_path.name}",
            "root_id": "",
            "nodes": [],
            "edges": [],
            "error": "pypdf is unavailable in this runtime.",
            "created_at": utc_now_iso(),
        }

    reader = PdfReader(str(file_path))
    docs: list[dict[str, Any]] = []
    for idx, page in enumerate(reader.pages):
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        docs.append(
            {
                "doc_id": f"pdf-page-{idx + 1}",
                "text": page_text,
                "metadata": {
                    "source_id": stable_id(str(file_path.resolve()), prefix="src"),
                    "source_name": file_path.name,
                    "file_name": file_path.name,
                    "page_label": str(idx + 1),
                    "type": "text",
                },
            }
        )
    return build_knowledge_map(
        question="",
        context="",
        documents=docs,
        answer_text="",
        max_depth=max_depth,
        include_reasoning_map=False,
        source_type_hint="pdf",
        node_limit=node_limit,
    )


class _SimpleHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.title_parts: list[str] = []
        self.headings: list[str] = []
        self.links: list[str] = []
        self._current_heading: list[str] = []
        self._heading_tag = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        if tag_l == "title":
            self.in_title = True
        if tag_l in {"h1", "h2", "h3"}:
            self._heading_tag = tag_l
            self._current_heading = []
        if tag_l == "a":
            href = dict(attrs).get("href") or ""
            href = href.strip()
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l == "title":
            self.in_title = False
        if self._heading_tag and tag_l == self._heading_tag:
            heading = clean_text(" ".join(self._current_heading))
            if heading:
                self.headings.append(heading)
            self._heading_tag = ""
            self._current_heading = []

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self._heading_tag:
            self._current_heading.append(data)


def crawl_website_to_graph(
    url: str,
    *,
    max_pages: int = 8,
    same_domain_only: bool = True,
    timeout_seconds: int = 8,
) -> dict[str, Any]:
    start_url = clean_text(url)
    parsed = urllib.parse.urlparse(start_url)
    base_domain = parsed.netloc.lower()
    if not parsed.scheme:
        start_url = f"https://{start_url}"
        parsed = urllib.parse.urlparse(start_url)
        base_domain = parsed.netloc.lower()

    queue: deque[str] = deque([start_url])
    visited: set[str] = set()
    pages: list[dict[str, Any]] = []
    link_edges: list[tuple[str, str]] = []

    while queue and len(visited) < max(1, max_pages):
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        try:
            request = urllib.request.Request(current, headers={"User-Agent": "maia-mindmap/1.0"})
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="ignore")
        except Exception:
            continue

        parser = _SimpleHtmlParser()
        try:
            parser.feed(body)
        except Exception:
            pass

        page_title = clean_text(" ".join(parser.title_parts)) or clean_text(current)
        page_id = stable_id(current, prefix="page")
        pages.append(
            {
                "id": page_id,
                "url": current,
                "title": truncate(page_title, 120),
                "headings": parser.headings[:12],
                "text": truncate(" | ".join(parser.headings[:8]), 280),
            }
        )

        for href in parser.links[:80]:
            resolved = urllib.parse.urljoin(current, href)
            resolved_parsed = urllib.parse.urlparse(resolved)
            if resolved_parsed.scheme not in {"http", "https"}:
                continue
            if same_domain_only and resolved_parsed.netloc.lower() != base_domain:
                continue
            normalized = resolved.split("#", 1)[0].rstrip("/")
            if not normalized:
                continue
            link_edges.append((current.rstrip("/"), normalized))
            if normalized not in visited and normalized not in queue and len(visited) + len(queue) < max_pages * 2:
                queue.append(normalized)

    url_to_node = {row["url"].rstrip("/"): row["id"] for row in pages}
    nodes = [
        {
            "id": row["id"],
            "title": row["title"],
            "text": row["text"],
            "source_id": row["id"],
            "source_name": row["url"],
            "node_type": "web_page",
            "children": [],
            "related": [],
        }
        for row in pages
    ]
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str]] = set()
    for left_url, right_url in link_edges:
        left_id = url_to_node.get(left_url)
        right_id = url_to_node.get(right_url)
        if not left_id or not right_id or left_id == right_id:
            continue
        pair = (left_id, right_id)
        if pair in seen_edges:
            continue
        seen_edges.add(pair)
        edges.append(
            {
                "id": stable_id(f"{left_id}->{right_id}", prefix="edge"),
                "source": left_id,
                "target": right_id,
                "type": "hyperlink",
            }
        )

    return {
        "version": 1,
        "kind": "graph",
        "title": f"Website graph: {parsed.netloc or start_url}",
        "root_id": nodes[0]["id"] if nodes else "",
        "nodes": nodes,
        "edges": edges,
        "created_at": utc_now_iso(),
    }


def group_records_by_source(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[str(row.get("source_id", ""))].append(row)
    return grouped

