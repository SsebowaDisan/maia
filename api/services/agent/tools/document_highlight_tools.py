from __future__ import annotations

from typing import Any

from api.services.agent.models import AgentSource
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.document_highlight_helpers import (
    _as_bounded_int,
    _build_highlights,
    _build_pdf_scan_steps,
    _deep_file_source_summaries,
    _document_scene_payload,
    _extract_terms,
    _load_source_chunks,
    _normalize_color,
    _normalize_file_ids,
    _page_number_from_label,
    _pdf_scene_payload,
    _safe_snippet,
)

class DocumentHighlightExtractTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="documents.highlight.extract",
        action_class="read",
        risk_level="low",
        required_permissions=["data.read"],
        execution_policy="auto_execute",
        description="Highlight and copy matching words from selected indexed files.",
    )

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        selected_file_ids = _normalize_file_ids(context.settings.get("__selected_file_ids"))
        index_id_raw = context.settings.get("__selected_index_id")
        index_id = int(index_id_raw) if isinstance(index_id_raw, int) or str(index_id_raw).isdigit() else None
        depth_tier = str(
            params.get("research_depth_tier")
            or context.settings.get("__research_depth_tier")
            or "standard"
        ).strip().lower()
        research_topic = " ".join(str(prompt or "").split()).strip()[:280]
        highlight_color = _normalize_color(params.get("highlight_color") or context.settings.get("__highlight_color"))
        max_sources = _as_bounded_int(
            params.get("max_sources") or context.settings.get("__file_research_max_sources"),
            default=8,
            low=1,
            high=240,
        )
        max_chunks = _as_bounded_int(
            params.get("max_chunks") or context.settings.get("__file_research_max_chunks"),
            default=28,
            low=20,
            high=3000,
        )
        max_scan_pages = _as_bounded_int(
            params.get("max_scan_pages") or context.settings.get("__file_research_max_scan_pages"),
            default=8,
            low=8,
            high=300,
        )
        max_highlights = _as_bounded_int(
            params.get("max_highlights"),
            default=96 if max_sources >= 80 else 36,
            low=12,
            high=220,
        )
        prefer_pdf_only = bool(
            params.get("prefer_pdf")
            if params.get("prefer_pdf") is not None
            else context.settings.get("__file_research_prefer_pdf", True)
        )

        chunks = _load_source_chunks(
            user_id=context.user_id,
            file_ids=selected_file_ids,
            index_id=index_id,
            max_sources=max_sources,
            max_chunks=max_chunks,
            prefer_pdf=prefer_pdf_only,
        )
        if not chunks:
            return ToolExecutionResult(
                summary="No readable file content available for highlighting.",
                content=(
                    "Unable to scan selected files for highlights.\n"
                    "- Select one or more indexed files, then rerun highlight extraction."
                ),
                data={"highlight_color": highlight_color, "highlighted_words": [], "copied_snippets": []},
                sources=[],
                next_steps=[],
                events=[
                    ToolTraceEvent(
                        event_type="document_opened",
                        title="Open selected files",
                        detail="No selected file content was available",
                        data=_document_scene_payload(
                            lane="document-open-empty",
                            payload={
                                "chunk_count": 0,
                                "source_count": 0,
                            },
                        ),
                    )
                ],
            )

        terms = _extract_terms(prompt, params, chunks)
        highlights = _build_highlights(
            chunks=chunks,
            terms=terms,
            color=highlight_color,
            max_items=max_highlights,
        )
        if not highlights and chunks:
            fallback_terms = _extract_terms("", {}, chunks)
            highlights = _build_highlights(
                chunks=chunks,
                terms=fallback_terms,
                color=highlight_color,
                max_items=max_highlights,
            )
            if fallback_terms:
                terms = fallback_terms

        copied_snippets = [row["snippet"] for row in highlights[:10] if row.get("snippet")]
        copied_bucket = context.settings.get("__copied_highlights")
        if not isinstance(copied_bucket, list):
            copied_bucket = []
        copy_limit = min(max_highlights, 180)
        for row in highlights[:copy_limit]:
            copied_bucket.append(
                {
                    "source": "file",
                    "color": row.get("color") or highlight_color,
                    "word": row.get("word") or "",
                    "text": row.get("snippet") or "",
                    "reference": row.get("source_name") or "Indexed file",
                    "page_label": row.get("page_label") or "",
                }
            )
        copied_cap = 400 if max_sources >= 80 else 120
        context.settings["__copied_highlights"] = copied_bucket[-copied_cap:]
        context.settings["__highlight_color"] = highlight_color

        source_summary_by_id: dict[str, dict[str, Any]] = {}
        for row in highlights:
            source_id = str(row.get("source_id") or "")
            if not source_id:
                continue
            source_name = str(row.get("source_name") or "Indexed file")
            page_label = str(row.get("page_label") or "")
            snippet = _safe_snippet(str(row.get("snippet") or ""), limit=280)
            keyword = str(row.get("word") or "").strip().lower()
            summary = source_summary_by_id.setdefault(
                source_id,
                {
                    "source_name": source_name,
                    "page_label": page_label,
                    "extract": snippet,
                    "keywords": [],
                    "highlight_count": 0,
                },
            )
            if not summary.get("page_label") and page_label:
                summary["page_label"] = page_label
            if not summary.get("extract") and snippet:
                summary["extract"] = snippet
            if keyword:
                keywords = summary.get("keywords")
                if not isinstance(keywords, list):
                    keywords = []
                    summary["keywords"] = keywords
                if keyword not in keywords and len(keywords) < 12:
                    keywords.append(keyword)
            summary["highlight_count"] = int(summary.get("highlight_count") or 0) + 1

        # Group all loaded chunks by source_id for per-file LLM synthesis.
        chunks_by_source: dict[str, list[dict[str, Any]]] = {}
        for chunk in chunks:
            sid = str(chunk.get("source_id") or "").strip()
            if sid:
                chunks_by_source.setdefault(sid, []).append(chunk)

        # For deep-research tiers, synthesize each file's key findings with LLM.
        file_syntheses = _deep_file_source_summaries(
            chunks_by_source,
            topic=research_topic,
            depth_tier=depth_tier,
        )

        # Compute total highlight count for proportional relevance scoring.
        total_highlights = max(1, sum(
            int(s.get("highlight_count") or 0)
            for s in source_summary_by_id.values()
        ))

        source_by_id: dict[str, AgentSource] = {}
        for source_id, summary in source_summary_by_id.items():
            highlight_count = int(summary.get("highlight_count") or 0)
            # Proportional relevance: 0.55 base + up to 0.40 from match density.
            relevance_score = round(
                min(0.95, 0.55 + 0.40 * (highlight_count / total_highlights)), 4
            )
            # Use LLM synthesis if available, else fall back to keyword snippet.
            extract_text = file_syntheses.get(source_id) or str(summary.get("extract") or "").strip()
            source_by_id[source_id] = AgentSource(
                source_type="file",
                label=str(summary.get("source_name") or "Indexed file"),
                file_id=source_id,
                score=relevance_score,
                metadata={
                    "page_label": str(summary.get("page_label") or ""),
                    "extract": extract_text,
                    "excerpt": extract_text,
                    "snippet": extract_text,
                    "keywords": list(summary.get("keywords") or [])[:12],
                    "highlight_count": highlight_count,
                },
            )

        highlighted_words = [row.get("word", "") for row in highlights if row.get("word")]
        unique_words = list(dict.fromkeys(highlighted_words))
        pdf_scan_steps = _build_pdf_scan_steps(
            chunks=chunks,
            highlights=highlights,
            max_pages=max_scan_pages,
        )
        unique_sources = {
            str(row.get("source_id") or "").strip()
            for row in chunks
            if str(row.get("source_id") or "").strip()
        }
        has_pdf_file = any(
            str(row.get("source_name") or "").strip().lower().endswith(".pdf")
            for row in chunks
            if isinstance(row, dict)
        )
        is_pdf_scan = bool(pdf_scan_steps) and (
            has_pdf_file
            or any(str(row.get("page_label") or "").strip() for row in pdf_scan_steps)
        )

        events: list[ToolTraceEvent] = [
            ToolTraceEvent(
                event_type="document_opened",
                title="Open selected files",
                detail=f"Scanning {len(chunks)} file excerpt(s)",
                data=_document_scene_payload(
                    lane="document-open",
                    payload={
                        "chunk_count": len(chunks),
                        "source_count": len(unique_sources),
                    },
                ),
            ),
        ]
        if is_pdf_scan and pdf_scan_steps:
            first_step = pdf_scan_steps[0]
            events.append(
                ToolTraceEvent(
                    event_type="pdf_open",
                    title="Open PDF preview",
                    detail=str(first_step.get("source_name") or "Indexed PDF"),
                    data=_pdf_scene_payload(
                        lane="pdf-open",
                        page_index=int(first_step.get("page_index") or 1),
                        page_total=int(first_step.get("page_total") or len(pdf_scan_steps)),
                        payload={
                            "source_name": str(first_step.get("source_name") or ""),
                            "pdf_page": int(first_step.get("page_number") or 1),
                            "page_index": int(first_step.get("page_index") or 1),
                            "page_total": int(first_step.get("page_total") or len(pdf_scan_steps)),
                            "pdf_total_pages": int(first_step.get("page_total") or len(pdf_scan_steps)),
                            "scroll_percent": float(first_step.get("scroll_percent") or 0.0),
                        },
                    ),
                )
            )
            for step in pdf_scan_steps:
                page_number = int(step.get("page_number") or 1)
                page_index = int(step.get("page_index") or 1)
                page_total = int(step.get("page_total") or len(pdf_scan_steps))
                source_name = str(step.get("source_name") or "Indexed PDF")
                page_label = str(step.get("page_label") or "").strip()
                snippet_preview = str(step.get("snippet") or "").strip()
                direction = str(step.get("scroll_direction") or "down").strip().lower()
                if direction not in {"up", "down"}:
                    direction = "down"
                base_payload = _pdf_scene_payload(
                    lane="pdf-page",
                    page_index=page_index,
                    page_total=page_total,
                    payload={
                        "source_name": source_name,
                        "source_id": str(step.get("source_id") or ""),
                        "pdf_page": page_number,
                        "page_index": page_index,
                        "page_total": page_total,
                        "pdf_total_pages": page_total,
                        "page_label": page_label,
                        "scroll_percent": float(step.get("scroll_percent") or 0.0),
                        "scroll_direction": direction,
                    },
                )
                events.append(
                    ToolTraceEvent(
                        event_type="pdf_page_change",
                        title=f"Navigate to PDF page {page_number}",
                        detail=(
                            f"{source_name} - page {page_number}"
                            if not page_label
                            else f"{source_name} - page {page_label}"
                        ),
                        data=base_payload,
                    )
                )
                events.append(
                    ToolTraceEvent(
                        event_type="pdf_scan_region",
                        title=f"Scan PDF page {page_number}",
                        detail=_safe_snippet(snippet_preview, limit=120)
                        or "Scanning visible text region",
                        data={
                            **base_payload,
                            "scan_region": _safe_snippet(snippet_preview, limit=240),
                            "scan_pass": page_index,
                        },
                    )
                )

        events.append(
            ToolTraceEvent(
                event_type="document_scanned",
                title="Scan document excerpts",
                detail=f"Detected {len(unique_words)} candidate highlighted word(s)",
                data=_document_scene_payload(
                    lane="document-scan",
                    payload={
                        "terms": terms[:10],
                        "highlight_color": highlight_color,
                        "max_sources": max_sources,
                        "max_chunks": max_chunks,
                    },
                ),
            )
        )
        events.append(
            ToolTraceEvent(
                event_type="highlights_detected",
                title="Highlight words in files",
                detail=", ".join(unique_words[:8]) if unique_words else "No matching words found",
                data=_document_scene_payload(
                    lane="document-highlights",
                    payload={
                        "keywords": unique_words[:12],
                        "highlight_color": highlight_color,
                        "highlighted_words": highlights[: min(max_highlights, 120)],
                        "copied_snippets": copied_snippets[:10],
                        "page_total": len(pdf_scan_steps) if pdf_scan_steps else 0,
                    },
                ),
            )
        )
        if highlights:
            first_highlight = highlights[0]
            evidence_page = _page_number_from_label(first_highlight.get("page_label")) or 1
            evidence_total = len(pdf_scan_steps) if pdf_scan_steps else max(1, evidence_page)
            events.append(
                ToolTraceEvent(
                    event_type="pdf_evidence_linked",
                    title="Link highlight evidence",
                    detail=_safe_snippet(str(first_highlight.get("snippet") or ""), limit=140),
                    data=_pdf_scene_payload(
                        lane="pdf-evidence",
                        page_index=evidence_page,
                        page_total=evidence_total,
                        payload={
                            "highlight_color": highlight_color,
                            "keyword": str(first_highlight.get("word") or ""),
                            "source_name": str(first_highlight.get("source_name") or ""),
                            "page_label": str(first_highlight.get("page_label") or ""),
                            "pdf_page": evidence_page,
                            "page_index": evidence_page,
                            "page_total": evidence_total,
                            "pdf_total_pages": evidence_total,
                        },
                    ),
                )
            )
        if copied_snippets:
            events.append(
                ToolTraceEvent(
                    event_type="doc_copy_clipboard",
                    title="Copy highlighted words",
                    detail=_safe_snippet(copied_snippets[0], limit=160),
                    data=_document_scene_payload(
                        lane="document-copy-highlight",
                        payload={
                            "clipboard_text": copied_snippets[0],
                            "highlight_color": highlight_color,
                            "keywords": unique_words[:12],
                        },
                    ),
                )
            )

        lines = [
            "### File Highlights",
            f"- Highlight color: {highlight_color}",
            f"- Source files scanned: {len(unique_sources)}",
            f"- Excerpts scanned: {len(chunks)}",
            f"- Highlighted words: {', '.join(unique_words[:12]) if unique_words else 'none'}",
        ]
        if copied_snippets:
            lines.extend(
                [
                    "",
                    "### Copied snippets",
                    *[f"- {snippet}" for snippet in copied_snippets[:6]],
                ]
            )

        return ToolExecutionResult(
            summary=f"File highlight extraction completed with {len(unique_words)} highlighted word(s).",
            content="\n".join(lines),
            data={
                "highlight_color": highlight_color,
                "keywords": unique_words[:12],
                "highlighted_words": highlights[: min(max_highlights, 120)],
                "copied_snippets": copied_snippets[:10],
                "chunk_count": len(chunks),
                "source_count": len(unique_sources),
                "max_sources": max_sources,
                "max_chunks": max_chunks,
                "max_scan_pages": max_scan_pages,
                "scene_surface": "document",
                "pdf_page": int(pdf_scan_steps[-1].get("page_number") or 1) if pdf_scan_steps else 1,
                "page_index": int(pdf_scan_steps[-1].get("page_index") or 1) if pdf_scan_steps else 1,
                "page_total": len(pdf_scan_steps),
                "pdf_total_pages": len(pdf_scan_steps),
                "scroll_percent": float(pdf_scan_steps[-1].get("scroll_percent") or 0.0)
                if pdf_scan_steps
                else 0.0,
                "scroll_direction": str(pdf_scan_steps[-1].get("scroll_direction") or "down")
                if pdf_scan_steps
                else "down",
                "scan_region": str(pdf_scan_steps[-1].get("snippet") or "") if pdf_scan_steps else "",
            },
            sources=list(source_by_id.values()),
            next_steps=[],
            events=events,
        )
