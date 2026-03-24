"""B6-02 - Workflow execution engine.

Responsibility: execute a WorkflowDefinitionSchema - resolve DAG order,
run independent steps in parallel (B8), pass outputs through input_mapping,
validate step outputs against output_schema (B6), maintain a shared run
context (B7), evaluate edge conditions for branching, and emit activity events.

Changes since original:
  B6  - output_schema validation via jsonschema (optional dep, falls back to warn)
  B7  - WorkflowRunContext integrated; context.* keys available in input_mapping
  B8  - Independent steps grouped into parallel batches (ThreadPoolExecutor)
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as _FuturesTimeout
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from api.schemas.workflow_definition import WorkflowDefinitionSchema, WorkflowEdge, WorkflowStep
from api.services.agent.events import infer_stage, infer_status
from api.services.agent.models import AgentActivityEvent, new_id
from api.services.mailer_service import send_report_email
from api.services.agent.orchestration.text_helpers import chunk_preserve_text

logger = logging.getLogger(__name__)

_MAX_PARALLEL_STEPS = 5   # cap concurrent step threads
_RETRY_BASE_DELAY = 1.0   # seconds - exponential backoff base
_CITATION_SECTION_HEADING_RE = re.compile(
    r"^##\s+(?:Evidence\s+Citations|Sources|References)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_CITATION_LINE_RE = re.compile(r"^\s*-\s*\[(\d+)\]\s*(.+?)\s*$", re.MULTILINE)
_INLINE_CITATION_RE = re.compile(r"\[(\d+)\]")
_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_EMAIL_SUBJECT_RE = re.compile(r"(?im)^\s*subject:\s*(.+?)\s*$")
_EMAIL_TO_RE = re.compile(r"(?im)^\s*to:\s*(.+?)\s*$")
_SEARCH_HOSTS = {
    "search.brave.com",
    "www.google.com",
    "google.com",
    "www.bing.com",
    "bing.com",
    "duckduckgo.com",
    "www.duckduckgo.com",
}


class WorkflowExecutionError(Exception):
    pass


def _step_tool_ids(step: WorkflowStep | None) -> list[str]:
    step_config = getattr(step, "step_config", None)
    if step is None or not isinstance(step_config, dict):
        return []
    raw = step_config.get("tool_ids")
    if not isinstance(raw, list):
        return []
    return [str(tool_id).strip() for tool_id in raw if str(tool_id).strip()]


def _extract_email_from_text(text: Any) -> str:
    match = _EMAIL_RE.search(str(text or ""))
    return str(match.group(1)).strip() if match else ""


def _normalize_http_url(value: Any) -> str:
    raw = str(value or "").strip().strip(" <>\"'`").rstrip(".,;:!?")
    if not raw or not re.match(r"^https?://", raw, flags=re.IGNORECASE):
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return parsed.geturl()


def _clean_stage_topic(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:180] if text else ""


def _normalize_delivery_artifact(text: Any) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not value:
        return ""
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _preferred_artifact_keys(step: WorkflowStep | None) -> list[str]:
    if step is None or not isinstance(getattr(step, "input_mapping", None), dict):
        return []
    preferred: list[str] = []
    for param, source in step.input_mapping.items():
        raw_source = str(source or "").strip()
        if not raw_source or raw_source.startswith("literal:") or raw_source.startswith("context:"):
            continue
        preferred.append(str(param).strip())
    return [key for key in preferred if key]


def _choose_delivery_artifact(
    step_inputs: dict[str, Any],
    *,
    step: WorkflowStep | None = None,
) -> str:
    preferred_keys = _preferred_artifact_keys(step)
    candidates: list[tuple[str, str]] = []
    for key, value in (step_inputs or {}).items():
        if key in {"message", "task", "to", "recipient", "email", "delivery_email"}:
            continue
        if isinstance(value, str):
            normalized = _normalize_delivery_artifact(value)
            if normalized:
                if normalized.lower().startswith("the ") and " agent has completed their work and handed off to you." in normalized.lower():
                    continue
                if normalized.lower().startswith("you are receiving handoff context"):
                    continue
                if normalized.lower().startswith("summary of their findings:"):
                    continue
                candidates.append((str(key), normalized))
    if not candidates:
        return ""

    def _score(item: tuple[str, str]) -> tuple[int, int, int]:
        key, text = item
        lowered = text.lower()
        score = 0
        preferred = 1 if key in preferred_keys else 0
        if "## evidence citations" in lowered or "\n## sources" in lowered or "\n## references" in lowered:
            score += 4
        if _INLINE_CITATION_RE.search(text):
            score += 3
        if "subject:" in lowered:
            score += 2
        if any(marker in lowered for marker in ("best regards", "kind regards", "warm regards", "\nhi ", "\nhello", "\ndear ")):
            score += 2
        if "handed off to you" in lowered or "your task:" in lowered or "summary of their findings" in lowered:
            score -= 6
        return (preferred, score, len(text))

    candidates.sort(key=_score, reverse=True)
    return candidates[0][1]


def _derive_delivery_subject(*, artifact: str, step: WorkflowStep | None) -> str:
    subject_match = _EMAIL_SUBJECT_RE.search(artifact)
    if subject_match:
        subject = " ".join(subject_match.group(1).split()).strip()
        if subject:
            return subject
    if step is not None:
        description = " ".join(str(step.description or "").split()).strip(" .")
        if description:
            compact = description[:120].rstrip(" .")
            return compact[0].upper() + compact[1:] if compact else "Research Brief"
    return "Research Brief"


def _derive_grounded_email_subject(
    *,
    artifact: str,
    step_inputs: dict[str, Any],
    step: WorkflowStep | None,
) -> str:
    topic = _clean_stage_topic(step_inputs.get("topic") or step_inputs.get("query"))
    if topic:
        compact_topic = topic[:80].strip(" -")
        return f"{compact_topic.title()} Research Brief"
    heading_match = re.search(r"\*\*(.+?)\*\*", str(artifact or ""))
    if heading_match:
        heading = " ".join(str(heading_match.group(1) or "").split()).strip(" -")
        if heading and len(heading) <= 90:
            return heading
    return _derive_delivery_subject(artifact=artifact, step=step)


def _derive_delivery_body(*, artifact: str) -> str:
    if not artifact:
        return ""
    lines = artifact.splitlines()
    trimmed_lines: list[str] = []
    skipped_headers = False
    for line in lines:
        stripped = line.strip()
        if not skipped_headers and (not stripped or _EMAIL_TO_RE.match(stripped) or _EMAIL_SUBJECT_RE.match(stripped)):
            continue
        skipped_headers = True
        trimmed_lines.append(line)
    body = "\n".join(trimmed_lines).strip()
    return body or artifact


def _normalize_grounded_email_result(
    *,
    result: str,
    required_subject: str,
    citation_section: str,
) -> str:
    text = str(result or "").strip()
    if not text:
        return text
    text = re.sub(
        r"\n?-- Additional context from team dialogue --.*$",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()
    text = re.sub(
        r"(?is)\b(?:current stage objective|verified research brief|source citations)\s*:.*$",
        "",
        text,
    ).strip()
    subject_match = _EMAIL_SUBJECT_RE.search(text)
    if subject_match:
        current_subject = " ".join(subject_match.group(1).split()).strip()
        invalid_subject = (
            not current_subject
            or "compose a polished" in current_subject.lower()
            or "send-ready draft" in current_subject.lower()
            or "@gmail.com" in current_subject.lower()
            or len(current_subject) > 120
        )
        if invalid_subject:
            text = _EMAIL_SUBJECT_RE.sub(f"Subject: {required_subject}", text, count=1)
    else:
        text = f"Subject: {required_subject}\n\n{text}"
    if citation_section and not _has_terminal_citation_section(text):
        text = f"{text.rstrip()}\n\n{citation_section}".strip()
    return _normalize_numbered_citation_section(text)


def _is_valid_grounded_email_draft(
    text: Any,
    *,
    citation_section: str,
) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if not raw.startswith("Subject:"):
        return False
    if "executed tools" in lowered or "internal execution traces" in lowered:
        return False
    if "summary of their findings" in lowered or "your task:" in lowered:
        return False
    if "the email-specialist agent has completed their work and handed off to you" in lowered:
        return False
    if "no external evidence sources were captured in this run" in lowered:
        return False
    if not any(marker in lowered for marker in ("\nhi ", "\nhello", "\ndear ")):
        return False
    if not any(marker in lowered for marker in ("best regards", "kind regards", "warm regards")):
        return False
    if _count_inline_citation_markers(raw) < 2:
        return False
    if citation_section and not _has_terminal_citation_section(raw):
        return False
    return True


def _is_search_like_url(url: str) -> bool:
    normalized = _normalize_http_url(url)
    if not normalized:
        return True
    try:
        parsed = urlparse(normalized)
    except Exception:
        return True
    host = (parsed.netloc or "").lower()
    if host in _SEARCH_HOSTS:
        return True
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()
    return path == "/search" or "search?" in normalized.lower() or query.startswith("q=")


def _display_label_for_url(url: str) -> str:
    normalized = _normalize_http_url(url)
    if not normalized:
        return "Source"
    parsed = urlparse(normalized)
    host = (parsed.netloc or "source").lower()
    host_label = host[4:] if host.startswith("www.") else host
    segments = [segment for segment in (parsed.path or "").split("/") if segment]
    if not segments:
        return host_label
    tail = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", segments[-1]).replace("-", " ").replace("_", " ").strip()
    if not tail or len(tail) < 4 or len(tail) > 72 or tail.isdigit():
        return host_label
    return f"{tail.title()} | {host_label}"


def _collect_step_activity_source_urls(*, run_id: str, step_agent_id: str, limit: int = 16) -> list[str]:
    try:
        from api.services.agent.activity import get_activity_store
    except Exception:
        return []

    store = get_activity_store()
    if not hasattr(store, "load_events"):
        return []
    rows = store.load_events(run_id)
    discovered: list[str] = []
    seen: set[str] = set()
    candidate_keys = ("target_url", "final_url", "page_url", "url", "source_url")
    for row in rows:
        if row.get("type") != "event":
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        candidate_step_agent_id = str(
            payload.get("step_agent_id") or data.get("step_agent_id") or metadata.get("step_agent_id") or ""
        ).strip()
        if step_agent_id and candidate_step_agent_id != step_agent_id:
            continue
        event_type = str(payload.get("event_type") or payload.get("type") or "").strip().lower()
        if event_type.startswith("team_chat") or event_type.startswith("brain_"):
            continue
        candidates: list[str] = []
        for source in (data, metadata, payload):
            for key in candidate_keys:
                value = source.get(key)
                normalized = _normalize_http_url(value)
                if normalized:
                    candidates.append(normalized)
        for candidate in candidates:
            if _is_search_like_url(candidate):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            discovered.append(candidate)
            if len(discovered) >= max(1, int(limit or 1)):
                return discovered
    return discovered


def _append_activity_citation_section(text: str, *, run_id: str, step_agent_id: str) -> str:
    body = str(text or "").strip()
    if not body or _has_terminal_citation_section(body):
        return body
    inline_refs = [int(match.group(1)) for match in _INLINE_CITATION_RE.finditer(body)]
    if not inline_refs:
        return body
    citation_urls = _collect_step_activity_source_urls(
        run_id=run_id,
        step_agent_id=step_agent_id,
        limit=max(4, max(inline_refs)),
    )
    if not citation_urls:
        return body
    rows = []
    for idx, url in enumerate(citation_urls[: max(inline_refs)], start=1):
        rows.append(f"- [{idx}] [{_display_label_for_url(url)}]({url})")
    if not rows:
        return body
    return f"{body}\n\n## Evidence Citations\n" + "\n".join(rows)


def _is_direct_delivery_candidate(step: WorkflowStep | None, step_inputs: dict[str, Any]) -> bool:
    tool_ids = set(_step_tool_ids(step))
    if not tool_ids.intersection({"gmail.send", "email.send", "mailer.report_send"}):
        return False
    if tool_ids.intersection({"marketing.web_research", "web.extract.structured", "browser.playwright.inspect"}):
        return False
    role_text = " ".join(
        str(
            (getattr(step, "step_config", {}) or {}).get("role")
            if isinstance(getattr(step, "step_config", None), dict)
            else ""
        ).split()
    ).strip().lower()
    role_implies_writer = any(
        marker in role_text
        for marker in ("writer", "author", "editor", "content", "email specialist", "drafter")
    )
    role_implies_delivery = any(
        marker in role_text
        for marker in ("deliver", "delivery", "dispatch", "sender", "mailer")
    )
    if role_implies_writer and not role_implies_delivery:
        return False
    description = " ".join(str(getattr(step, "description", "") or "").lower().split())
    if any(
        marker in description
        for marker in (
            "draft only",
            "do not dispatch",
            "do not send",
            "do not deliver",
        )
    ):
        return False
    artifact = _choose_delivery_artifact(step_inputs, step=step)
    return bool(artifact)


def _extract_terminal_citation_section(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    heading = _CITATION_SECTION_HEADING_RE.search(raw)
    if not heading:
        return ""
    section = raw[heading.start():].strip()
    return section if section and _CITATION_LINE_RE.search(section) else ""


def _looks_like_email_draft(text: Any) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if raw.startswith("Subject:"):
        return True
    if "## evidence citations" in lowered and any(
        marker in lowered for marker in ("\nhi", "\nhello", "\ndear", "\nbest regards", "\nregards")
    ):
        return True
    return False


def _is_grounded_email_draft_candidate(step: WorkflowStep | None, step_inputs: dict[str, Any]) -> bool:
    if step is None:
        return False
    if _is_direct_delivery_candidate(step, step_inputs):
        return False
    tool_ids = set(_step_tool_ids(step))
    description = " ".join(str(getattr(step, "description", "") or "").lower().split())
    if "email" not in description or "draft" not in description:
        return False
    if not tool_ids.intersection({"report.generate", "gmail.draft", "email.draft", "mailer.report_send"}):
        return False
    artifact = _choose_delivery_artifact(step_inputs, step=step)
    if not artifact:
        return False
    return _has_terminal_citation_section(artifact) and _count_inline_citation_markers(artifact) >= 1


def _looks_like_customer_facing_output(step: WorkflowStep | None, output: Any) -> bool:
    raw = str(output or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if raw.startswith("Subject:"):
        return True
    if _has_terminal_citation_section(raw) and any(
        marker in lowered
        for marker in (
            "\nhi ",
            "\nhello",
            "\ndear ",
            "best regards",
            "kind regards",
            "warm regards",
        )
    ):
        return True
    if step is None:
        return False
    description = " ".join(str(getattr(step, "description", "") or "").lower().split())
    tool_ids = set(_step_tool_ids(step))
    if "email" in description and _has_terminal_citation_section(raw):
        return True
    if tool_ids.intersection({"gmail.draft", "email.draft", "mailer.report_send"}) and _has_terminal_citation_section(raw):
        return True
    return False


def _emit_parent_step_event(
    *,
    on_event: Optional[Callable],
    run_id: str,
    step: WorkflowStep,
    agent_id: str,
    event_type: str,
    title: str,
    detail: str,
    data: dict[str, Any] | None = None,
) -> None:
    event = {
        "event_id": new_id("evt"),
        "run_id": run_id,
        "event_type": event_type,
        "title": title,
        "detail": detail,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent_id": agent_id,
        "step_agent_id": agent_id,
        "data": {
            "run_id": run_id,
            "step_id": step.step_id,
            "agent_id": agent_id,
            "step_agent_id": agent_id,
            **(data or {}),
        },
    }
    _persist_parent_activity_event(event, parent_run_id=run_id)
    if on_event:
        on_event(event)


def _run_direct_delivery_step(
    *,
    step: WorkflowStep,
    step_inputs: dict[str, Any],
    tenant_id: str,
    run_id: str,
    agent_id: str,
    on_event: Optional[Callable] = None,
) -> str | None:
    artifact = _choose_delivery_artifact(step_inputs)
    recipient = (
        _extract_email_from_text(step_inputs.get("to"))
        or _extract_email_from_text(step_inputs.get("recipient"))
        or _extract_email_from_text(step_inputs.get("delivery_email"))
        or _extract_email_from_text(step.description)
        or _extract_email_from_text(artifact)
    )
    body = _derive_delivery_body(artifact=artifact)
    if not recipient or not body:
        return None

    stored_delivery: dict[str, Any] | None = None
    if run_id:
        try:
            from api.services.agents.workflow_context import WorkflowRunContext

            run_ctx = WorkflowRunContext(run_id)
            cached = run_ctx.read(f"__delivery_sent_{step.step_id}")
            if isinstance(cached, dict):
                stored_delivery = cached
        except Exception:
            stored_delivery = None

    subject = _derive_delivery_subject(artifact=artifact, step=step)
    if stored_delivery:
        cached_body = str(stored_delivery.get("body") or body).strip() or body
        cached_recipient = str(stored_delivery.get("recipient") or recipient).strip() or recipient
        cached_subject = str(stored_delivery.get("subject") or subject).strip() or subject
        cached_message_id = str(stored_delivery.get("message_id") or "").strip()
        _emit_parent_step_event(
            on_event=on_event,
            run_id=run_id,
            step=step,
            agent_id=agent_id,
            event_type="tool_completed",
            title="Email delivery already completed",
            detail=cached_message_id or cached_recipient,
            data={
                "tool_id": "mailer.report_send",
                "recipient": cached_recipient,
                "subject": cached_subject,
                "message_id": cached_message_id,
                "deduplicated": True,
            },
        )
        return f"To: {cached_recipient}\nSubject: {cached_subject}\n\n{cached_body}"

    body_preview = body[:240]
    _emit_parent_step_event(
        on_event=on_event,
        run_id=run_id,
        step=step,
        agent_id=agent_id,
        event_type="email_open_compose",
        title="Open compose window",
        detail=recipient,
        data={"tool_id": "mailer.report_send"},
    )
    _emit_parent_step_event(
        on_event=on_event,
        run_id=run_id,
        step=step,
        agent_id=agent_id,
        event_type="email_draft_create",
        title="Create delivery draft",
        detail=recipient,
        data={"tool_id": "mailer.report_send"},
    )
    _emit_parent_step_event(
        on_event=on_event,
        run_id=run_id,
        step=step,
        agent_id=agent_id,
        event_type="tool_started",
        title="Email delivery",
        detail=recipient,
        data={"tool_id": "mailer.report_send"},
    )
    _emit_parent_step_event(
        on_event=on_event,
        run_id=run_id,
        step=step,
        agent_id=agent_id,
        event_type="email_set_to",
        title="Apply recipient",
        detail=recipient,
        data={"tool_id": "mailer.report_send"},
    )
    _emit_parent_step_event(
        on_event=on_event,
        run_id=run_id,
        step=step,
        agent_id=agent_id,
        event_type="email_set_subject",
        title="Apply subject",
        detail=subject,
        data={"tool_id": "mailer.report_send"},
    )
    typed_preview = ""
    body_chunks = chunk_preserve_text(
        body,
        chunk_size=120,
        limit=max(1, (len(body) // 120) + 2),
    )
    for chunk_index, chunk in enumerate(body_chunks, start=1):
        typed_preview += chunk
        _emit_parent_step_event(
            on_event=on_event,
            run_id=run_id,
            step=step,
            agent_id=agent_id,
            event_type="email_type_body",
            title=f"Type email body {chunk_index}/{len(body_chunks)}",
            detail=chunk or " ",
            data={
                "tool_id": "mailer.report_send",
                "chunk_index": chunk_index,
                "chunk_total": len(body_chunks),
                "typed_preview": typed_preview,
            },
        )
    _emit_parent_step_event(
        on_event=on_event,
        run_id=run_id,
        step=step,
        agent_id=agent_id,
        event_type="email_set_body",
        title="Apply email body",
        detail=f"{len(body)} characters",
        data={"tool_id": "mailer.report_send", "typed_preview": typed_preview or body},
    )
    _emit_parent_step_event(
        on_event=on_event,
        run_id=run_id,
        step=step,
        agent_id=agent_id,
        event_type="email_ready_to_send",
        title="Dispatching cited email",
        detail=recipient,
        data={"tool_id": "mailer.report_send", "typed_preview": typed_preview or body},
    )
    _emit_parent_step_event(
        on_event=on_event,
        run_id=run_id,
        step=step,
        agent_id=agent_id,
        event_type="email_click_send",
        title="Click Send",
        detail="Submitting message to mailer service",
        data={"tool_id": "mailer.report_send"},
    )
    delivery_response = send_report_email(
        to_email=recipient,
        subject=subject,
        body_text=body,
    )
    message_id = str(delivery_response.get("id") or "").strip()
    if run_id:
        try:
            from api.services.agents.workflow_context import WorkflowRunContext

            run_ctx = WorkflowRunContext(run_id)
            run_ctx.write(
                f"__delivery_sent_{step.step_id}",
                {
                    "recipient": recipient,
                    "subject": subject,
                    "body": body,
                    "message_id": message_id,
                },
            )
        except Exception:
            pass
    _emit_parent_step_event(
        on_event=on_event,
        run_id=run_id,
        step=step,
        agent_id=agent_id,
        event_type="email_sent",
        title="Cited email sent",
        detail=message_id or recipient,
        data={"tool_id": "mailer.report_send", "recipient": recipient, "subject": subject},
    )
    _emit_parent_step_event(
        on_event=on_event,
        run_id=run_id,
        step=step,
        agent_id=agent_id,
        event_type="tool_completed",
        title="Email delivery completed",
        detail=f"Sent cited email to {recipient}",
        data={"tool_id": "mailer.report_send", "recipient": recipient, "subject": subject},
    )
    return f"To: {recipient}\nSubject: {subject}\n\n{body}"


def _run_grounded_email_draft_step(
    *,
    step: WorkflowStep,
    step_inputs: dict[str, Any],
    tenant_id: str,
    run_id: str,
    on_event: Optional[Callable] = None,
) -> str:
    from api.services.agents.definition_store import get_agent, load_schema
    from api.services.agents.runner import run_agent_task

    record = get_agent(tenant_id, step.agent_id)
    if not record:
        raise ValueError(f"Agent '{step.agent_id}' not found in tenant '{tenant_id}'.")
    schema = load_schema(record)

    system_prompt = _inject_evolution_overlay(tenant_id, step.agent_id, schema.system_prompt or "")
    artifact = _choose_delivery_artifact(step_inputs, step=step)
    recipient = (
        _extract_email_from_text(step_inputs.get("to"))
        or _extract_email_from_text(step_inputs.get("recipient"))
        or _extract_email_from_text(step_inputs.get("delivery_email"))
        or _extract_email_from_text(step.description)
    )
    citation_section = _extract_terminal_citation_section(artifact)
    source_body = artifact
    if citation_section:
        source_body = artifact[: artifact.rfind(citation_section)].rstrip()
    required_subject = _derive_grounded_email_subject(
        artifact=artifact,
        step_inputs=step_inputs,
        step=step,
    )

    prompt_parts = [
        "You are preparing a client-ready outbound email draft from a verified research brief.",
        "Use only the facts and citations present in the source artifact below.",
        "Do not mention internal team discussion, workflow steps, verification process, or implementation details.",
        "Do not invent sources, statistics, study titles, or artifacts not present in the source material.",
        f"Use this exact subject line: {required_subject}",
        "Write with a premium, clear, restrained tone: crisp subject line, concise greeting, polished body, and a clean close.",
        "Convert the research brief into email prose. Do not simply copy the source headings or echo the stage instruction.",
        "Keep the result detailed enough to be useful, but shaped as an executive email rather than a report. Prefer a compact, citation-rich brief when the evidence supports it.",
        "Use short paragraphs and, only when helpful, at most three compact bullets for the most important takeaways.",
    ]
    if recipient:
        prompt_parts.append(f"Recipient: {recipient}")
    if step.description:
        prompt_parts.append(f"Current stage objective: {str(step.description).strip()}")
    prompt_parts.append(
        "Required output format:\n"
        "Subject: ...\n\n"
        "Hi ...,\n\n"
        "<body with inline citations like [1][2]>\n\n"
        "Best regards,\n"
        "<sender>\n\n"
        "## Evidence Citations\n"
        "- [1] ...\n"
        "- [2] ..."
    )
    prompt_parts.append(f"Verified research brief:\n{source_body}")
    if citation_section:
        prompt_parts.append(f"Source citations:\n{citation_section}")
    prompt = "\n\n".join(part for part in prompt_parts if part)

    result_parts: list[str] = []
    for chunk in run_agent_task(
        prompt,
        tenant_id=tenant_id,
        run_id=run_id or None,
        system_prompt=system_prompt or None,
        allowed_tool_ids=[],
        max_tool_calls=0,
        agent_id=step.agent_id,
        settings_overrides={
            "__llm_only_keyword_generation": True,
            "__workflow_stage_primary_topic": _clean_stage_topic(step_inputs.get("topic") or step_inputs.get("query")),
        },
    ):
        text = chunk.get("text") or chunk.get("content") or chunk.get("delta") or ""
        if text:
            result_parts.append(str(text))
        if on_event and isinstance(chunk, dict) and str(chunk.get("event_type") or "").strip():
            on_event(chunk)

    raw_result = _normalize_grounded_email_result(
        result="".join(result_parts).strip(),
        required_subject=required_subject,
        citation_section=citation_section,
    )
    if _is_valid_grounded_email_draft(raw_result, citation_section=citation_section):
        return raw_result

    repair_prompt = "\n\n".join(
        part
        for part in (
            "Rewrite the source artifact below into a clean outbound email draft.",
            f"Use this exact subject line: {required_subject}",
            f"Recipient: {recipient}" if recipient else "",
            "Requirements:",
            "- Use only the source artifact facts and its inline citations.",
            "- Include a real greeting, polished paragraphs, and a professional sign-off.",
            "- Keep all citations internally consistent and end with the full Evidence Citations section.",
            "- Do not mention workflow, tools, execution traces, internal review, or handoffs.",
            "- Return only the final email draft.",
            f"Source artifact:\n{source_body}",
            f"Evidence Citations:\n{citation_section}" if citation_section else "",
        )
        if part
    )
    repaired_parts: list[str] = []
    for chunk in run_agent_task(
        repair_prompt,
        tenant_id=tenant_id,
        run_id=run_id or None,
        system_prompt=system_prompt or None,
        allowed_tool_ids=[],
        max_tool_calls=0,
        agent_id=step.agent_id,
        settings_overrides={
            "__llm_only_keyword_generation": True,
            "__workflow_stage_primary_topic": _clean_stage_topic(step_inputs.get("topic") or step_inputs.get("query")),
        },
    ):
        text = chunk.get("text") or chunk.get("content") or chunk.get("delta") or ""
        if text:
            repaired_parts.append(str(text))
        if on_event and isinstance(chunk, dict) and str(chunk.get("event_type") or "").strip():
            on_event(chunk)
    repaired_result = _normalize_grounded_email_result(
        result="".join(repaired_parts).strip(),
        required_subject=required_subject,
        citation_section=citation_section,
    )
    if _is_valid_grounded_email_draft(repaired_result, citation_section=citation_section):
        return repaired_result

    greeting = f"Hi {recipient}," if recipient else "Hi,"
    fallback_body = source_body.strip()
    if citation_section and citation_section not in fallback_body:
        fallback_body = f"{fallback_body}\n\n{citation_section}"
    return (
        f"Subject: {required_subject}\n\n"
        f"{greeting}\n\n"
        f"{fallback_body}\n\n"
        "Best regards,\n"
        "Maia"
    ).strip()


def _normalize_child_activity_event(
    event: dict[str, Any],
    *,
    parent_run_id: str,
    step_agent_id: str = "",
) -> dict[str, Any]:
    payload = dict(event or {})
    original_run_id = str(payload.get("run_id") or "").strip()
    original_event_id = str(payload.get("event_id") or "").strip()
    if original_run_id and original_run_id != parent_run_id:
        payload.setdefault("source_run_id", original_run_id)
    if original_event_id:
        payload.setdefault("source_event_id", original_event_id)
    payload["run_id"] = parent_run_id
    payload["event_id"] = new_id("evt")
    if step_agent_id:
        payload["step_agent_id"] = step_agent_id

    for key in ("data", "metadata"):
        raw_map = payload.get(key)
        if not isinstance(raw_map, dict):
            continue
        next_map = dict(raw_map)
        nested_run_id = str(next_map.get("run_id") or "").strip()
        if nested_run_id and nested_run_id != parent_run_id:
            next_map.setdefault("source_run_id", nested_run_id)
        elif original_run_id and original_run_id != parent_run_id:
            next_map.setdefault("source_run_id", original_run_id)
        if step_agent_id:
            next_map.setdefault("step_agent_id", step_agent_id)
        next_map["run_id"] = parent_run_id
        payload[key] = next_map

    return payload


def _persist_parent_activity_event(event: dict[str, Any], *, parent_run_id: str) -> None:
    event_type = str(event.get("event_type") or "").strip()
    if not event_type:
        return
    raw_data = event.get("data")
    data = dict(raw_data) if isinstance(raw_data, dict) else {}
    raw_metadata = event.get("metadata")
    metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else dict(data)
    merged = dict(metadata)
    merged.update(data)
    record = AgentActivityEvent(
        event_id=str(event.get("event_id") or new_id("evt")).strip() or new_id("evt"),
        run_id=parent_run_id,
        event_type=event_type,
        title=str(event.get("title") or event_type.replace("_", " ").title()),
        detail=str(event.get("detail") or ""),
        timestamp=str(event.get("timestamp") or event.get("ts") or ""),
        metadata=merged,
        data=merged,
        seq=int(event.get("seq") or 0) if str(event.get("seq") or "").strip() else 0,
        stage=str(event.get("stage") or infer_stage(event_type)),
        status=str(event.get("status") or infer_status(event_type)),
        snapshot_ref=str(event.get("snapshot_ref") or "") or None,
    )
    from api.services.agent.activity import get_activity_store

    get_activity_store().append(record)


def execute_workflow(
    workflow: WorkflowDefinitionSchema,
    tenant_id: str,
    *,
    initial_inputs: dict[str, Any] | None = None,
    on_event: Optional[Callable[[dict[str, Any]], None]] = None,
    run_id: str | None = None,
    step_timeout_s: int = 300,
) -> dict[str, Any]:
    """Execute a workflow and return all step outputs keyed by output_key.

    Args:
        workflow: Validated WorkflowDefinitionSchema.
        tenant_id: Active tenant.
        initial_inputs: Top-level inputs available to all step input_mappings.
        on_event: Optional callback for activity events.
        run_id: Optional run ID used to key the shared WorkflowRunContext (B7).

    Returns:
        Dict mapping output_key --' step result for every executed step.
    """
    from api.services.agents.workflow_context import WorkflowRunContext, cleanup_context

    effective_run_id = run_id or str(uuid.uuid4())
    ctx = WorkflowRunContext(effective_run_id)
    outputs: dict[str, Any] = dict(initial_inputs or {})
    outputs_lock = threading.Lock()
    skipped_steps: set[str] = set()

    # Per-worker cost tracking - stored in context for step-level access
    cost_tracker = None
    try:
        from api.services.workflows.per_worker_cost import WorkflowCostTracker
        cost_tracker = WorkflowCostTracker(run_id=effective_run_id)
        ctx.write("__cost_tracker", cost_tracker)
    except Exception:
        pass

    try:
        ordered_ids = workflow.topological_order()
    except ValueError as exc:
        raise WorkflowExecutionError(str(exc)) from exc

    # Store workflow agent IDs/roster in context for real cross-agent collaboration.
    workflow_agent_ids: list[str] = []
    seen_workflow_agent_ids: set[str] = set()
    for step in workflow.steps:
        agent_id = str(step.agent_id or "").strip()
        if not agent_id or agent_id in seen_workflow_agent_ids:
            continue
        seen_workflow_agent_ids.add(agent_id)
        workflow_agent_ids.append(agent_id)
    workflow_agent_roster: list[dict[str, str]] = []
    seen_agent_ids: set[str] = set()
    for step in workflow.steps:
        agent_id = str(step.agent_id or "").strip()
        if not agent_id or agent_id in seen_agent_ids:
            continue
        seen_agent_ids.add(agent_id)
        role_hint = str(step.step_config.get("role") or "").strip() if isinstance(step.step_config, dict) else ""
        display_name = str(step.step_config.get("name") or "").strip() if isinstance(step.step_config, dict) else ""
        if not display_name:
            display_name = agent_id.replace("_", " ").replace("-", " ").strip().title() or agent_id
        if not role_hint:
            role_hint = "agent"
        workflow_agent_roster.append(
            {
                "id": agent_id,
                "agent_id": agent_id,
                "name": display_name,
                "role": role_hint,
                "step_id": str(step.step_id or "").strip(),
                "step_description": str(step.description or "").strip(),
            }
        )
    workflow_agent_roster = _ensure_supervisor_in_roster(workflow_agent_roster, workflow=workflow)
    ctx.write("__workflow_agent_ids", workflow_agent_ids)
    ctx.write("__workflow_agent_roster", workflow_agent_roster)

    # Dynamic dependency tracking for runtime unblocking visibility
    task_dag = None
    try:
        from api.services.workflows.task_dag import TaskDAG
        task_dag = TaskDAG.from_workflow(workflow)
    except Exception:
        pass

    _emit(on_event, {
        "event_type": "workflow_started",
        "workflow_id": workflow.workflow_id,
        "step_count": len(workflow.steps),
        "step_order": ordered_ids,
        "run_id": effective_run_id,
    })

    # B8: Group steps into parallel execution batches.
    batches = _build_parallel_batches(workflow, ordered_ids)

    for batch in batches:
        runnable: list[str] = []
        for step_id in batch:
            step = workflow.get_step(step_id)
            if step is None:
                continue
            incoming = [e for e in workflow.edges if e.to_step == step_id]
            if any(e.from_step in skipped_steps for e in incoming):
                skipped_steps.add(step_id)
                if task_dag:
                    task_dag.mark_skipped(step_id)
                _emit(on_event, {
                    "event_type": "workflow_step_skipped",
                    "workflow_id": workflow.workflow_id,
                    "step_id": step_id,
                    "reason": "predecessor_skipped",
                })
                continue
            if _check_conditions(incoming, outputs, on_event, workflow, step_id):
                skipped_steps.add(step_id)
                if task_dag:
                    task_dag.mark_skipped(step_id)
            else:
                runnable.append(step_id)
                if task_dag:
                    task_dag.mark_running(step_id)
                if cost_tracker:
                    cost_tracker.start_step(step_id, step.agent_id if step else "")

        if not runnable:
            continue

        if len(runnable) == 1:
            _execute_step(workflow, runnable[0], outputs, outputs_lock, ctx, tenant_id, on_event, skipped_steps, step_timeout_s, effective_run_id)
        else:
            # B8: Run independent steps concurrently
            _execute_batch(workflow, runnable, outputs, outputs_lock, ctx, tenant_id, on_event, skipped_steps, step_timeout_s, effective_run_id)

        # Update DAG + cost for completed/failed steps in this batch
        for step_id in runnable:
            if step_id in skipped_steps:
                continue
            if cost_tracker:
                cost_tracker.end_step(step_id)
                # Estimate cost from result length as a rough proxy
                result = outputs.get(workflow.get_step(step_id).output_key if workflow.get_step(step_id) else "", "")
                result_len = len(str(result or ""))
                cost_tracker.record(step_id=step_id, agent_id=workflow.get_step(step_id).agent_id if workflow.get_step(step_id) else "", tokens_in=result_len // 4, tokens_out=result_len // 4)
            if task_dag:
                if step_id in outputs or any(workflow.get_step(step_id) and workflow.get_step(step_id).output_key in outputs for _ in [1]):
                    newly_ready = task_dag.mark_completed(step_id)
                    if newly_ready:
                        _emit(on_event, {"event_type": "workflow_steps_unblocked", "workflow_id": workflow.workflow_id, "unblocked": newly_ready})
                else:
                    task_dag.mark_failed(step_id)

    # Emit cost breakdown with completion
    cost_summary = cost_tracker.summary() if cost_tracker else {}
    _emit(on_event, {
        "event_type": "workflow_completed",
        "workflow_id": workflow.workflow_id,
        "run_id": effective_run_id,
        "outputs": {k: str(v)[:6000] for k, v in outputs.items()},
        "cost_summary": cost_summary,
    })

    cleanup_context(effective_run_id)
    return outputs


# -- Parallel batch builder (B8)

def _build_parallel_batches(
    workflow: WorkflowDefinitionSchema,
    ordered_ids: list[str],
) -> list[list[str]]:
    """Group the topological order into parallel execution batches."""
    deps: dict[str, set[str]] = {s.step_id: set() for s in workflow.steps}
    for edge in workflow.edges:
        deps[edge.to_step].add(edge.from_step)

    batches: list[list[str]] = []
    completed: set[str] = set()
    remaining = list(ordered_ids)

    while remaining:
        batch = [sid for sid in remaining if deps[sid].issubset(completed)]
        if not batch:
            batch = [remaining[0]]  # Fallback - avoids infinite loop
        batches.append(batch)
        for sid in batch:
            remaining.remove(sid)
            completed.add(sid)

    return batches


# -- Step execution helpers--

def _execute_batch(
    workflow: WorkflowDefinitionSchema,
    step_ids: list[str],
    outputs: dict[str, Any],
    outputs_lock: threading.Lock,
    ctx: Any,
    tenant_id: str,
    on_event: Optional[Callable],
    skipped_steps: set[str],
    step_timeout_s: int = 300,
    run_id: str = "",
) -> None:
    cap = min(len(step_ids), _MAX_PARALLEL_STEPS)
    futures = {}

    # Compute per-step timeouts; use max for as_completed batch-level timeout
    step_timeouts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=cap, thread_name_prefix="wf-step") as pool:
        for step_id in step_ids:
            step = workflow.get_step(step_id)
            if step is None:
                continue
            with outputs_lock:
                step_inputs = _resolve_inputs(step.input_mapping, outputs, ctx)
            _emit(on_event, {
                "event_type": "workflow_step_started",
                "workflow_id": workflow.workflow_id,
                "step_id": step_id,
                "agent_id": step.agent_id,
                "step_type": step.step_type,
                "parallel": True,
            })
            timeout = step.timeout_s or step_timeout_s
            step_timeouts[step.step_id] = timeout
            futures[pool.submit(
                _run_step_with_retry, step, step_inputs, tenant_id,
                workflow.workflow_id, run_id, on_event, timeout,
            )] = (step, timeout)

        # Batch-level timeout = max of all individual step timeouts + buffer
        batch_timeout = max(step_timeouts.values(), default=step_timeout_s) + 10

        for future in as_completed(futures, timeout=batch_timeout):
            step, timeout = futures[future]
            try:
                result = future.result(timeout=timeout)
                _validate_output(step, result, workflow.workflow_id, on_event)
                with outputs_lock:
                    outputs[step.output_key] = result
                _emit(on_event, {
                    "event_type": "workflow_step_completed",
                    "workflow_id": workflow.workflow_id,
                    "step_id": step.step_id,
                    "agent_id": step.agent_id,
                    "output_key": step.output_key,
                    "result_preview": str(result)[:2000],
                })
            except _FuturesTimeout as exc:
                logger.error("Workflow step %s timed out", step.step_id)
                _emit(on_event, {
                    "event_type": "workflow_step_failed",
                    "workflow_id": workflow.workflow_id,
                    "step_id": step.step_id,
                    "error": f"Step timed out after {timeout}s",
                })
                raise WorkflowExecutionError(f"Step '{step.step_id}' timed out after {timeout}s") from exc
            except Exception as exc:
                logger.error("Workflow step %s failed: %s", step.step_id, exc, exc_info=True)
                _emit(on_event, {
                    "event_type": "workflow_step_failed",
                    "workflow_id": workflow.workflow_id,
                    "step_id": step.step_id,
                    "error": str(exc)[:2000],
                })
                raise WorkflowExecutionError(f"Step '{step.step_id}' failed: {exc}") from exc


def _execute_step(
    workflow: WorkflowDefinitionSchema,
    step_id: str,
    outputs: dict[str, Any],
    outputs_lock: threading.Lock,
    ctx: Any,
    tenant_id: str,
    on_event: Optional[Callable],
    skipped_steps: set[str],
    step_timeout_s: int = 300,
    run_id: str = "",
) -> None:
    step = workflow.get_step(step_id)
    if step is None:
        return
    with outputs_lock:
        step_inputs = _resolve_inputs(step.input_mapping, outputs, ctx)
        # Inject handoff context from predecessor step
        _inject_handoff_context(workflow, step, step_inputs, outputs, run_id, on_event)
    timeout = step.timeout_s or step_timeout_s
    _emit(on_event, {
        "event_type": "workflow_step_started",
        "workflow_id": workflow.workflow_id,
        "step_id": step_id,
        "agent_id": step.agent_id,
        "step_type": step.step_type,
        "parallel": False,
    })
    try:
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="wf-step-to") as _pool:
            _fut = _pool.submit(
                _run_step_with_retry, step, step_inputs, tenant_id,
                workflow.workflow_id, run_id, on_event, timeout,
            )
            try:
                result = _fut.result(timeout=timeout)
            except _FuturesTimeout as te:
                raise TimeoutError(f"Step '{step_id}' timed out after {timeout}s") from te
        _validate_output(step, result, workflow.workflow_id, on_event)
        with outputs_lock:
            outputs[step.output_key] = result
        _emit(on_event, {
            "event_type": "workflow_step_completed",
            "workflow_id": workflow.workflow_id,
            "step_id": step_id,
            "agent_id": step.agent_id,
            "output_key": step.output_key,
            "result_preview": str(result)[:2000],
        })
    except WorkflowExecutionError:
        raise
    except Exception as exc:
        logger.error("Workflow step %s failed: %s", step_id, exc, exc_info=True)
        _emit(on_event, {
            "event_type": "workflow_step_failed",
            "workflow_id": workflow.workflow_id,
            "step_id": step_id,
            "error": str(exc)[:2000],
        })
        raise WorkflowExecutionError(f"Step '{step_id}' failed: {exc}") from exc


def _check_conditions(
    incoming: list[WorkflowEdge],
    outputs: dict[str, Any],
    on_event: Optional[Callable],
    workflow: WorkflowDefinitionSchema,
    step_id: str,
) -> bool:
    for edge in incoming:
        if edge.condition:
            try:
                if not _eval_condition(edge.condition, outputs):
                    _emit(on_event, {
                        "event_type": "workflow_step_skipped",
                        "workflow_id": workflow.workflow_id,
                        "step_id": step_id,
                        "reason": f"condition not met: {edge.condition}",
                    })
                    return True
            except Exception as exc:
                logger.warning("Edge condition eval failed: %s - skipping %s", exc, step_id)
                return True
    return False


# -- B6: Output schema validation

def _validate_output(
    step: WorkflowStep,
    result: Any,
    workflow_id: str,
    on_event: Optional[Callable],
) -> None:
    if not step.output_schema:
        return
    try:
        import json as _json
        import jsonschema  # type: ignore[import]
        data = result
        if isinstance(result, str):
            try:
                data = _json.loads(result)
            except (ValueError, TypeError):
                pass
        jsonschema.validate(instance=data, schema=step.output_schema)
    except ImportError:
        logger.debug("jsonschema not installed - output_schema validation skipped for step %s", step.step_id)
    except Exception as exc:
        logger.warning("Step %s output failed schema validation: %s", step.step_id, exc)
        _emit(on_event, {
            "event_type": "workflow_step_output_invalid",
            "workflow_id": workflow_id,
            "step_id": step.step_id,
            "validation_error": str(exc)[:500],
        })


# -- Stage contract validation--

def _validate_stage_contract(
    step: WorkflowStep,
    phase: str,
    data: dict[str, Any],
    workflow_id: str,
    on_event: Optional[Callable],
) -> None:
    """Validate inputs or outputs against the step type's stage contract."""
    try:
        from api.services.workflows.stage_contracts import validate_step_boundary
        errors = validate_step_boundary(step_type=step.step_type, phase=phase, data=data if isinstance(data, dict) else {})
        if errors:
            logger.warning("Step %s %s contract violation: %s", step.step_id, phase, errors)
            _emit(on_event, {
                "event_type": f"workflow_step_{phase}_contract_violation",
                "workflow_id": workflow_id,
                "step_id": step.step_id,
                "violations": errors,
            })
    except Exception:
        pass


# -- Quality gate

def _run_quality_gate(
    step: WorkflowStep,
    result: Any,
    workflow_id: str,
    on_event: Optional[Callable],
) -> None:
    """Check output quality for agent steps (detect placeholders, filler).

    Raises on critically low quality (score < 0.3) so the Brain review loop
    has a chance to catch it.  Warnings are emitted for borderline scores.
    """
    if step.step_type not in ("agent", ""):
        return
    text = str(result or "")
    if len(text) < 50:
        return
    try:
        from api.services.agent.reasoning.quality_gate import check_output_quality
        qr = check_output_quality(text)
        if not qr["passed"]:
            issue_messages = [i["message"] for i in qr["issues"]]
            score = qr.get("score", 0.5)
            _emit(on_event, {
                "event_type": "workflow_step_quality_warning",
                "workflow_id": workflow_id,
                "step_id": step.step_id,
                "quality_score": score,
                "issues": issue_messages,
            })
            if score < 0.3:
                logger.warning("Step %s quality gate BLOCKED (score %.2f): %s", step.step_id, score, issue_messages)
                raise ValueError(
                    f"Quality gate failed for step '{step.step_id}' (score {score:.2f}): "
                    + "; ".join(issue_messages[:3])
                )
            logger.warning("Step %s quality gate warning (score %.2f): %s", step.step_id, score, issue_messages)
    except ValueError:
        raise
    except Exception:
        pass


def _emit_step_kickoff_chat(
    step: WorkflowStep,
    step_inputs: dict[str, Any],
    tenant_id: str,
    run_id: str,
    on_event: Optional[Callable],
) -> None:
    """Start a short teammate exchange as soon as a step begins."""
    if step.step_type not in ("agent", "") or not run_id:
        return
    try:
        from api.services.agent.brain.team_chat import get_team_chat_service
        from api.services.agents.workflow_context import WorkflowRunContext

        run_ctx = WorkflowRunContext(run_id)
        roster = run_ctx.read("__workflow_agent_roster")
        if not isinstance(roster, list) or len(roster) < 2:
            return

        original_task = str(
            step_inputs.get("message")
            or step_inputs.get("task")
            or step.description
            or ""
        ).strip()
        if not original_task:
            return

        chat_svc = get_team_chat_service()
        conversation = chat_svc.start_conversation(
            run_id=run_id,
            topic=original_task,
            initiated_by=step.agent_id or step.step_id,
            step_id=step.step_id,
            on_event=on_event,
        )
        chat_svc.kickoff_step(
            conversation=conversation,
            current_agent=str(step.agent_id or step.step_id or "").strip(),
            step_description=str(step.description or original_task).strip(),
            original_task=original_task,
            agents=roster,
            step_id=step.step_id,
            tenant_id=tenant_id,
            on_event=on_event,
        )
    except Exception as exc:
        logger.debug("Step kickoff chat skipped: %s", exc)


def _rewrite_stage_output_with_llm(
    *,
    current_output: str,
    instruction: str,
    original_task: str,
    step_description: str,
    tenant_id: str,
) -> str:
    """Revise a completed stage output without re-running the full tool stack."""
    try:
        from api.services.agent.llm_runtime import call_text_response

        prompt = (
            "Revise this completed workflow-stage deliverable.\n"
            "Return only the revised deliverable body.\n"
            "Rules:\n"
            "- Use only the information already present in the current deliverable.\n"
            "- Preserve supported claims, inline citations, markdown links, and the source section when present.\n"
            "- If a citation, URL, or numbered reference cannot be supported from the current deliverable, "
            "remove or soften the unsupported claim instead of inventing a repaired source.\n"
            "- Do not invent new sources, facts, or actions.\n"
            "- Do not mention the review process, feedback process, or internal workflow.\n"
            "- Improve attribution clarity, structure, readability, and citation hygiene.\n"
            "- For a standard research brief or research-plus-email deliverable, prefer compact executive depth; "
            "roughly 1000-1500 characters is usually appropriate unless the evidence genuinely requires more.\n\n"
            f"Original task:\n{original_task[:1200]}\n\n"
            f"Stage objective:\n{step_description[:1200]}\n\n"
            f"Revision instruction:\n{instruction[:1600]}\n\n"
            f"Current deliverable:\n{current_output[:16000]}"
        )
        rewritten = call_text_response(
            system_prompt=(
                "You revise workflow-stage deliverables for accuracy, attribution clarity, and premium readability. "
                "Return only the revised deliverable."
            ),
            user_prompt=prompt,
            temperature=0.1,
            timeout_seconds=30,
            max_tokens=2800,
            retries=1,
            enable_thinking=False,
            use_fallback_models=True,
        )
        cleaned = str(rewritten or "").strip()
        return cleaned or current_output
    except Exception as exc:
        logger.debug("Stage output rewrite skipped: %s", exc)
        return current_output


def _is_compact_research_brief_step(step: WorkflowStep | None) -> bool:
    if step is None or (step.step_type and step.step_type != "agent"):
        return False
    description = " ".join(str(getattr(step, "description", "") or "").lower().split())
    if not description:
        return False
    if "do not draft or send the email" in description or "executive research brief" in description:
        return True
    tool_ids = set(_step_tool_ids(step))
    if "email" in description or tool_ids.intersection({"gmail.draft", "gmail.send", "email.draft", "email.send", "mailer.report_send"}):
        return False
    return bool(tool_ids.intersection({"marketing.web_research", "web.extract.structured", "report.generate"}))


def _should_compact_research_brief(step: WorkflowStep | None, result: Any) -> bool:
    if not _is_compact_research_brief_step(step):
        return False
    raw = str(result or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if "subject:" in lowered or _looks_like_email_draft(raw):
        return False
    if not _has_strong_citation_scaffold(raw):
        return False
    heading_count = len(re.findall(r"(?m)^##\s+", raw))
    return len(raw) > 1800 or heading_count > 2 or "## recommended next steps" in lowered


def _compact_research_brief_output(
    *,
    step: WorkflowStep | None,
    step_inputs: dict[str, Any],
    result: Any,
    tenant_id: str,
) -> Any:
    if not _should_compact_research_brief(step, result):
        return result

    raw = str(result or "").strip()
    compacted = _rewrite_stage_output_with_llm(
        current_output=raw,
        instruction=(
            "Rewrite this into a compact cited executive research brief suitable for immediate email drafting. "
            "Keep only the highest-signal findings, remove repetition, avoid long platform/vendor laundry lists, "
            "and preserve inline citations plus the final Evidence Citations section. "
            "Prefer a one-screen brief that usually lands around 1000-1500 characters when that can preserve the evidence clearly. "
            "Do not add recommendations unless they are directly supported and materially necessary."
        ),
        original_task=str(step_inputs.get("query") or step_inputs.get("topic") or step_inputs.get("message") or step_inputs.get("task") or "").strip(),
        step_description=str(getattr(step, "description", "") or "").strip(),
        tenant_id=tenant_id,
    )
    compacted = _normalize_numbered_citation_section(str(compacted or "").strip())
    compacted = _verify_and_clean_citations(compacted, tenant_id)
    if _has_strong_citation_scaffold(compacted) and len(compacted) > 1700:
        compacted_retry = _rewrite_stage_output_with_llm(
            current_output=compacted,
            instruction=(
                "Compress this cited executive research brief further without losing the strongest supported claims. "
                "Target a tighter one-screen format: concise title, two or three short sections, and a compact Evidence Citations section. "
                "Remove secondary examples, duplicate qualifiers, and any non-essential recommendations. "
                "Keep inline citations and the terminal Evidence Citations section fully consistent."
            ),
            original_task=str(step_inputs.get("query") or step_inputs.get("topic") or step_inputs.get("message") or step_inputs.get("task") or "").strip(),
            step_description=str(getattr(step, "description", "") or "").strip(),
            tenant_id=tenant_id,
        )
        compacted_retry = _normalize_numbered_citation_section(str(compacted_retry or "").strip())
        compacted_retry = _verify_and_clean_citations(compacted_retry, tenant_id)
        if _has_strong_citation_scaffold(compacted_retry) and len(compacted_retry) < len(compacted):
            compacted = compacted_retry
    if _has_strong_citation_scaffold(compacted) and len(compacted) < len(raw):
        return compacted
    return raw


def _normalize_numbered_citation_section(text: str) -> str:
    """Normalize numbered inline citations against the terminal citation section.

    This keeps the body and terminal source list in sync:
    - renumbers surviving citations sequentially
    - removes orphan inline markers with no list entry
    - drops malformed / truncated citation rows
    - removes unreferenced terminal rows when the body has explicit markers
    """
    raw = str(text or "").strip()
    if not raw:
        return raw

    heading = _CITATION_SECTION_HEADING_RE.search(raw)
    if not heading:
        return raw

    body = raw[: heading.start()].rstrip()
    section = raw[heading.end() :].strip()
    if not section:
        return body

    entries: list[dict[str, Any]] = []
    for match in _CITATION_LINE_RE.finditer(section):
        try:
            old_idx = int(match.group(1))
        except Exception:
            continue
        remainder = str(match.group(2) or "").strip()
        url_match = re.search(r"\((https?://[^)\s]+)\)", remainder, flags=re.IGNORECASE)
        url = ""
        if url_match:
            candidate = str(url_match.group(1) or "").strip().rstrip(".,;:!?")
            if re.match(r"^https?://[^/\s)]+\.[^/\s)]+", candidate, flags=re.IGNORECASE):
                url = candidate
        if "(" in remainder and ")" in remainder and not url:
            continue
        entries.append(
            {
                "old_idx": old_idx,
                "remainder": remainder,
                "url": url,
            }
        )

    if not entries:
        return body

    body_refs = [int(match.group(1)) for match in _INLINE_CITATION_RE.finditer(body)]
    referenced = set(body_refs)
    kept_entries = [
        entry
        for entry in entries
        if (not referenced or entry["old_idx"] in referenced)
    ]
    if not kept_entries:
        return re.sub(r"\s{2,}", " ", _INLINE_CITATION_RE.sub("", body)).strip()

    old_to_new = {
        entry["old_idx"]: idx
        for idx, entry in enumerate(kept_entries, start=1)
    }

    def _replace_inline(match: re.Match[str]) -> str:
        old_idx = int(match.group(1))
        new_idx = old_to_new.get(old_idx)
        return f"[{new_idx}]" if new_idx else ""

    normalized_body = _INLINE_CITATION_RE.sub(_replace_inline, body)
    normalized_body = re.sub(r"\s+\.", ".", normalized_body)
    normalized_body = re.sub(r"\s+,", ",", normalized_body)
    normalized_body = re.sub(r"\[\](?:\s*\[\])+", "", normalized_body)
    normalized_body = re.sub(r"\n{3,}", "\n\n", normalized_body).strip()

    normalized_rows = []
    for new_idx, entry in enumerate(kept_entries, start=1):
        remainder = re.sub(r"^\[\d+\]\s*", "", entry["remainder"]).strip()
        if not remainder:
            continue
        normalized_rows.append(f"- [{new_idx}] {remainder}")
    if not normalized_rows:
        return normalized_body

    return f"{normalized_body}\n\n## Evidence Citations\n" + "\n".join(normalized_rows)


def _has_terminal_citation_section(text: str) -> bool:
    return bool(_CITATION_SECTION_HEADING_RE.search(str(text or "")))


def _count_inline_citation_markers(text: str) -> int:
    return len(list(_INLINE_CITATION_RE.finditer(str(text or ""))))


def _has_strong_citation_scaffold(text: str) -> bool:
    raw = str(text or "")
    return _has_terminal_citation_section(raw) and _count_inline_citation_markers(raw) >= 3


def _is_citation_hygiene_dialogue(
    *,
    interaction_type: Any,
    interaction_label: Any,
    operation_label: Any,
    question: Any,
    reason: Any,
) -> bool:
    normalized_turn = _normalize_dialogue_turn_type(interaction_type)
    if "citation" in normalized_turn or "reference" in normalized_turn:
        return True
    haystack = " ".join(
        str(part or "").strip().lower()
        for part in (interaction_label, operation_label, question, reason)
        if str(part or "").strip()
    )
    if not haystack:
        return False
    return any(
        marker in haystack
        for marker in (
            "citation",
            "citations",
            "evidence citations",
            "source numbering",
            "reference format",
            "formatting consistency",
            "source details",
            "complete incomplete arxiv citation",
        )
    )


def _should_skip_dialogue_need_for_reviewed_output(
    *,
    output: str,
    interaction_type: Any,
    interaction_label: Any,
    operation_label: Any,
    question: Any,
    reason: Any,
) -> bool:
    return _has_strong_citation_scaffold(output) and _is_citation_hygiene_dialogue(
        interaction_type=interaction_type,
        interaction_label=interaction_label,
        operation_label=operation_label,
        question=question,
        reason=reason,
    )


def _is_safe_integrated_output(original_output: str, revised_output: str) -> bool:
    original = str(original_output or "").strip()
    revised = str(revised_output or "").strip()
    if not revised:
        return False
    if not original:
        return True
    needs_full_preservation = _has_terminal_citation_section(original) or len(original) >= 500
    if needs_full_preservation and len(revised) < max(500, int(len(original) * 0.8)):
        return False
    if _has_terminal_citation_section(original) and not _has_terminal_citation_section(revised):
        return False
    revised_lead = revised.lstrip()[:12]
    if revised_lead and revised_lead[0] in {"—", "-", "*", "]", ")", ":"}:
        return False
    if original.startswith("Subject:") and not revised.startswith("Subject:"):
        return False
    return True


def _review_exhausted_without_proceed(review_history: list[dict[str, Any]]) -> bool:
    if not review_history:
        return False
    last = review_history[-1]
    decision = " ".join(str(last.get("decision") or "").split()).strip().lower()
    return bool(decision and decision != "proceed" and len(review_history) >= 3)


def _seconds_until_deadline(step_deadline_ts: float | None) -> float | None:
    if not step_deadline_ts:
        return None
    return max(0.0, float(step_deadline_ts) - time.monotonic())


def _should_skip_post_review_collaboration(
    *,
    step_deadline_ts: float | None,
    minimum_seconds_required: float,
) -> bool:
    remaining = _seconds_until_deadline(step_deadline_ts)
    if remaining is None:
        return False
    return remaining < float(minimum_seconds_required)


# -- Brain review - reviews agent output between workflow steps--

def _run_brain_review(
    step: WorkflowStep,
    result: Any,
    step_inputs: dict[str, Any],
    tenant_id: str,
    run_id: str,
    on_event: Optional[Callable],
    step_deadline_ts: float | None = None,
) -> Any:
    """Run Brain review loop on agent step output. Returns potentially revised output."""
    if step.step_type not in ("agent", ""):
        return result
    text_result = str(result or "").strip()
    if not text_result:
        text_result = str(step.description or step.step_id or "").strip()
    if not text_result:
        return result
    reviewed_output = text_result
    try:
        import os
        review_enabled = os.getenv("MAIA_BRAIN_REVIEW_ENABLED", "true").strip().lower() not in ("false", "0", "no")
        dialogue_enabled = os.getenv("MAIA_DIALOGUE_ENABLED", "true").strip().lower() not in ("false", "0", "no")

        original_task = str(step_inputs.get("message") or step_inputs.get("task") or step.description or "")

        def _run_agent_as(target_agent: str, prompt: str) -> str:
            agent_id = str(target_agent or "").strip() or str(step.agent_id or step.step_id).strip()
            if not agent_id:
                return ""
            agent_output = _run_agent_step(
                agent_id,
                {"message": prompt},
                tenant_id,
                run_id=run_id,
                on_event=on_event,
            )
            return str(agent_output or "")

        def _rerun_agent(prompt: str) -> str:
            # Re-run with the same agent profile rather than a generic LLM call.
            current_agent_id = str(step.agent_id or step.step_id).strip()
            return _run_agent_as(current_agent_id, prompt)

        def _revise_output(feedback: str, current_output: str, round_num: int) -> str:
            instruction = (
                f"Revision round {round_num}/{3}. "
                f"Address this feedback precisely:\n{feedback}"
            )
            revised = _rewrite_stage_output_with_llm(
                current_output=current_output,
                instruction=instruction,
                original_task=original_task,
                step_description=str(step.description or ""),
                tenant_id=tenant_id,
            )
            revised = _normalize_numbered_citation_section(revised)
            return _verify_and_clean_citations(revised, tenant_id)

        def _answer_question(question: str, current_output: str, round_num: int) -> str:
            instruction = (
                f"Question round {round_num}/{3}. "
                "Revise the deliverable so it directly answers this reviewer question while preserving supported citations:\n"
                f"{question}"
            )
            revised = _rewrite_stage_output_with_llm(
                current_output=current_output,
                instruction=instruction,
                original_task=original_task,
                step_description=str(step.description or ""),
                tenant_id=tenant_id,
            )
            revised = _normalize_numbered_citation_section(revised)
            return _verify_and_clean_citations(revised, tenant_id)

        def _answer_as_teammate(target_agent: str, prompt: str) -> str:
            try:
                from api.services.agent.llm_runtime import call_text_response
                from api.services.agents.workflow_context import WorkflowRunContext

                roster_map: dict[str, dict[str, Any]] = {}
                if run_id:
                    run_ctx = WorkflowRunContext(run_id)
                    raw_roster = run_ctx.read("__workflow_agent_roster")
                    if isinstance(raw_roster, list):
                        for row in raw_roster:
                            if isinstance(row, dict):
                                roster_map[str(row.get("agent_id") or row.get("id") or "").strip()] = row
                target_meta = roster_map.get(str(target_agent or "").strip(), {})
                target_name = str(
                    target_meta.get("name")
                    or target_meta.get("role")
                    or target_agent
                    or "Teammate"
                ).strip()
                response = call_text_response(
                    system_prompt=(
                        f"You are {target_name}, a workflow teammate contributing a short, evidence-grounded reply. "
                        "Answer only from the current shared output and task context. "
                        "Do not use tools, do not search, do not mention internal orchestration, and do not invent new evidence."
                    ),
                    user_prompt=(
                        f"Original task:\n{original_task[:1200]}\n\n"
                        f"Current stage objective:\n{str(step.description or '')[:1200]}\n\n"
                        f"Current reviewed draft:\n{reviewed_output[:5000]}\n\n"
                        f"Teammate request:\n{prompt[:2400]}"
                    ),
                    temperature=0.2,
                    timeout_seconds=20,
                    max_tokens=900,
                    retries=1,
                    enable_thinking=False,
                    use_fallback_models=True,
                )
                return str(response or "").strip()
            except Exception as exc:
                logger.debug("Teammate dialogue rewrite skipped: %s", exc)
                return ""

        review_history: list[dict[str, Any]] = []
        if review_enabled and len(text_result) >= 50:
            from api.services.agent.brain.review_loop import brain_review_loop

            reviewed_output, review_history = brain_review_loop(
                agent_id=step.agent_id or step.step_id,
                step_id=step.step_id,
                step_description=step.description,
                original_task=original_task,
                initial_output=text_result,
                run_id=run_id,
                tenant_id=tenant_id,
                on_event=on_event,
                run_agent_fn=_rerun_agent,
                revise_output_fn=_revise_output,
                answer_question_fn=_answer_question,
            )
            # Record review stats for the run summary
            if review_history:
                revisions = sum(1 for r in review_history if r.get("decision") == "revise")
                questions = sum(1 for r in review_history if r.get("decision") == "question")
                if revisions or questions:
                    _emit(on_event, {
                        "event_type": "brain_review_summary",
                        "step_id": step.step_id,
                        "data": {"revisions": revisions, "questions": questions, "rounds": len(review_history)},
                    })
            if _review_exhausted_without_proceed(review_history):
                _emit(on_event, {
                    "event_type": "brain_halt",
                    "title": f"Brain review capped for {step.agent_id or step.step_id}",
                    "detail": "Proceeding with the best cleaned draft after max review rounds.",
                    "data": {
                        "step_id": step.step_id,
                        "agent_id": step.agent_id or step.step_id,
                        "run_id": run_id,
                        "reason": "max_review_rounds_reached",
                    },
                })
                return _verify_and_clean_citations(
                    _normalize_numbered_citation_section(reviewed_output),
                    tenant_id,
                )

        reviewed_output = _verify_and_clean_citations(
            _normalize_numbered_citation_section(reviewed_output),
            tenant_id,
        )

        if dialogue_enabled and _should_skip_post_review_collaboration(
            step_deadline_ts=step_deadline_ts,
            minimum_seconds_required=150.0,
        ):
            _emit(on_event, {
                "event_type": "brain_collaboration_skipped",
                "title": f"Finalizing {step.agent_id or step.step_id}",
                "detail": "Skipping extra teammate discussion to preserve step completion time.",
                "data": {
                    "step_id": step.step_id,
                    "agent_id": step.agent_id or step.step_id,
                    "run_id": run_id,
                    "reason": "step_deadline_near",
                },
            })
            return reviewed_output

        if dialogue_enabled:
            # Team chat -- Brain facilitates agent conversations (LLM-driven)
            try:
                from api.services.agent.brain.team_chat import get_team_chat_service
                from api.services.agents.workflow_context import WorkflowRunContext

                chat_svc = get_team_chat_service()
                run_ctx = WorkflowRunContext(run_id) if run_id else None
                roster = run_ctx.read("__workflow_agent_roster") if run_ctx else []
                if roster and len(roster) > 1:
                    conv = chat_svc.start_conversation(
                        run_id=run_id, topic=original_task,
                        initiated_by=step.agent_id or step.step_id,
                        step_id=step.step_id, on_event=on_event,
                    )
                    chat_messages = chat_svc.brain_facilitates(
                        conversation=conv,
                        step_output=reviewed_output,
                        original_task=original_task,
                        agents=roster,
                        step_id=step.step_id,
                        tenant_id=tenant_id,
                        on_event=on_event,
                    )
            except Exception as exc:
                logger.debug("Team chat skipped: %s", exc)
            try:
                reviewed_output = _run_dialogue_detection(
                    step=step,
                    output=reviewed_output,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    on_event=on_event,
                    run_agent_for_agent_fn=_answer_as_teammate,
                )
            except Exception as exc:
                logger.debug("Dialogue detection skipped inside brain review: %s", exc)

        reviewed_output = _verify_and_clean_citations(
            _normalize_numbered_citation_section(reviewed_output),
            tenant_id,
        )

        return reviewed_output
    except Exception as exc:
        logger.debug("Brain review skipped: %s", exc)
        return result


# -- Dialogue detection - check if agents should talk to each other--

def _run_dialogue_detection(
    step: WorkflowStep,
    output: str,
    tenant_id: str,
    run_id: str,
    on_event: Optional[Callable],
    run_agent_for_agent_fn: Optional[Callable[[str, str], str]] = None,
) -> str:
    """Detect if the agent needs input from a teammate and facilitate the dialogue."""
    try:
        import os
        if os.getenv("MAIA_DIALOGUE_ENABLED", "true").strip().lower() in ("false", "0", "no"):
            return output

        from api.services.agent.brain.dialogue_detector import (
            detect_dialogue_needs,
            evaluate_dialogue_follow_up,
            infer_dialogue_scene,
            propose_seed_dialogue_turn,
        )
        from api.services.agent.dialogue_turns import get_dialogue_service

        # Get available agent roles from the workflow run context
        try:
            from api.services.agents.workflow_context import WorkflowRunContext
            run_ctx = WorkflowRunContext(run_id) if run_id else None
            available_agents = run_ctx.read("__workflow_agent_ids") if run_ctx else []
            available_roster = run_ctx.read("__workflow_agent_roster") if run_ctx else []
        except Exception:
            available_agents = []
            available_roster = []
        if not isinstance(available_agents, list):
            available_agents = []
        if not available_agents:
            return output
        if not isinstance(available_roster, list):
            available_roster = []

        needs = detect_dialogue_needs(
            agent_output=output,
            current_agent=step.agent_id or step.step_id,
            available_agents=available_agents,
            agent_roster=available_roster,
            step_description=step.description,
            tenant_id=tenant_id,
        )
        if not needs:
            seed_turn = propose_seed_dialogue_turn(
                agent_output=output,
                current_agent=step.agent_id or step.step_id,
                available_agents=available_agents,
                agent_roster=available_roster,
                step_description=step.description,
                tenant_id=tenant_id,
            )
            if isinstance(seed_turn, dict) and seed_turn.get("question"):
                needs = [seed_turn]
        filtered_needs: list[dict[str, Any]] = []
        for need in needs:
            if _should_skip_dialogue_need_for_reviewed_output(
                output=output,
                interaction_type=need.get("interaction_type", "question"),
                interaction_label=need.get("interaction_label", ""),
                operation_label=need.get("operation_label", ""),
                question=need.get("question", ""),
                reason=need.get("reason", ""),
            ):
                logger.debug(
                    "Skipping low-value citation dialogue for %s in %s",
                    step.agent_id or step.step_id,
                    run_id,
                )
                continue
            filtered_needs.append(need)
        needs = filtered_needs
        if not needs:
            return output

        dialogue_svc = get_dialogue_service()
        source_agent = str(step.agent_id or step.step_id or "agent").strip() or "agent"
        enrichments: list[str] = []

        for need in needs:
            target = need.get("target_agent", "")
            question = need.get("question", "")
            if not target or not question:
                continue
            interaction_type = _normalize_dialogue_turn_type(need.get("interaction_type", "question"))
            interaction_label = str(need.get("interaction_label", "")).strip() or _default_interaction_label(interaction_type)
            scene_family = _normalize_dialogue_scene_family(need.get("scene_family"))
            scene_surface = _normalize_dialogue_scene_surface(need.get("scene_surface"), scene_family=scene_family)
            operation_label = str(need.get("operation_label", "")).strip()[:160]
            action = _dialogue_action_for_surface(scene_surface=scene_surface, scene_family=scene_family)
            reason = str(need.get("reason", "")).strip()
            request_text = question
            if reason:
                request_text = f"{question}\n\nWhy this matters: {reason}"
            if not scene_family or not scene_surface:
                inferred_scene = infer_dialogue_scene(
                    current_agent=source_agent,
                    target_agent=target,
                    interaction_type=interaction_type,
                    interaction_label=interaction_label,
                    operation_label=operation_label,
                    question=request_text,
                    reason=reason,
                    step_description=str(step.description or ""),
                    source_output=str(output or ""),
                    tenant_id=tenant_id,
                )
                if not scene_family:
                    scene_family = _normalize_dialogue_scene_family(inferred_scene.get("scene_family"))
                if not scene_surface:
                    scene_surface = _normalize_dialogue_scene_surface(
                        inferred_scene.get("scene_surface"),
                        scene_family=scene_family,
                    )
                action = _dialogue_action_for_surface(scene_surface=scene_surface, scene_family=scene_family)
            prompt_preamble = _build_dialogue_prompt_preamble(
                interaction_label=interaction_label,
                reason=reason,
            )
            response_turn_type = _derive_response_turn_type(interaction_type)

            _emit(on_event, {
                "event_type": "agent_dialogue_started",
                "title": f"{source_agent} needs input from {target}",
                "detail": request_text[:200],
                "data": {
                    "from_agent": source_agent,
                    "to_agent": target,
                    "run_id": run_id,
                    "turn_role": "request",
                    "turn_type": interaction_type,
                    "interaction_type": interaction_type,
                    "interaction_label": interaction_label,
                    "scene_family": scene_family,
                    "scene_surface": scene_surface,
                    "operation_label": operation_label or interaction_label,
                    "action": action,
                    "action_phase": "active",
                    "action_status": "in_progress",
                },
            })

            answer = dialogue_svc.ask(
                run_id=run_id,
                from_agent=source_agent,
                to_agent=target,
                question=request_text,
                tenant_id=tenant_id,
                on_event=on_event,
                answer_fn=run_agent_for_agent_fn,
                ask_turn_type=interaction_type,
                answer_turn_type=response_turn_type,
                ask_turn_role="request",
                answer_turn_role="response",
                interaction_label=interaction_label,
                scene_family=scene_family,
                scene_surface=scene_surface,
                operation_label=operation_label,
                action=action,
                action_phase="active",
                action_status="in_progress",
                prompt_preamble=prompt_preamble,
            )

            follow_up = evaluate_dialogue_follow_up(
                source_agent=source_agent,
                target_agent=target,
                interaction_type=interaction_type,
                initial_request=request_text,
                teammate_response=str(answer or ""),
                source_output=str(output or ""),
                tenant_id=tenant_id,
            )
            if follow_up.get("requires_follow_up") and run_agent_for_agent_fn:
                follow_up_prompt = str(follow_up.get("follow_up_prompt", "")).strip()
                follow_up_type = _normalize_dialogue_turn_type(
                    follow_up.get("follow_up_type", interaction_type),
                )
                follow_up_label = (
                    str(follow_up.get("follow_up_label", "")).strip()
                    or str(follow_up.get("reason", "")).strip()
                    or interaction_label
                )
                follow_up_scene_family = scene_family
                follow_up_scene_surface = scene_surface
                follow_up_operation_label = operation_label
                follow_up_action = action
                if follow_up_prompt:
                    answer = dialogue_svc.ask(
                        run_id=run_id,
                        from_agent=source_agent,
                        to_agent=target,
                        question=follow_up_prompt,
                        tenant_id=tenant_id,
                        on_event=on_event,
                        answer_fn=run_agent_for_agent_fn,
                        ask_turn_type=follow_up_type,
                        answer_turn_type=_derive_response_turn_type(follow_up_type),
                        ask_turn_role="request",
                        answer_turn_role="response",
                        interaction_label=follow_up_label,
                        scene_family=follow_up_scene_family,
                        scene_surface=follow_up_scene_surface,
                        operation_label=follow_up_operation_label,
                        action=follow_up_action,
                        action_phase="active",
                        action_status="in_progress",
                        prompt_preamble=_build_dialogue_prompt_preamble(
                            interaction_label=follow_up_label,
                            reason=str(follow_up.get("reason", "")).strip(),
                        ),
                    )

            integrated = False
            if run_agent_for_agent_fn:
                try:
                    integration_prompt = (
                        f"You are {source_agent}. You asked teammate {target}: {question}\n\n"
                        f"Teammate answer:\n{answer}\n\n"
                        f"Your current step output:\n{output[:3500]}\n\n"
                        "Revise your output to integrate valid teammate insights. "
                        "If you disagree with a point, state why with evidence."
                    )
                    revised_output = run_agent_for_agent_fn(source_agent, integration_prompt)
                    revised_text = str(revised_output or "").strip()
                    if revised_text and _is_safe_integrated_output(output, revised_text):
                        output = revised_text
                        integrated = True
                        _emit(on_event, {
                            "event_type": "agent_dialogue_turn",
                            "title": f"{source_agent} integrated teammate input",
                            "detail": revised_text[:300],
                            "stage": "execute",
                            "status": "info",
                            "data": {
                                "run_id": run_id,
                                "from_agent": source_agent,
                                "to_agent": "team",
                                "turn_type": "integration",
                                "turn_role": "integration",
                                "interaction_label": "integrated teammate feedback",
                                "scene_family": scene_family,
                                "scene_surface": scene_surface,
                                "operation_label": operation_label or "Integrate teammate feedback",
                                "action": action,
                                "action_phase": "completed",
                                "action_status": "ok",
                                "message": revised_text[:1000],
                            },
                        })
                    elif revised_text:
                        logger.debug(
                            "Rejected unsafe dialogue integration for %s in %s",
                            source_agent,
                            run_id,
                        )
                except Exception as exc:
                    logger.debug("Dialogue integration skipped: %s", exc)

            if not integrated:
                enrichments.append(f"[From {target}]: {answer}")

            _emit(on_event, {
                "event_type": "agent_dialogue_resolved",
                "title": f"Dialogue resolved: {source_agent} -- {target}",
                "detail": answer[:200],
                "data": {
                    "from_agent": target,
                    "to_agent": source_agent,
                    "run_id": run_id,
                    "turn_role": "response",
                    "scene_family": scene_family,
                    "scene_surface": scene_surface,
                    "operation_label": operation_label or interaction_label,
                    "action": action,
                    "action_phase": "completed",
                    "action_status": "ok",
                },
            })

        if enrichments and not _looks_like_customer_facing_output(step, output):
            output = f"{output}\n\n-- Additional context from team dialogue --\n" + "\n".join(enrichments)

        return output
    except Exception as exc:
        logger.debug("Dialogue detection skipped: %s", exc)
        return output


# -- Evolution store - record lessons from failures

def _normalize_dialogue_turn_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "question"
    return "_".join(part for part in raw.replace("-", "_").split("_") if part) or "question"


def _derive_response_turn_type(request_turn_type: str) -> str:
    normalized = _normalize_dialogue_turn_type(request_turn_type)
    if normalized.endswith("_request"):
        return f"{normalized[:-8]}_response".strip("_")
    if normalized.endswith("_question"):
        return f"{normalized[:-9]}_response".strip("_")
    if normalized.endswith("_response") or normalized.endswith("_answer"):
        return normalized
    if normalized in {"question", "request"}:
        return "response"
    return f"{normalized}_response"


def _default_interaction_label(turn_type: str) -> str:
    normalized = _normalize_dialogue_turn_type(turn_type)
    if normalized.endswith("_request"):
        normalized = normalized[:-8]
    return normalized.replace("_", " ").strip() or "teammate input"


def _normalize_dialogue_scene_family(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    allowed = {
        "email",
        "sheet",
        "document",
        "api",
        "browser",
        "chat",
        "crm",
        "support",
        "commerce",
    }
    return normalized if normalized in allowed else ""


def _normalize_dialogue_scene_surface(value: Any, *, scene_family: str = "") -> str:
    normalized = str(value or "").strip().lower()
    allowed = {"email", "google_sheets", "google_docs", "api", "website", "system"}
    if normalized in allowed:
        return normalized

    family = _normalize_dialogue_scene_family(scene_family)
    if family == "email":
        return "email"
    if family == "sheet":
        return "google_sheets"
    if family == "document":
        return "google_docs"
    if family == "browser":
        return "website"
    if family in {"api", "chat", "crm", "support", "commerce"}:
        return "api"
    return ""


def _dialogue_action_for_surface(*, scene_surface: str, scene_family: str) -> str:
    surface = str(scene_surface or "").strip().lower()
    family = _normalize_dialogue_scene_family(scene_family)
    if surface == "email" or family == "email":
        return "type"
    if surface in {"google_docs", "google_sheets"} or family in {"document", "sheet"}:
        return "type"
    if surface == "website" or family == "browser":
        return "navigate"
    if surface == "api" or family in {"api", "chat", "crm", "support", "commerce"}:
        return "verify"
    return "other"


def _build_dialogue_prompt_preamble(*, interaction_label: str, reason: str) -> str:
    label = str(interaction_label or "").strip()
    reason_text = str(reason or "").strip()
    if label and reason_text:
        return (
            f"Collaboration style: {label}. "
            f"Respond with the evidence, correction, or revision needed. Context: {reason_text}"
        )
    if label:
        return f"Collaboration style: {label}. Respond clearly with concrete supporting detail."
    if reason_text:
        return f"Respond with concise, actionable input. Context: {reason_text}"
    return "Respond with concise, actionable teammate input."


def _record_failure_lesson(tenant_id: str, step: WorkflowStep, error: str, run_id: str) -> None:
    """Record a lesson when a step fails, for cross-run learning."""
    try:
        from api.services.agent.reasoning.evolution_store import EvolutionStore
        store = EvolutionStore(tenant_id=tenant_id)
        store.record_failure_lesson(step_id=step.step_id, error=error, run_id=run_id)
    except Exception:
        pass


def _ensure_supervisor_in_roster(
    workflow_agent_roster: list[dict[str, str]],
    *,
    workflow: WorkflowDefinitionSchema,
) -> list[dict[str, str]]:
    if len(workflow_agent_roster) < 3:
        return workflow_agent_roster
    roles = {
        " ".join(str(row.get("role") or "").strip().lower().split())
        for row in workflow_agent_roster
    }
    if any("supervisor" in role or role in {"team lead", "lead"} for role in roles):
        return workflow_agent_roster

    supervisor_row = {
        "id": "supervisor",
        "agent_id": "supervisor",
        "name": "Supervisor",
        "role": "supervisor",
        "step_id": "",
        "step_description": str(workflow.description or workflow.name or "").strip()
        or "Resolve ambiguity, challenge weak evidence, and decide when work is ready to move.",
    }
    return [supervisor_row, *workflow_agent_roster]


# -- Private helpers

def _run_step_with_retry(
    step: WorkflowStep,
    step_inputs: dict[str, Any],
    tenant_id: str,
    workflow_id: str,
    run_id: str,
    on_event: Optional[Callable] = None,
    step_timeout_s: int | None = None,
) -> Any:
    """Run a step with exponential backoff retries; dead-letter on exhaustion."""
    # Validate input contract
    _validate_stage_contract(step, "input", step_inputs, workflow_id, on_event)

    last_exc: Exception | None = None
    max_attempts = 1 + step.max_retries
    step_deadline_ts = (
        time.monotonic() + max(30, int(step_timeout_s or 0)) - 20.0
        if step_timeout_s
        else None
    )

    for attempt in range(1, max_attempts + 1):
        try:
            step_on_event = on_event
            direct_delivery_candidate = _is_direct_delivery_candidate(step, step_inputs)
            grounded_email_draft_candidate = _is_grounded_email_draft_candidate(step, step_inputs)
            if attempt == 1:
                _emit_step_kickoff_chat(step, step_inputs, tenant_id, run_id, on_event)
                try:
                    from api.services.agent.brain.action_chat import StepActionChatBridge
                    from api.services.agents.workflow_context import WorkflowRunContext

                    run_ctx = WorkflowRunContext(run_id)
                    roster = run_ctx.read("__workflow_agent_roster")
                    original_task = str(
                        step_inputs.get("message")
                        or step_inputs.get("task")
                        or step.description
                        or ""
                    ).strip()
                    if isinstance(roster, list) and len(roster) > 1 and original_task:
                        bridge = StepActionChatBridge(
                            run_id=run_id,
                            step_id=step.step_id,
                            agent_id=str(step.agent_id or step.step_id or "").strip(),
                            step_description=str(step.description or "").strip(),
                            original_task=original_task,
                            agents=roster,
                            tenant_id=tenant_id,
                            on_event=on_event,
                        )

                        def _step_event_proxy(event: dict[str, Any]) -> None:
                            if on_event:
                                on_event(event)
                            try:
                                bridge.observe(event)
                            except Exception as exc:
                                logger.debug("Action chat bridge skipped event: %s", exc)

                        step_on_event = _step_event_proxy
                except Exception as exc:
                    logger.debug("Action chat bridge unavailable: %s", exc)
            result = _dispatch_step(step, step_inputs, tenant_id, run_id, step_on_event)
            # Validate output contract + quality gate
            _validate_stage_contract(step, "output", result if isinstance(result, dict) else {}, workflow_id, on_event)
            if direct_delivery_candidate or grounded_email_draft_candidate:
                return result
            _run_quality_gate(step, result, workflow_id, on_event)
            # Brain review for agent steps
            result = _run_brain_review(
                step,
                result,
                step_inputs,
                tenant_id,
                run_id,
                on_event,
                step_deadline_ts=step_deadline_ts,
            )
            result = _compact_research_brief_output(
                step=step,
                step_inputs=step_inputs,
                result=result,
                tenant_id=tenant_id,
            )
            return result
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Step %s attempt %d/%d failed (%s) - retrying in %.1fs",
                    step.step_id, attempt, max_attempts, exc, delay,
                )
                _emit(on_event, {
                    "event_type": "workflow_step_retrying",
                    "workflow_id": workflow_id,
                    "step_id": step.step_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "delay_s": delay,
                    "error": str(exc)[:500],
                })
                time.sleep(delay)

    # Exhausted retries - record lesson for cross-run learning + dead-letter store
    if last_exc is None:
        last_exc = WorkflowExecutionError(f"Step '{step.step_id}' failed with unknown error")
    _record_failure_lesson(tenant_id, step, str(last_exc)[:300], run_id)

    try:
        from api.services.workflows.dead_letter import record_dead_letter
        record_dead_letter(
            tenant_id=tenant_id,
            run_id=run_id,
            workflow_id=workflow_id,
            step_id=step.step_id,
            error=str(last_exc),
            inputs=step_inputs,
            attempt=max_attempts,
            step_type=step.step_type,
        )
    except Exception as dl_exc:
        logger.error("Failed to record dead-letter for step %s: %s", step.step_id, dl_exc)

    raise last_exc


def _dispatch_step(
    step: WorkflowStep,
    step_inputs: dict[str, Any],
    tenant_id: str,
    run_id: str,
    on_event: Optional[Callable] = None,
) -> Any:
    """Route to the correct handler based on step_type."""
    direct_delivery_candidate = False
    grounded_email_draft_candidate = False
    if step.step_type == "agent" or not step.step_type:
        direct_delivery_candidate = _is_direct_delivery_candidate(step, step_inputs)
        grounded_email_draft_candidate = _is_grounded_email_draft_candidate(step, step_inputs)

    # Check approval gates for sensitive actions -- block until approved/rejected
    try:
        from api.services.agent.approval_workflows import get_approval_service
        service = get_approval_service()
        raw_tool_ids = list(step.step_config.get("tool_ids") or []) if isinstance(step.step_config, dict) else []
        approval_candidates = ["mailer.report_send"] if direct_delivery_candidate else raw_tool_ids
        tool_ids = [t for t in approval_candidates if service.requires_approval(t, tenant_id)]
        if tool_ids:
            gate = service.create_gate(
                run_id=run_id, tool_id=tool_ids[0], params=step_inputs,
                connector_id=step.step_config.get("connector_id", ""),
            )
            logger.info("Approval gate created for step %s: %s", step.step_id, gate.gate_id)
            # Poll for approval decision (max 5 minutes)
            import time as _approval_time
            _approval_deadline = _approval_time.time() + 300
            while _approval_time.time() < _approval_deadline:
                pending = service.list_pending(run_id=run_id)
                gate_still_pending = any(g["gate_id"] == gate.gate_id for g in pending)
                if not gate_still_pending:
                    break
                _approval_time.sleep(2)
            # Check final status
            if gate.status == "rejected":
                raise RuntimeError(f"Step '{step.step_id}' blocked: approval rejected for {tool_ids[0]}")
            if gate.status == "pending":
                raise RuntimeError(f"Step '{step.step_id}' blocked: approval timed out for {tool_ids[0]}")
            if gate.status == "approved" and gate.edited_params:
                step_inputs = {**step_inputs, **gate.edited_params}
                logger.info("Approval gate %s: using edited params", gate.gate_id)
    except RuntimeError:
        raise
    except Exception:
        pass

    if step.step_type == "agent" or not step.step_type:
        if direct_delivery_candidate:
            direct_delivery_result = _run_direct_delivery_step(
                step=step,
                step_inputs=step_inputs,
                tenant_id=tenant_id,
                run_id=run_id,
                agent_id=step.agent_id,
                on_event=on_event,
            )
            if direct_delivery_result is not None:
                return direct_delivery_result
        if grounded_email_draft_candidate:
            return _run_grounded_email_draft_step(
                step=step,
                step_inputs=step_inputs,
                tenant_id=tenant_id,
                run_id=run_id,
                on_event=on_event,
            )
        return _run_agent_step(
            step.agent_id,
            step_inputs,
            tenant_id,
            run_id=run_id,
            on_event=on_event,
            step=step,
        )

    from api.services.workflows.nodes import get_handler
    handler = get_handler(step.step_type)
    if handler is None:
        raise ValueError(f"No handler registered for step_type '{step.step_type}'")
    return handler(step, step_inputs, on_event)


def _run_agent_step(
    agent_id: str,
    step_inputs: dict[str, Any],
    tenant_id: str,
    run_id: str = "",
    on_event: Optional[Callable] = None,
    step: WorkflowStep | None = None,
) -> Any:
    from api.services.agents.definition_store import get_agent, load_schema
    from api.services.agents.runner import run_agent_task

    record = get_agent(tenant_id, agent_id)
    if not record:
        raise ValueError(f"Agent '{agent_id}' not found in tenant '{tenant_id}'.")

    schema = load_schema(record)

    # Inject evolution store lessons as prompt overlay
    system_prompt = schema.system_prompt or ""
    system_prompt = _inject_evolution_overlay(tenant_id, agent_id, system_prompt)

    # Inject handoff context from previous agent if available
    handoff_context = step_inputs.pop("__handoff_context", None)
    if handoff_context and isinstance(handoff_context, str):
        system_prompt = f"{system_prompt}\n\n{handoff_context}" if system_prompt else handoff_context

    task = step_inputs.get("message") or step_inputs.get("task") or (
        f"Execute your task with the following context:\n{_format_inputs(step_inputs)}"
    )
    query_hint = ""
    if step is not None:
        step_objective = str(step.description or "").strip()
        step_tool_ids = (
            [
                str(tool_id).strip()
                for tool_id in (
                    step.step_config.get("tool_ids")
                    if isinstance(step.step_config, dict) and isinstance(step.step_config.get("tool_ids"), list)
                    else []
                )
                if str(tool_id).strip()
            ]
            if isinstance(step.step_config, dict)
            else []
        )
        step_tool_set = {tool_id.lower() for tool_id in step_tool_ids}
        query_hint = " ".join(str(step_inputs.get("query") or step_inputs.get("topic") or "").split()).strip()
        supporting_inputs = {
            key: value
            for key, value in step_inputs.items()
            if key not in {"message", "task"} and value not in (None, "", [], {})
        }
        scoped_parts: list[str] = []
        if step_objective:
            scoped_parts.append(
                "You are executing one workflow stage, not the entire user request.\n"
                f"Current stage objective:\n{step_objective}"
            )
        if query_hint and step_tool_set.intersection(
            {
                "marketing.web_research",
                "web.extract.structured",
                "browser.playwright.inspect",
            }
        ):
            scoped_parts.append(
                "Primary research topic:\n"
                f"{query_hint}\n\n"
                "Use this topic as the basis for search queries and source selection. "
                "Treat the broader stage objective as synthesis/output guidance, not as a literal search query."
            )
        scoped_parts.append(
            "Stage completion rule:\n"
            "Finish only this stage and produce the handoff artifact needed by the next stage. "
            "Do not draft the final response, do not perform downstream delivery actions, "
            "and do not reopen completed stages unless the current stage explicitly requires it."
        )
        if supporting_inputs:
            scoped_parts.append(
                "Available context and previous outputs:\n"
                f"{_format_inputs(supporting_inputs)}"
            )
        if scoped_parts:
            task = "\n\n".join(scoped_parts)

    def _should_allow_report_synthesis(
        *,
        allowed: list[str] | None,
        explicit_step_scope: bool,
    ) -> bool:
        if explicit_step_scope:
            return False
        if allowed is None:
            return False
        allowed_set = {str(tool_id).strip() for tool_id in allowed if str(tool_id).strip()}
        if "report.generate" in allowed_set:
            return False
        if allowed_set.intersection({"gmail.draft", "gmail.send", "email.draft", "email.send", "mailer.report_send"}):
            return False
        if not allowed_set.intersection(
            {
                "marketing.web_research",
                "web.extract.structured",
                "web.dataset.adapter",
                "browser.playwright.inspect",
                "documents.highlight.extract",
                "analytics.ga4.report",
                "analytics.ga4.full_report",
                "business.ga4_kpi_sheet_report",
            }
        ):
            return False
        return True
    schema_tool_ids = (
        [str(tool_id).strip() for tool_id in list(getattr(schema, "tools", []) or []) if str(tool_id).strip()]
        if getattr(schema, "tools", None) is not None
        else []
    )
    step_tool_ids: list[str] | None = None
    if step is not None and isinstance(step.step_config, dict) and "tool_ids" in step.step_config:
        raw_step_tools = step.step_config.get("tool_ids")
        if isinstance(raw_step_tools, list):
            step_tool_ids = [
                str(tool_id).strip()
                for tool_id in raw_step_tools
                if str(tool_id).strip()
            ]
        else:
            step_tool_ids = []

    if step_tool_ids is not None:
        if schema_tool_ids:
            schema_tool_set = set(schema_tool_ids)
            allowed_tool_ids = [tool_id for tool_id in step_tool_ids if tool_id in schema_tool_set]
            if not allowed_tool_ids and step_tool_ids:
                # Workflow assembly can assign step-specific tools that are valid
                # for this run even when the persisted agent profile is narrower.
                allowed_tool_ids = list(step_tool_ids)
        else:
            allowed_tool_ids = list(step_tool_ids)
    else:
        allowed_tool_ids = list(schema_tool_ids) if schema_tool_ids else None

    if _should_allow_report_synthesis(
        allowed=allowed_tool_ids,
        explicit_step_scope=step_tool_ids is not None,
    ):
        allowed_tool_ids = list(allowed_tool_ids or [])
        allowed_tool_ids.append("report.generate")

    settings_overrides: dict[str, Any] = {}
    if query_hint:
        settings_overrides["__workflow_stage_primary_topic"] = _clean_stage_topic(query_hint)
        settings_overrides["__research_search_terms"] = [_clean_stage_topic(query_hint)]

    max_tool_calls = getattr(schema, "max_tool_calls_per_run", None)
    result_parts: list[str] = []
    for chunk in run_agent_task(
        task,
        tenant_id=tenant_id,
        run_id=run_id or None,
        system_prompt=system_prompt or None,
        allowed_tool_ids=allowed_tool_ids,
        max_tool_calls=max_tool_calls,
        agent_id=agent_id,
        settings_overrides=settings_overrides or None,
    ):
        text = chunk.get("text") or chunk.get("content") or chunk.get("delta") or ""
        if text:
            result_parts.append(str(text))
        if on_event:
            # run_agent_task proxies AgentOrchestrator.run_stream(), which emits
            # {type:"activity", event:{...}} records. Unwrap activity payloads so
            # workflow SSE receives real event_type entries instead of generic "event".
            if (
                isinstance(chunk, dict)
                and str(chunk.get("type") or "").strip().lower() == "activity"
                and isinstance(chunk.get("event"), dict)
            ):
                event_payload = {**chunk["event"], "step_agent_id": agent_id}
                normalized_event = (
                    _normalize_child_activity_event(
                        event_payload,
                        parent_run_id=run_id,
                        step_agent_id=agent_id,
                    )
                    if run_id
                    else event_payload
                )
                if run_id:
                    _persist_parent_activity_event(normalized_event, parent_run_id=run_id)
                on_event(normalized_event)
            elif isinstance(chunk, dict) and str(chunk.get("event_type") or "").strip():
                event_payload = {**chunk, "step_agent_id": agent_id}
                normalized_event = (
                    _normalize_child_activity_event(
                        event_payload,
                        parent_run_id=run_id,
                        step_agent_id=agent_id,
                    )
                    if run_id
                    else event_payload
                )
                if run_id and str(normalized_event.get("event_type") or "").strip():
                    _persist_parent_activity_event(normalized_event, parent_run_id=run_id)
                on_event(normalized_event)

    raw_result = "".join(result_parts)

    # Citation verification for agent output
    raw_result = _verify_and_clean_citations(raw_result, tenant_id)
    if run_id:
        raw_result = _append_activity_citation_section(
            raw_result,
            run_id=run_id,
            step_agent_id=agent_id,
        )

    return raw_result


def _inject_evolution_overlay(tenant_id: str, agent_id: str, system_prompt: str) -> str:
    """Inject cross-run lessons into the agent's system prompt."""
    try:
        from api.services.agent.reasoning.evolution_store import EvolutionStore
        store = EvolutionStore(tenant_id=tenant_id)
        overlay = store.get_prompt_overlay(stage=agent_id, max_lessons=5)
        if overlay:
            return f"{system_prompt}\n\n{overlay}" if system_prompt else overlay
    except Exception:
        pass
    return system_prompt


def _verify_and_clean_citations(text: str, tenant_id: str) -> str:
    """Verify citations in agent output and strip hallucinated ones."""
    if not text or len(text) < 100:
        return text
    try:
        from api.services.agent.reasoning.citation_verify import verify_citations, strip_hallucinated_citations
        # Get list of uploaded filenames for L1 verification
        filenames: list[str] = []
        try:
            from api.context import get_context
            ctx = get_context()
            index = ctx.get_index()
            Source = index._resources.get("Source")
            if Source:
                from sqlmodel import Session, select
                from ktem.db.engine import engine
                with Session(engine) as session:
                    rows = session.exec(select(Source.name)).all()
                    filenames = [str(r) for r in rows if r]
        except Exception:
            pass

        results = verify_citations(text, uploaded_filenames=filenames)
        if results:
            hallucinated = [r for r in results if r["status"] == "hallucinated"]
            if hallucinated:
                logger.info("Stripping %d hallucinated citations from agent output", len(hallucinated))
                text = strip_hallucinated_citations(text, results)
    except Exception:
        pass
    return text


def _inject_handoff_context(
    workflow: Any,
    step: Any,
    step_inputs: dict[str, Any],
    outputs: dict[str, Any],
    run_id: str,
    on_event: Optional[Callable] = None,
) -> None:
    """Build and inject handoff context from the predecessor agent."""
    if step.step_type not in ("agent", ""):
        return
    try:
        from api.services.agent.handoff_manager import build_handoff_context
        incoming_edges = [e for e in workflow.edges if e.to_step == step.step_id]
        if not incoming_edges:
            return

        contexts: list[Any] = []
        seen_predecessors: set[str] = set()
        for edge in incoming_edges:
            prev_step_id = str(getattr(edge, "from_step", "") or "").strip()
            if not prev_step_id or prev_step_id in seen_predecessors:
                continue
            seen_predecessors.add(prev_step_id)
            prev_step = workflow.get_step(prev_step_id)
            if not prev_step:
                continue
            prev_output = str(outputs.get(prev_step.output_key, "")).strip()
            if not prev_output:
                prev_output = (
                    f"Completed step {prev_step_id}: {str(getattr(prev_step, 'description', '') or '').strip()}"
                    or f"Completed step {prev_step_id}."
                )
            context = build_handoff_context(
                from_agent=prev_step.agent_id or prev_step_id,
                to_agent=step.agent_id or step.step_id,
                from_step_id=prev_step_id,
                to_step_id=step.step_id,
                previous_output=prev_output,
                step_description=step.description,
                run_id=run_id,
            )
            contexts.append(context)

        if not contexts:
            return

        if len(contexts) == 1:
            step_inputs["__handoff_context"] = contexts[0].to_prompt_context()
        else:
            context_rows = [ctx.to_prompt_context() for ctx in contexts[-4:]]
            step_inputs["__handoff_context"] = (
                "You are receiving handoff context from multiple teammates.\n\n"
                + "\n\n".join(context_rows)
            )

        for context in contexts:
            _emit(on_event, {
                "event_type": "agent_handoff",
                "title": f"{context.from_agent} -> {context.to_agent}",
                "detail": context.summary[:220],
                "stage": "execute",
                "status": "info",
                "data": {
                    **context.to_dict(),
                    "run_id": run_id,
                    "from_agent": context.from_agent,
                    "to_agent": context.to_agent,
                    "scene_family": "api",
                    "scene_surface": "system",
                    "operation_label": "Handoff context transfer",
                    "action": "handoff",
                    "action_phase": "completed",
                    "action_status": "ok",
                },
            })
    except Exception:
        pass


def _resolve_inputs(
    input_mapping: dict[str, str],
    outputs: dict[str, Any],
    ctx: Any | None = None,
) -> dict[str, Any]:
    """Resolve input_mapping against available outputs and run context (B7).

    Supports:
      - "literal:value"  --' use "value" directly
      - "context:key"    --' read from WorkflowRunContext (B7)
      - bare key         --' look up outputs[key]
    """
    resolved: dict[str, Any] = {}
    for param, source in input_mapping.items():
        if source.startswith("literal:"):
            resolved[param] = source[len("literal:"):]
        elif source.startswith("context:") and ctx is not None:
            resolved[param] = ctx.read(source[len("context:"):])
        else:
            resolved[param] = outputs.get(source, "")
    return resolved


def _eval_condition(condition: str, outputs: dict[str, Any]) -> bool:
    """Evaluate a workflow edge condition string against step outputs.

    Supports:
      - Compound:  ``A OR B``, ``A AND B``, ``NOT A``  (OR splits first, AND within)
      - Comparison: ``output.key == value``, ``output.key != value``, ``output.key > 5``
      - Truthy:     ``output.key``  (True when value is truthy)
      - Literals:   quoted strings, int/float, True/False/None/null
    """
    import re
    condition = condition.strip()

    # OR (lowest precedence) - split first so AND binds tighter
    if re.search(r'\bOR\b', condition, re.IGNORECASE):
        parts = re.split(r'\bOR\b', condition, flags=re.IGNORECASE)
        return any(_eval_condition(p.strip(), outputs) for p in parts if p.strip())

    # AND
    if re.search(r'\bAND\b', condition, re.IGNORECASE):
        parts = re.split(r'\bAND\b', condition, flags=re.IGNORECASE)
        return all(_eval_condition(p.strip(), outputs) for p in parts if p.strip())

    # NOT
    not_m = re.match(r'^NOT\s+(.+)$', condition, re.IGNORECASE)
    if not_m:
        return not _eval_condition(not_m.group(1).strip(), outputs)

    # Comparison: output.key OP value
    _CMP = re.compile(r'^output\.([A-Za-z_]\w*)\s*(==|!=|>=|<=|>|<)\s*(.+)$')
    m = _CMP.match(condition)
    if m:
        key, op, raw_val = m.group(1), m.group(2), m.group(3).strip()
        lhs = outputs.get(key)
        rhs: Any
        if (raw_val.startswith('"') and raw_val.endswith('"')) or \
           (raw_val.startswith("'") and raw_val.endswith("'")):
            rhs = raw_val[1:-1]
        elif raw_val in ("True", "true"):
            rhs = True
        elif raw_val in ("False", "false"):
            rhs = False
        elif raw_val in ("None", "null"):
            rhs = None
        else:
            try:
                rhs = int(raw_val)
            except ValueError:
                try:
                    rhs = float(raw_val)
                except ValueError:
                    rhs = raw_val
        if op == "==":
            return lhs == rhs
        if op == "!=":
            return lhs != rhs
        try:
            lhs_n, rhs_n = float(lhs), float(rhs)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        return {">" : lhs_n > rhs_n, ">=" : lhs_n >= rhs_n,
                "<" : lhs_n < rhs_n, "<=" : lhs_n <= rhs_n}.get(op, False)

    # Truthy: output.key
    _TRUTHY = re.compile(r'^output\.([A-Za-z_]\w*)$')
    m2 = _TRUTHY.match(condition)
    if m2:
        return bool(outputs.get(m2.group(1)))

    logger.warning("Unsupported workflow condition syntax (skipping): %r", condition)
    return False


def _emit(on_event: Optional[Callable], event: dict[str, Any]) -> None:
    if on_event:
        try:
            on_event(event)
        except Exception:
            pass


def _format_inputs(inputs: dict[str, Any]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in inputs.items())

