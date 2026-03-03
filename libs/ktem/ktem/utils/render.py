import os
import json
from html import escape

import markdown
from fast_langdetect import detect

from maia.base import RetrievedDocument
from maia.indices.qa.highlight_boxes import (
    extract_highlight_boxes_from_metadata,
    merge_adjacent_highlight_boxes,
    normalize_highlight_boxes,
)

BASE_PATH = os.environ.get("GR_FILE_ROOT_PATH", "")


def is_close(val1, val2, tolerance=1e-9):
    return abs(val1 - val2) <= tolerance


def replace_mardown_header(text: str) -> str:
    textlines = text.splitlines()
    newlines = []
    for line in textlines:
        if line.startswith("#"):
            line = "<strong>" + line.replace("#", "") + "</strong>"
        if line.startswith("=="):
            line = ""
        newlines.append(line)

    return "\n".join(newlines)


def get_header(doc: RetrievedDocument) -> str:
    """Get the header for the document"""
    header = ""
    if "page_label" in doc.metadata:
        header += f" [Page {doc.metadata['page_label']}]"

    header += f" {doc.metadata.get('file_name', '<evidence>')}"
    return header.strip()


class Render:
    """Default text rendering into HTML for the UI"""

    @staticmethod
    def collapsible(header, content, open: bool = False) -> str:
        """Render an HTML friendly collapsible section"""
        o = " open" if open else ""
        return (
            f"<details class='evidence' {o}><summary>"
            f"{header}</summary>{content}"
            "</details><br>"
        )

    @staticmethod
    def table(text: str) -> str:
        """Render table from markdown format into HTML"""
        text = replace_mardown_header(text)
        return markdown.markdown(
            text,
            extensions=[
                "markdown.extensions.tables",
                "markdown.extensions.fenced_code",
            ],
        )

    @staticmethod
    def table_preserve_linebreaks(text: str) -> str:
        """Render table from markdown format into HTML"""
        return markdown.markdown(
            text,
            extensions=[
                "markdown.extensions.tables",
                "markdown.extensions.fenced_code",
            ],
        ).replace("\n", "<br>")

    @staticmethod
    def preview(
        html_content: str,
        doc: RetrievedDocument,
        highlight_text: str | None = None,
        highlight_boxes: list[dict[str, float]] | None = None,
    ) -> str:
        text = doc.content
        pdf_path = doc.metadata.get("file_path", "")

        if not os.path.isfile(pdf_path):
            print(f"pdf-path: {pdf_path} does not exist")
            return html_content

        is_pdf = doc.metadata.get("file_type", "") == "application/pdf"
        page_idx = int(doc.metadata.get("page_label", 1))

        if not is_pdf:
            print("Document is not pdf")
            return html_content

        if page_idx < 0:
            print("Fail to extract page number")
            return html_content

        resolved_boxes = normalize_highlight_boxes(highlight_boxes or [])
        if not resolved_boxes:
            resolved_boxes = merge_adjacent_highlight_boxes(
                extract_highlight_boxes_from_metadata(doc.metadata or {})
            )

        phrase = "true"
        if not highlight_text:
            try:
                detection = detect(text.replace("\n", " "))
                lang = ""
                if isinstance(detection, dict):
                    lang = str(detection.get("lang") or "").strip().lower()
                elif isinstance(detection, list) and detection:
                    first = detection[0]
                    if isinstance(first, dict):
                        lang = str(first.get("lang") or "").strip().lower()
                phrase = "false" if lang in {"ja", "cn", "zh"} else "true"
            except Exception as exc:
                print(exc)
                phrase = "true"

            text_lines = [line.strip() for line in str(text).splitlines() if line.strip()]
            if phrase == "true":
                highlight_text = text_lines[0] if text_lines else str(text).strip()
            else:
                joined = " ".join(text_lines) if text_lines else str(text).strip()
                highlight_text = joined[:120]

        safe_pdf_src = escape(f"{BASE_PATH}/file={pdf_path}", quote=True)
        safe_search = escape(str(highlight_text or "").replace("\n", " "), quote=True)
        if len(safe_search) > 360:
            safe_search = safe_search[:360]

        if resolved_boxes:
            payload = json.dumps(resolved_boxes, ensure_ascii=True, separators=(",", ":"))
            safe_boxes = escape(payload, quote=True)
            return f"""
            {html_content}
            <a href="#" class="pdf-link" data-src="{safe_pdf_src}" data-page="{page_idx}" data-search="{safe_search}" data-boxes="{safe_boxes}" data-bboxes="{safe_boxes}" data-phrase="{phrase}">
                See in PDF
            </a>
            """  # noqa

        return f"""
        {html_content}
        <a href="#" class="pdf-link" data-src="{safe_pdf_src}" data-page="{page_idx}" data-search="{safe_search}" data-phrase="{phrase}">
            See in PDF
        </a>
        """  # noqa

    @staticmethod
    def highlight(text: str, elem_id: str | None = None) -> str:
        """Highlight text"""
        id_text = f" id='mark-{elem_id}'" if elem_id else ""
        return f"<mark{id_text}>{text}</mark>"

    @staticmethod
    def image(url: str, text: str = "") -> str:
        """Render an image"""
        img = f'<img src="{url}"><br>'
        if text:
            caption = f"<p>{text}</p>"
            return f"<figure>{img}{caption}</figure><br>"
        return img

    @staticmethod
    def collapsible_with_header(
        doc: RetrievedDocument,
        open_collapsible: bool = False,
    ) -> str:
        header = f"<i>{get_header(doc)}</i>"
        if doc.metadata.get("type", "") == "image":
            doc_content = Render.image(url=doc.metadata["image_origin"], text=doc.text)
        elif doc.metadata.get("type", "") == "table_raw":
            doc_content = Render.table_preserve_linebreaks(doc.text)
        else:
            doc_content = Render.table(doc.text)

        return Render.collapsible(
            header=Render.preview(header, doc),
            content=doc_content,
            open=open_collapsible,
        )

    @staticmethod
    def collapsible_with_header_score(
        doc: RetrievedDocument,
        override_text: str | None = None,
        highlight_text: str | None = None,
        highlight_boxes: list[dict[str, float]] | None = None,
        open_collapsible: bool = False,
    ) -> str:
        """Format the retrieval score and the document"""
        # score from doc_store (Elasticsearch)
        if is_close(doc.score, -1.0):
            vectorstore_score = ""
            text_search_str = " (full-text search)<br>"
        else:
            vectorstore_score = str(round(doc.score, 2))
            text_search_str = "<br>"

        llm_reranking_score = (
            round(doc.metadata["llm_trulens_score"], 2)
            if doc.metadata.get("llm_trulens_score") is not None
            else 0.0
        )
        reranking_score = (
            round(doc.metadata["reranking_score"], 2)
            if doc.metadata.get("reranking_score") is not None
            else 0.0
        )
        item_type_prefix = doc.metadata.get("type", "")
        item_type_prefix = item_type_prefix.capitalize()
        if item_type_prefix:
            item_type_prefix += " from "

        if "raw" in item_type_prefix:
            item_type_prefix = ""

        if llm_reranking_score > 0:
            relevant_score = llm_reranking_score
        elif reranking_score > 0:
            relevant_score = reranking_score
        else:
            relevant_score = 0.0

        rendered_score = Render.collapsible(
            header=f"<b>&emsp;Relevance score</b>: {relevant_score:.1f}",
            content="<b>&emsp;&emsp;Vectorstore score:</b>"
            f" {vectorstore_score}"
            f"{text_search_str}"
            "<b>&emsp;&emsp;LLM relevant score:</b>"
            f" {llm_reranking_score}<br>"
            "<b>&emsp;&emsp;Reranking score:</b>"
            f" {reranking_score}<br>",
        )

        text = doc.text if not override_text else override_text
        if doc.metadata.get("type", "") == "image":
            rendered_doc_content = Render.image(
                url=doc.metadata["image_origin"],
                text=text,
            )
        elif doc.metadata.get("type", "") == "table_raw":
            rendered_doc_content = Render.table_preserve_linebreaks(doc.text)
        else:
            rendered_doc_content = Render.table(text)

        rendered_header = Render.preview(
            f"<i>{item_type_prefix}{get_header(doc)}</i>"
            f" [score: {llm_reranking_score}]",
            doc,
            highlight_text=highlight_text,
            highlight_boxes=highlight_boxes,
        )
        rendered_doc_content = (
            f"<div class='evidence-content'>{rendered_doc_content}</div>"
        )

        return Render.collapsible(
            header=rendered_header,
            content=rendered_score + rendered_doc_content,
            open=open_collapsible,
        )
