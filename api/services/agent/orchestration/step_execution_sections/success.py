from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Any
from urllib.parse import urlparse


_DEEP_FOLLOWUP_TIERS = {"deep_analytics", "deep_research", "expert"}


def _tool_surface_info(tool_id: str) -> tuple[str, str]:
    """Return (event_family, scene_surface) derived from the tool's namespace prefix."""
    tid = str(tool_id or "").lower().strip()
    if tid.startswith("browser.") or tid.startswith("web.") or tid == "marketing.web_research":
        return "browser", "browser"
    if tid.startswith("gmail.") or tid.startswith("email."):
        return "email", "email"
    if tid.startswith("analytics.") or tid.startswith("business.ga4"):
        return "analytics", "document"
    if (
        tid.startswith("docs.")
        or tid.startswith("workspace.docs")
        or tid.startswith("workspace.drive")
        or tid.startswith("workspace.sheets")
        or tid.startswith("documents.")
        or tid.startswith("sheets.")
        or tid.startswith("drive.")
        or tid.startswith("data.")
    ):
        return "document", "document"
    return "api", "document"

from api.services.agent.llm_execution_support import summarize_step_outcome
from api.services.agent.models import AgentActivityEvent
from api.services.agent.planner import PlannedStep, build_browser_followup_steps

from ..execution_trace import record_parallel_research_trace
from ..models import ExecutionState
from ..text_helpers import extract_action_artifact_metadata
from ..web_evidence import record_web_evidence
from ..web_kpi import is_web_tool, record_web_kpi
from .workspace_shadow import run_workspace_shadow_logging


def _host_from_url(url: str) -> str:
    try:
        host = str(urlparse(str(url or "").strip()).hostname or "").strip().lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    lowered = " ".join(str(value).split()).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _depth_tier_from_settings(settings: dict[str, Any]) -> str:
    return (
        " ".join(str(settings.get("__research_depth_tier") or "standard").split())
        .strip()
        .lower()
        or "standard"
    )


def _branching_mode_from_settings(settings: dict[str, Any]) -> str:
    return (
        " ".join(str(settings.get("__research_branching_mode") or "segmented").split())
        .strip()
        .lower()
        or "segmented"
    )


def _should_insert_live_source_followups(
    *,
    settings: dict[str, Any],
    deep_research_mode: bool,
) -> bool:
    explicit_allowed_scope = bool(_allowed_tool_ids_from_settings(settings))
    depth_tier = _depth_tier_from_settings(settings)
    if deep_research_mode or depth_tier in _DEEP_FOLLOWUP_TIERS:
        return True

    explicit_file_scope = _truthy(settings.get("__deep_search_prompt_scoped_pdfs")) or _truthy(
        settings.get("__deep_search_user_selected_files")
    )
    if explicit_file_scope:
        return True

    target_url = " ".join(str(settings.get("__task_target_url") or "").split()).strip()
    if target_url:
        return True

    if explicit_allowed_scope:
        # Explicit workflow step scopes should not silently fan out into
        # browser-heavy follow-up inspection during standard research runs.
        # Preserve only the clearly intentional cases above: deep tiers,
        # file-scoped reviews, and explicit target URLs.
        return False

    return False


def _should_retry_research_coverage(
    *,
    settings: dict[str, Any],
    deep_research_mode: bool,
) -> bool:
    depth_tier = _depth_tier_from_settings(settings)
    if deep_research_mode or depth_tier in _DEEP_FOLLOWUP_TIERS:
        return True
    explicit_file_scope = _truthy(settings.get("__deep_search_prompt_scoped_pdfs")) or _truthy(
        settings.get("__deep_search_user_selected_files")
    )
    if explicit_file_scope:
        return True
    target_url = " ".join(str(settings.get("__task_target_url") or "").split()).strip()
    return bool(target_url)


def _allowed_tool_ids_from_settings(settings: dict[str, Any]) -> set[str]:
    raw = settings.get("__allowed_tool_ids")
    if not isinstance(raw, list):
        return set()
    return {str(tool_id).strip() for tool_id in raw if str(tool_id).strip()}


def _primary_research_query_from_settings(settings: dict[str, Any], *, fallback: str = "") -> str:
    topic = " ".join(str(settings.get("__workflow_stage_primary_topic") or "").split()).strip()
    if topic:
        return topic[:240]
    raw_terms = settings.get("__research_search_terms")
    if isinstance(raw_terms, list):
        for item in raw_terms:
            cleaned = " ".join(str(item or "").split()).strip()
            if cleaned:
                return cleaned[:240]
    return " ".join(str(fallback or "").split()).strip()[:240]


def _filter_inserted_steps_by_allowlist(
    *,
    steps: list[PlannedStep],
    settings: dict[str, Any],
) -> list[PlannedStep]:
    allowed = _allowed_tool_ids_from_settings(settings)
    if not allowed:
        return list(steps)
    return [step for step in steps if step.tool_id in allowed]


def handle_step_success(
    *,
    access_context: Any,
    deep_research_mode: bool,
    execution_prompt: str,
    state: ExecutionState,
    registry: Any,
    steps: list[PlannedStep],
    step_cursor: int,
    step: PlannedStep,
    index: int,
    step_started: str,
    duration_seconds: float,
    result: Any,
    run_tool_live: Callable[..., Generator[dict[str, Any], None, Any]],
    emit_event: Callable[[AgentActivityEvent], dict[str, Any]],
    activity_event_factory: Callable[..., AgentActivityEvent],
) -> Generator[dict[str, Any], None, None]:
    result_data = result.data if isinstance(result.data, dict) else {}
    step_status = "failed" if result_data.get("available") is False else "success"
    if is_web_tool(step.tool_id):
        record_web_kpi(
            settings=state.execution_context.settings,
            tool_id=step.tool_id,
            status=step_status,
            duration_seconds=duration_seconds,
            data=result_data,
        )
        record_web_evidence(
            settings=state.execution_context.settings,
            tool_id=step.tool_id,
            status=step_status,
            data=result_data,
            sources=result.sources if isinstance(result.sources, list) else [],
        )
    action_metadata = extract_action_artifact_metadata(result_data, step=index)
    action = registry.get(step.tool_id).to_action(
        status=step_status,
        summary=result.summary,
        started_at=step_started,
        metadata=action_metadata,
    )
    state.all_actions.append(action)
    state.all_sources.extend(result.sources)
    state.executed_steps.append(
        {
            "step": index,
            "tool_id": step.tool_id,
            "title": step.title,
            "status": step_status,
            "summary": result.summary,
        }
    )
    llm_step = summarize_step_outcome(
        request_message=execution_prompt,
        tool_id=step.tool_id,
        step_title=step.title,
        result_summary=result.summary,
        result_data=result_data,
    )
    llm_step_summary = str(llm_step.get("summary") or "").strip()
    llm_step_suggestion = str(llm_step.get("suggestion") or "").strip()
    if llm_step_suggestion and llm_step_suggestion not in state.next_steps:
        state.next_steps.append(llm_step_suggestion)
        suggestion_event = activity_event_factory(
            event_type="tool_progress",
            title="LLM context suggestion",
            detail=llm_step_suggestion,
            metadata={
                "tool_id": step.tool_id,
                "step": index,
                "llm_suggestion": True,
            },
        )
        yield emit_event(suggestion_event)
    if llm_step_summary:
        llm_step_event = activity_event_factory(
            event_type="llm.step_summary",
            title="LLM step summary",
            detail=llm_step_summary,
            metadata={"tool_id": step.tool_id, "step": index},
        )
        yield emit_event(llm_step_event)
    event_family, scene_surface = _tool_surface_info(step.tool_id)
    completed_event = activity_event_factory(
        event_type="tool_completed" if step_status == "success" else "tool_failed",
        title=step.title,
        detail=llm_step_summary or result.summary,
        metadata={
            "event_family": event_family,
            "scene_surface": scene_surface,
            "action": "verify",
            "action_phase": "completed",
            "action_status": "completed" if step_status == "success" else "failed",
            "tool_id": step.tool_id,
            "step": index,
            "llm_step_summary": llm_step_summary,
            "llm_step_suggestion": llm_step_suggestion,
        },
    )
    yield emit_event(completed_event)

    if step_status == "success" and step.tool_id == "marketing.web_research" and not state.dynamic_inspection_inserted:
        allow_live_source_followups = _should_insert_live_source_followups(
            settings=state.execution_context.settings,
            deep_research_mode=deep_research_mode,
        )
        configured_max_urls = state.execution_context.settings.get("__research_max_live_inspections")
        try:
            max_urls = int(configured_max_urls)
        except Exception:
            max_urls = 0
        if max_urls <= 0:
            max_urls = 4 if deep_research_mode else 2
        max_urls = max(1, min(max_urls, 40))
        def _safe_int_setting(name: str, default: int) -> int:
            try:
                return int(state.execution_context.settings.get(name) or default)
            except Exception:
                return int(default)

        inserted_steps: list[PlannedStep] = []
        coverage_ok = bool(result.data.get("coverage_ok", True)) if isinstance(result.data, dict) else True
        if (
            not coverage_ok
            and not state.research_retry_inserted
            and _should_retry_research_coverage(
                settings=state.execution_context.settings,
                deep_research_mode=deep_research_mode,
            )
        ):
            result_query = (
                " ".join(str((result.data or {}).get("query") or "").split()).strip()
                if isinstance(result.data, dict)
                else ""
            )
            query = _primary_research_query_from_settings(
                state.execution_context.settings,
                fallback=result_query or execution_prompt,
            )
            max_query_variants = _safe_int_setting("__research_max_query_variants", 12)
            raw_variants = (result.data or {}).get("query_variants") if isinstance(result.data, dict) else []
            scoped_hosts_raw = (
                (result.data or {}).get("domain_scope_hosts")
                if isinstance(result.data, dict)
                else []
            )
            scoped_hosts = (
                [
                    " ".join(str(item).split()).strip().lower()
                    for item in scoped_hosts_raw
                    if " ".join(str(item).split()).strip()
                ][:6]
                if isinstance(scoped_hosts_raw, list)
                else []
            )
            target_url = " ".join(
                str(state.execution_context.settings.get("__task_target_url") or "").split()
            ).strip()
            target_host = _host_from_url(target_url)
            if target_host and target_host not in scoped_hosts:
                scoped_hosts.append(target_host)
            scope_mode = (
                " ".join(str((result.data or {}).get("domain_scope_mode") or "").split()).strip().lower()
                if isinstance(result.data, dict)
                else ""
            )
            if scope_mode not in {"strict", "prefer", "off"}:
                scope_mode = "strict" if scoped_hosts else "off"
            query_variant_limit = max(2, max_query_variants)
            query_variants = (
                [
                    " ".join(str(item).split()).strip()
                    for item in raw_variants
                    if " ".join(str(item).split()).strip()
                ][:query_variant_limit]
                if isinstance(raw_variants, list)
                else []
            )
            if not query_variants:
                planned_terms = state.execution_context.settings.get("__research_search_terms")
                if isinstance(planned_terms, list):
                    query_variants = [
                        " ".join(str(item).split()).strip()
                        for item in planned_terms
                        if " ".join(str(item).split()).strip()
                    ][:query_variant_limit]
            if query:
                inserted_steps.append(
                    PlannedStep(
                        tool_id="marketing.web_research",
                        title="Expand source coverage with additional targeted research",
                        params={
                            "query": f"{query} official report filetype:pdf",
                            "query_variants": query_variants,
                            "provider": "brave_search",
                            "allow_provider_fallback": True,
                            "max_query_variants": max_query_variants,
                            "results_per_query": _safe_int_setting("__research_results_per_query", 10),
                            "fused_top_k": _safe_int_setting("__research_fused_top_k", 80),
                            "min_unique_sources": _safe_int_setting("__research_min_unique_sources", 20),
                            "search_budget": _safe_int_setting("__research_web_search_budget", 120),
                            "domain_scope": scoped_hosts[:6],
                            "domain_scope_mode": scope_mode,
                            "target_url": target_url,
                            "research_depth_tier": str(
                                state.execution_context.settings.get("__research_depth_tier") or "standard"
                            ),
                        },
                    )
                )
                state.research_retry_inserted = True
        followup_steps = (
            build_browser_followup_steps(
                result.data,
                max_urls=max_urls,
            )
            if allow_live_source_followups
            else []
        )
        inserted_steps = _filter_inserted_steps_by_allowlist(
            steps=inserted_steps,
            settings=state.execution_context.settings,
        )
        followup_steps = _filter_inserted_steps_by_allowlist(
            steps=followup_steps,
            settings=state.execution_context.settings,
        )
        if followup_steps:
            state.dynamic_inspection_inserted = True
            inserted_steps.extend(followup_steps)
        if inserted_steps:
            insertion_point = step_cursor + 1
            steps[insertion_point:insertion_point] = inserted_steps
            batch_trace = record_parallel_research_trace(
                state=state,
                step_index=index,
                tool_id=step.tool_id,
                batch_type="adaptive_research_followups",
                inserted_steps=[item.tool_id for item in inserted_steps],
                metadata={
                    "coverage_ok": coverage_ok,
                    "inserted": len(inserted_steps),
                },
            )
            refined_event = activity_event_factory(
                event_type="plan_refined",
                title="Expanded research plan with live source inspections",
                detail=f"Inserted {len(inserted_steps)} adaptive follow-up step(s)",
                metadata={
                    "inserted": len(inserted_steps),
                    "total_steps": len(steps),
                    "step_ids": [item.tool_id for item in steps],
                    "coverage_ok": coverage_ok,
                    "live_source_followups_enabled": allow_live_source_followups,
                    "parallel_research_trace": batch_trace,
                },
            )
            yield emit_event(refined_event)

    yield from run_workspace_shadow_logging(
        access_context=access_context,
        execution_prompt=execution_prompt,
        state=state,
        step=step,
        index=index,
        result=result,
        registry=registry,
        run_tool_live=run_tool_live,
        emit_event=emit_event,
        activity_event_factory=activity_event_factory,
    )
