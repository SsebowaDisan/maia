from __future__ import annotations

import hashlib
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

SCENE_SURFACE_PREVIEW = "preview"


def _snippet(text: str, max_len: int = 220) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[: max_len - 1].rstrip()}..."


def _event(
    *,
    tool_id: str,
    event_type: str,
    title: str,
    detail: str = "",
    data: dict[str, Any] | None = None,
) -> ToolTraceEvent:
    payload = {"tool_id": tool_id, "scene_surface": SCENE_SURFACE_PREVIEW}
    if isinstance(data, dict):
        payload.update(data)
    return ToolTraceEvent(event_type=event_type, title=title, detail=detail, data=payload)


def _normalize_field_schema(value: Any) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    if isinstance(value, dict):
        for raw_name, raw_type in list(value.items())[:20]:
            name = str(raw_name or "").strip()[:80]
            field_type = str(raw_type or "string").strip().lower()[:32] or "string"
            if not name:
                continue
            normalized.append({"name": name, "type": field_type, "description": ""})
    elif isinstance(value, list):
        for item in value[:20]:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("field") or "").strip()[:80]
            if not name:
                continue
            field_type = str(item.get("type") or "string").strip().lower()[:32] or "string"
            description = str(item.get("description") or "").strip()[:160]
            normalized.append({"name": name, "type": field_type, "description": description})
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in normalized:
        key = str(row.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _parse_boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"true", "yes", "1", "y"}:
        return True
    if text in {"false", "no", "0", "n"}:
        return False
    return None


def _coerce_field_value(field_type: str, value: Any) -> Any:
    normalized_type = str(field_type or "string").strip().lower()
    if normalized_type in {"number", "float"}:
        try:
            return float(str(value).replace(",", "").strip())
        except Exception:
            return None
    if normalized_type in {"integer", "int"}:
        try:
            return int(float(str(value).replace(",", "").strip()))
        except Exception:
            return None
    if normalized_type in {"bool", "boolean"}:
        return _parse_boolean(value)
    if normalized_type in {"array", "list"}:
        if isinstance(value, list):
            cleaned = [str(item).strip()[:160] for item in value if str(item).strip()]
            return cleaned[:12]
        text = str(value or "").strip()
        if not text:
            return []
        return [text[:160]]
    text = str(value or "").strip()
    return text[:360]


def _sanitize_values(values: Any, field_schema: list[dict[str, str]]) -> dict[str, Any]:
    rows = values if isinstance(values, dict) else {}
    if field_schema:
        output: dict[str, Any] = {}
        for field in field_schema:
            name = str(field.get("name") or "").strip()
            if not name:
                continue
            output[name] = _coerce_field_value(str(field.get("type") or "string"), rows.get(name))
        return output
    fallback: dict[str, Any] = {}
    for raw_key, raw_value in list(rows.items())[:12]:
        key = str(raw_key or "").strip()[:80]
        if not key:
            continue
        if isinstance(raw_value, (int, float, bool)):
            fallback[key] = raw_value
            continue
        if isinstance(raw_value, list):
            cleaned = [str(item).strip()[:160] for item in raw_value if str(item).strip()]
            fallback[key] = cleaned[:10]
            continue
        text = str(raw_value or "").strip()
        fallback[key] = text[:360]
    return fallback


def _sanitize_evidence(payload: Any, *, url: str) -> list[dict[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    output: list[dict[str, Any]] = []
    for row in rows[:12]:
        if not isinstance(row, dict):
            continue
        field_name = str(row.get("field") or "").strip()[:80]
        quote = str(row.get("quote") or row.get("excerpt") or "").strip()[:320]
        if not quote:
            continue
        confidence_raw = row.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(confidence_raw)))
        except Exception:
            confidence = None
        output.append(
            {
                "field": field_name,
                "quote": quote,
                "confidence": confidence,
                "url": url,
            }
        )
    return output


def _schema_signature(field_schema: list[dict[str, str]]) -> str:
    ordered = [
        {
            "name": str(item.get("name") or "").strip(),
            "type": str(item.get("type") or "").strip().lower(),
        }
        for item in field_schema
    ]
    raw = json.dumps(ordered, ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _extraction_fingerprint(*, url: str, goal: str, page_text: str, schema_signature: str) -> str:
    payload = {
        "url": str(url or "").strip().lower(),
        "goal": " ".join(str(goal or "").split()).strip().lower(),
        "content_hash": hashlib.sha256(str(page_text or "").encode("utf-8")).hexdigest(),
        "schema_signature": schema_signature,
    }
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _schema_coverage(field_schema: list[dict[str, str]], values: dict[str, Any]) -> float:
    if not field_schema:
        return 1.0 if values else 0.0
    populated = 0
    for field in field_schema:
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        value = values.get(name)
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                populated += 1
            continue
        if isinstance(value, list):
            if value:
                populated += 1
            continue
        populated += 1
    expected = max(1, len([row for row in field_schema if str(row.get("name") or "").strip()]))
    return round(max(0.0, min(1.0, float(populated) / float(expected))), 4)


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
