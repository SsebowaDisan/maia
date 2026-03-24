from __future__ import annotations

import re
from typing import Any, Optional

from api.schemas.workflow_definition import WorkflowStep
from api.services.agent.orchestration.text_helpers import chunk_preserve_text

from .activity import _emit_parent_step_event
from .common import (
    _clean_stage_topic,
    _count_inline_citation_markers,
    _EMAIL_SUBJECT_RE,
    _EMAIL_TO_RE,
    _extract_email_from_text,
    _extract_terminal_citation_section,
    _has_terminal_citation_section,
    _INLINE_CITATION_RE,
    _looks_like_email_draft,
    _normalize_delivery_artifact,
    _preferred_artifact_keys,
    _step_tool_ids,
)
from .review import _has_strong_citation_scaffold, _normalize_numbered_citation_section


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
                lowered = normalized.lower()
                if lowered.startswith("the ") and " agent has completed their work and handed off to you." in lowered:
                    continue
                if lowered.startswith("you are receiving handoff context"):
                    continue
                if lowered.startswith("summary of their findings:"):
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
    text = re.sub(r"\n?-- Additional context from team dialogue --.*$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    text = re.sub(r"(?is)\b(?:current stage objective|verified research brief|source citations)\s*:.*$", "", text).strip()
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


def _is_direct_delivery_candidate(step: WorkflowStep | None, step_inputs: dict[str, Any]) -> bool:
    tool_ids = set(_step_tool_ids(step))
    if not tool_ids.intersection({"gmail.send", "email.send", "mailer.report_send"}):
        return False
    if tool_ids.intersection({"marketing.web_research", "web.extract.structured", "browser.playwright.inspect"}):
        return False
    role_text = " ".join(
        str((getattr(step, "step_config", {}) or {}).get("role") if isinstance(getattr(step, "step_config", None), dict) else "").split()
    ).strip().lower()
    role_implies_writer = any(marker in role_text for marker in ("writer", "author", "editor", "content", "email specialist", "drafter"))
    role_implies_delivery = any(marker in role_text for marker in ("deliver", "delivery", "dispatch", "sender", "mailer"))
    if role_implies_writer and not role_implies_delivery:
        return False
    description = " ".join(str(getattr(step, "description", "") or "").lower().split())
    if any(marker in description for marker in ("draft only", "do not dispatch", "do not send", "do not deliver")):
        return False
    artifact = _choose_delivery_artifact(step_inputs, step=step)
    return bool(artifact)


def _is_grounded_email_draft_candidate(step: WorkflowStep | None, step_inputs: dict[str, Any]) -> bool:
    if step is None or _is_direct_delivery_candidate(step, step_inputs):
        return False
    tool_ids = set(_step_tool_ids(step))
    description = " ".join(str(getattr(step, "description", "") or "").lower().split())
    if "email" not in description or "draft" not in description:
        return False
    if not tool_ids.intersection({"report.generate", "gmail.draft", "email.draft", "mailer.report_send"}):
        return False
    artifact = _choose_delivery_artifact(step_inputs, step=step)
    return bool(artifact) and _has_terminal_citation_section(artifact) and _count_inline_citation_markers(artifact) >= 1


def _run_direct_delivery_step(
    *,
    step: WorkflowStep,
    step_inputs: dict[str, Any],
    tenant_id: str,
    run_id: str,
    agent_id: str,
    on_event: Optional[Any] = None,
    ops: Any,
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
            cached = WorkflowRunContext(run_id).read(f"__delivery_sent_{step.step_id}")
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
            data={"tool_id": "mailer.report_send", "recipient": cached_recipient, "subject": cached_subject, "message_id": cached_message_id, "deduplicated": True},
        )
        return f"To: {cached_recipient}\nSubject: {cached_subject}\n\n{cached_body}"

    for event_type, title, detail, data in [
        ("email_open_compose", "Open compose window", recipient, {"tool_id": "mailer.report_send"}),
        ("email_draft_create", "Create delivery draft", recipient, {"tool_id": "mailer.report_send"}),
        ("tool_started", "Email delivery", recipient, {"tool_id": "mailer.report_send"}),
        ("email_set_to", "Apply recipient", recipient, {"tool_id": "mailer.report_send"}),
        ("email_set_subject", "Apply subject", subject, {"tool_id": "mailer.report_send"}),
    ]:
        _emit_parent_step_event(on_event=on_event, run_id=run_id, step=step, agent_id=agent_id, event_type=event_type, title=title, detail=detail, data=data)

    typed_preview = ""
    body_chunks = chunk_preserve_text(body, chunk_size=120, limit=max(1, (len(body) // 120) + 2))
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
            data={"tool_id": "mailer.report_send", "chunk_index": chunk_index, "chunk_total": len(body_chunks), "typed_preview": typed_preview},
        )
    _emit_parent_step_event(on_event=on_event, run_id=run_id, step=step, agent_id=agent_id, event_type="email_set_body", title="Apply email body", detail=f"{len(body)} characters", data={"tool_id": "mailer.report_send", "typed_preview": typed_preview or body})
    _emit_parent_step_event(on_event=on_event, run_id=run_id, step=step, agent_id=agent_id, event_type="email_ready_to_send", title="Dispatching cited email", detail=recipient, data={"tool_id": "mailer.report_send", "typed_preview": typed_preview or body})
    _emit_parent_step_event(on_event=on_event, run_id=run_id, step=step, agent_id=agent_id, event_type="email_click_send", title="Click Send", detail="Submitting message to mailer service", data={"tool_id": "mailer.report_send"})

    delivery_response = ops.send_report_email(to_email=recipient, subject=subject, body_text=body)
    message_id = str(delivery_response.get("id") or "").strip()
    if run_id:
        try:
            from api.services.agents.workflow_context import WorkflowRunContext
            WorkflowRunContext(run_id).write(
                f"__delivery_sent_{step.step_id}",
                {"recipient": recipient, "subject": subject, "body": body, "message_id": message_id},
            )
        except Exception:
            pass
    _emit_parent_step_event(on_event=on_event, run_id=run_id, step=step, agent_id=agent_id, event_type="email_sent", title="Cited email sent", detail=message_id or recipient, data={"tool_id": "mailer.report_send", "recipient": recipient, "subject": subject})
    _emit_parent_step_event(on_event=on_event, run_id=run_id, step=step, agent_id=agent_id, event_type="tool_completed", title="Email delivery completed", detail=f"Sent cited email to {recipient}", data={"tool_id": "mailer.report_send", "recipient": recipient, "subject": subject})
    return f"To: {recipient}\nSubject: {subject}\n\n{body}"


def _run_grounded_email_draft_step(
    *,
    step: WorkflowStep,
    step_inputs: dict[str, Any],
    tenant_id: str,
    run_id: str,
    on_event: Optional[Any] = None,
    ops: Any,
) -> str:
    from api.services.agents.definition_store import get_agent, load_schema
    from api.services.agents.runner import run_agent_task

    record = get_agent(tenant_id, step.agent_id)
    if not record:
        raise ValueError(f"Agent '{step.agent_id}' not found in tenant '{tenant_id}'.")
    schema = load_schema(record)

    system_prompt = ops._inject_evolution_overlay(tenant_id, step.agent_id, schema.system_prompt or "")
    artifact = _choose_delivery_artifact(step_inputs, step=step)
    recipient = (
        _extract_email_from_text(step_inputs.get("to"))
        or _extract_email_from_text(step_inputs.get("recipient"))
        or _extract_email_from_text(step_inputs.get("delivery_email"))
        or _extract_email_from_text(step.description)
    )
    citation_section = _extract_terminal_citation_section(artifact)
    source_body = artifact[: artifact.rfind(citation_section)].rstrip() if citation_section else artifact
    required_subject = _derive_grounded_email_subject(artifact=artifact, step_inputs=step_inputs, step=step)

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

    def _run(prompt_text: str) -> str:
        result_parts: list[str] = []
        for chunk in run_agent_task(
            prompt_text,
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
        return "".join(result_parts).strip()

    raw_result = _normalize_grounded_email_result(result=_run(prompt), required_subject=required_subject, citation_section=citation_section)
    if _is_valid_grounded_email_draft(raw_result, citation_section=citation_section):
        return raw_result

    repair_prompt = "\n\n".join(
        part for part in (
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
        ) if part
    )
    repaired_result = _normalize_grounded_email_result(result=_run(repair_prompt), required_subject=required_subject, citation_section=citation_section)
    if _is_valid_grounded_email_draft(repaired_result, citation_section=citation_section):
        return repaired_result

    greeting = f"Hi {recipient}," if recipient else "Hi,"
    fallback_body = source_body.strip()
    if citation_section and citation_section not in fallback_body:
        fallback_body = f"{fallback_body}\n\n{citation_section}"
    return f"Subject: {required_subject}\n\n{greeting}\n\n{fallback_body}\n\nBest regards,\nMaia".strip()
