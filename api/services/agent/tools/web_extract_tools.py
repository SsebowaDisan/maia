from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from api.services.agent.connectors.registry import get_connector_registry
from api.services.agent.llm_runtime import call_json_response, sanitize_json_value
from api.services.agent.models import AgentSource
from api.services.agent.tools.web_quality import (
    compute_quality_score,
    quality_band,
    quality_remediation,
)
from api.services.agent.tools.base import (
    AgentTool,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolMetadata,
    ToolTraceEvent,
)
from api.services.agent.tools.web_extract_support import (
    event as _event,
    extraction_fingerprint as _extraction_fingerprint,
    normalize_field_schema as _normalize_field_schema,
    sanitize_evidence as _sanitize_evidence,
    sanitize_values as _sanitize_values,
    schema_coverage as _schema_coverage,
    schema_signature as _schema_signature,
    snippet as _snippet,
)


class WebStructuredExtractTool(AgentTool):
    metadata = ToolMetadata(
        tool_id="web.extract.structured",
        action_class="read",
        risk_level="medium",
        required_permissions=["web.read"],
        execution_policy="auto_execute",
        description="Extract schema-guided structured data from a web page.",
    )

    def _resolve_url(self, *, prompt: str, params: dict[str, Any]) -> str:
        url = str(params.get("url") or "").strip()
        if url:
            return url
        return str(params.get("source_url") or "").strip()

    def execute(
        self,
        *,
        context: ToolExecutionContext,
        prompt: str,
        params: dict[str, Any],
    ) -> ToolExecutionResult:
        tool_id = self.metadata.tool_id
        events: list[ToolTraceEvent] = []
        extraction_goal = str(params.get("extraction_goal") or params.get("goal") or prompt).strip()
        field_schema = _normalize_field_schema(params.get("field_schema") or params.get("schema"))
        url = self._resolve_url(prompt=prompt, params=params)
        page_text = str(
            params.get("page_text")
            or params.get("text")
            or params.get("html_text")
            or ""
        ).strip()
        render_quality = str(params.get("render_quality") or "unknown").strip().lower() or "unknown"
        try:
            content_density = max(0.0, min(1.0, float(params.get("content_density") or 0.0)))
        except Exception:
            content_density = 0.0
        blocked_signal = bool(params.get("blocked_signal"))
        blocked_reason = str(params.get("blocked_reason") or "").strip()

        events.append(
            _event(
                tool_id=tool_id,
                event_type="prepare_request",
                title="Prepare structured extraction request",
                detail=_snippet(extraction_goal, 140),
                data={
                    "url": url,
                    "goal": extraction_goal[:240],
                    "schema_fields": [row.get("name") for row in field_schema][:20],
                },
            )
        )

        if not page_text:
            if not url:
                raise ToolExecutionError("Provide `url` or `page_text` for structured extraction.")
            events.append(
                _event(
                    tool_id=tool_id,
                    event_type="api_call_started",
                    title="Load web page content",
                    detail=url[:180],
                    data={"web_provider": "playwright_browser"},
                )
            )
            connector = get_connector_registry().build("playwright_browser", settings=context.settings)
            capture = connector.browse_and_capture(
                url=url,
                follow_same_domain_links=False,
            )
            page_text = str(capture.get("text_excerpt") or "").strip()
            url = str(capture.get("url") or url).strip()
            render_quality = str(capture.get("render_quality") or "unknown").strip().lower() or "unknown"
            try:
                content_density = max(0.0, min(1.0, float(capture.get("content_density") or 0.0)))
            except Exception:
                content_density = 0.0
            blocked_signal = bool(capture.get("blocked_signal"))
            blocked_reason = str(capture.get("blocked_reason") or "").strip()
            events.append(
                _event(
                    tool_id=tool_id,
                    event_type="api_call_completed",
                    title="Web page content loaded",
                    detail=f"Captured {len(page_text)} characters",
                    data={
                        "captured_chars": len(page_text),
                        "render_quality": render_quality,
                        "content_density": content_density,
                        "blocked_signal": blocked_signal,
                        "blocked_reason": blocked_reason,
                    },
                )
            )

        if not page_text:
            schema_signature = _schema_signature(field_schema)
            extraction_fingerprint = _extraction_fingerprint(
                url=url,
                goal=extraction_goal,
                page_text="",
                schema_signature=schema_signature,
            )
            quality_score = compute_quality_score(
                render_quality=render_quality,
                content_density=content_density,
                extraction_confidence=0.0,
                schema_coverage=0.0,
                evidence_count=0,
                blocked_signal=blocked_signal,
            )
            return ToolExecutionResult(
                summary="Structured extraction failed: empty page content.",
                content="No readable page text was available for extraction.",
                data={
                    "url": url,
                    "goal": extraction_goal,
                    "fields": field_schema,
                    "values": {},
                    "confidence": 0.0,
                    "schema_coverage": 0.0,
                    "quality_score": quality_score,
                    "quality_band": quality_band(quality_score),
                    "extraction_fingerprint": extraction_fingerprint,
                    "schema_signature": schema_signature,
                    "evidence": [],
                    "gaps": ["No readable content extracted from target page."],
                    "render_quality": render_quality,
                    "content_density": content_density,
                    "blocked_signal": blocked_signal,
                    "blocked_reason": blocked_reason,
                },
                sources=[],
                next_steps=quality_remediation(score=quality_score, blocked_signal=blocked_signal)
                + [
                    "Retry with a different page URL.",
                    "Provide page text directly in `page_text` for deterministic extraction.",
                ],
                events=events
                + [
                    _event(
                        tool_id=tool_id,
                        event_type="tool_failed",
                        title="Structured extraction failed",
                        detail="No readable content extracted from target page.",
                        data={"reason": "empty_content"},
                    )
                ],
            )

        schema_signature = _schema_signature(field_schema)
        extraction_fingerprint = _extraction_fingerprint(
            url=url,
            goal=extraction_goal,
            page_text=page_text,
            schema_signature=schema_signature,
        )
        cache_store = context.settings.get("__web_extract_cache")
        if not isinstance(cache_store, dict):
            cache_store = {}
            context.settings["__web_extract_cache"] = cache_store
        cached_payload = cache_store.get(extraction_fingerprint)
        if isinstance(cached_payload, dict):
            cached_values = _sanitize_values(cached_payload.get("values"), field_schema)
            cached_evidence = _sanitize_evidence(cached_payload.get("evidence"), url=url)
            cached_gaps_raw = cached_payload.get("gaps")
            cached_gaps = (
                [str(item).strip()[:200] for item in cached_gaps_raw[:10] if str(item).strip()]
                if isinstance(cached_gaps_raw, list)
                else []
            )
            try:
                confidence = max(0.0, min(1.0, float(cached_payload.get("confidence") or 0.0)))
            except Exception:
                confidence = 0.0
            schema_coverage = _schema_coverage(field_schema, cached_values)
            quality_score = compute_quality_score(
                render_quality=render_quality,
                content_density=content_density,
                extraction_confidence=confidence,
                schema_coverage=schema_coverage,
                evidence_count=len(cached_evidence),
                blocked_signal=blocked_signal,
            )
            quality_label = quality_band(quality_score)
            events.append(
                _event(
                    tool_id=tool_id,
                    event_type="tool_progress",
                    title="Reuse cached structured extraction",
                    detail=f"Fingerprint: {extraction_fingerprint}",
                    data={
                        "cache_hit": True,
                        "extraction_fingerprint": extraction_fingerprint,
                        "quality_score": quality_score,
                    },
                )
            )
            field_lines = [f"- {key}: {cached_values.get(key)}" for key in list(cached_values.keys())[:20]]
            cached_content = "\n".join(
                [
                    "### Structured Web Extraction",
                    f"- URL: {url or 'n/a'}",
                    f"- Goal: {_snippet(extraction_goal, 180)}",
                    f"- Confidence: {round(confidence * 100.0, 1)}%",
                    f"- Quality score: {quality_score:.3f} ({quality_label})",
                    "",
                    "#### Extracted fields",
                    "\n".join(field_lines) if field_lines else "- No fields extracted.",
                    "",
                    "#### Gaps",
                    "\n".join(f"- {item}" for item in cached_gaps[:8]) if cached_gaps else "- None",
                ]
            )
            host = (urlparse(url).hostname or "web page").strip()
            return ToolExecutionResult(
                summary=f"Extracted {len(cached_values)} structured field(s) from web page (cached).",
                content=cached_content,
                data={
                    "url": url,
                    "goal": extraction_goal,
                    "fields": field_schema,
                    "values": cached_values,
                    "confidence": confidence,
                    "schema_coverage": schema_coverage,
                    "quality_score": quality_score,
                    "quality_band": quality_label,
                    "extraction_fingerprint": extraction_fingerprint,
                    "schema_signature": schema_signature,
                    "cache_hit": True,
                    "evidence": cached_evidence,
                    "gaps": cached_gaps,
                    "render_quality": render_quality,
                    "content_density": content_density,
                    "blocked_signal": blocked_signal,
                    "blocked_reason": blocked_reason,
                },
                sources=[
                    AgentSource(
                        source_type="web",
                        label=f"Structured extraction from {host}",
                        url=url or None,
                        score=confidence,
                        metadata={
                            "goal": extraction_goal[:240],
                            "field_count": len(cached_values),
                            "evidence_count": len(cached_evidence),
                            "confidence": confidence,
                            "schema_coverage": schema_coverage,
                            "quality_score": quality_score,
                            "quality_band": quality_label,
                            "cache_hit": True,
                        },
                    )
                ],
                next_steps=quality_remediation(score=quality_score, blocked_signal=blocked_signal)
                + [
                    "Validate extracted fields against one additional source.",
                    "Use extracted JSON in downstream reporting workflow.",
                ],
                events=events,
            )

        events.append(
            _event(
                tool_id=tool_id,
                event_type="api_call_started",
                title="Run LLM structured extraction",
                detail=f"Schema fields: {len(field_schema)}",
            )
        )
        prompt_payload = {
            "url": url,
            "goal": extraction_goal[:400],
            "field_schema": field_schema,
            "content_excerpt": page_text[:8000],
        }
        response = call_json_response(
            system_prompt=(
                "You are a web data extraction engine for enterprise workflows. "
                "Return strict JSON only and never invent facts."
            ),
            user_prompt=(
                "Extract structured data from the provided page content.\n"
                "Schema:\n"
                "{\n"
                '  "values": {"field": "value"},\n'
                '  "confidence": 0.0,\n'
                '  "evidence": [{"field":"field","quote":"exact short quote","confidence":0.0}],\n'
                '  "gaps": ["missing information"]\n'
                "}\n"
                "Rules:\n"
                "- Use only facts from content_excerpt.\n"
                "- If data is missing, set value to empty string/null and add a gap.\n"
                "- Keep evidence quotes short.\n\n"
                f"Input:\n{json.dumps(prompt_payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=22,
            max_tokens=1200,
        )
        llm_response_available = isinstance(response, dict)
        response_payload = sanitize_json_value(response) if llm_response_available else {}
        events.append(
            _event(
                tool_id=tool_id,
                event_type="api_call_completed",
                title="LLM extraction completed",
                detail="Raw extraction payload received",
                data={"llm_response_available": llm_response_available},
            )
        )

        values = _sanitize_values(response_payload.get("values"), field_schema)
        evidence = _sanitize_evidence(response_payload.get("evidence"), url=url)
        gaps_raw = response_payload.get("gaps")
        gaps = (
            [str(item).strip()[:200] for item in gaps_raw[:10] if str(item).strip()]
            if isinstance(gaps_raw, list)
            else []
        )
        confidence_raw = response_payload.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(confidence_raw)))
        except Exception:
            confidence = 0.0 if not values else 0.55
        if not llm_response_available:
            gaps.append("LLM extraction response was unavailable; extraction used deterministic fallback sanitization.")
        schema_coverage = _schema_coverage(field_schema, values)
        quality_score = compute_quality_score(
            render_quality=render_quality,
            content_density=content_density,
            extraction_confidence=confidence,
            schema_coverage=schema_coverage,
            evidence_count=len(evidence),
            blocked_signal=blocked_signal,
        )
        quality_label = quality_band(quality_score)
        cache_store[extraction_fingerprint] = {
            "values": values,
            "confidence": confidence,
            "evidence": evidence,
            "gaps": gaps,
        }

        events.append(
            _event(
                tool_id=tool_id,
                event_type="normalize_response",
                title="Normalize structured output",
                detail=f"Fields: {len(values)}, evidence rows: {len(evidence)}",
                data={
                    "confidence": confidence,
                    "field_count": len(values),
                    "evidence_count": len(evidence),
                    "schema_coverage": schema_coverage,
                    "quality_score": quality_score,
                },
            )
        )

        field_lines = [f"- {key}: {values.get(key)}" for key in list(values.keys())[:20]]
        content = "\n".join(
            [
                "### Structured Web Extraction",
                f"- URL: {url or 'n/a'}",
                f"- Goal: {_snippet(extraction_goal, 180)}",
                f"- Confidence: {round(confidence * 100.0, 1)}%",
                f"- Quality score: {quality_score:.3f} ({quality_label})",
                "",
                "#### Extracted fields",
                "\n".join(field_lines) if field_lines else "- No fields extracted.",
                "",
                "#### Gaps",
                "\n".join(f"- {item}" for item in gaps[:8]) if gaps else "- None",
            ]
        )

        host = (urlparse(url).hostname or "web page").strip()
        sources = [
            AgentSource(
                source_type="web",
                label=f"Structured extraction from {host}",
                url=url or None,
                score=confidence,
                metadata={
                    "goal": extraction_goal[:240],
                    "field_count": len(values),
                    "evidence_count": len(evidence),
                    "confidence": confidence,
                    "schema_coverage": schema_coverage,
                    "quality_score": quality_score,
                    "quality_band": quality_label,
                    "cache_hit": False,
                },
            )
        ]

        return ToolExecutionResult(
            summary=f"Extracted {len(values)} structured field(s) from web page.",
            content=content,
            data={
                "url": url,
                "goal": extraction_goal,
                "fields": field_schema,
                "values": values,
                "confidence": confidence,
                "schema_coverage": schema_coverage,
                "quality_score": quality_score,
                "quality_band": quality_label,
                "extraction_fingerprint": extraction_fingerprint,
                "schema_signature": schema_signature,
                "cache_hit": False,
                "evidence": evidence,
                "gaps": gaps,
                "render_quality": render_quality,
                "content_density": content_density,
                "blocked_signal": blocked_signal,
                "blocked_reason": blocked_reason,
            },
            sources=sources,
            next_steps=quality_remediation(score=quality_score, blocked_signal=blocked_signal)
            + [
                "Validate extracted fields against one additional source.",
                "Use extracted JSON in downstream reporting workflow.",
            ],
            events=events,
        )
