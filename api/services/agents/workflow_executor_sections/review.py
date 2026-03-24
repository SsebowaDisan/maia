from __future__ import annotations

import re
import time
from typing import Any, Optional

from api.schemas.workflow_definition import WorkflowStep

from .common import (
    _CITATION_LINE_RE,
    _CITATION_SECTION_HEADING_RE,
    _count_inline_citation_markers,
    _emit,
    _has_strong_citation_scaffold,
    _has_terminal_citation_section,
    _INLINE_CITATION_RE,
    _looks_like_customer_facing_output,
    _looks_like_email_draft,
    _step_tool_ids,
    logger,
)


def _rewrite_stage_output_with_llm(
    *,
    current_output: str,
    instruction: str,
    original_task: str,
    step_description: str,
    tenant_id: str,
) -> str:
    try:
        from api.services.agent.llm_runtime import call_text_response
        prompt = (
            "Revise this completed workflow-stage deliverable.\n"
            "Return only the revised deliverable body.\n"
            "Rules:\n"
            "- Use only the information already present in the current deliverable.\n"
            "- Preserve supported claims, inline citations, markdown links, and the source section when present.\n"
            "- If a citation, URL, or numbered reference cannot be supported from the current deliverable, remove or soften the unsupported claim instead of inventing a repaired source.\n"
            "- Do not invent new sources, facts, or actions.\n"
            "- Do not mention the review process, feedback process, or internal workflow.\n"
            "- Improve attribution clarity, structure, readability, and citation hygiene.\n"
            "- For a standard research brief or research-plus-email deliverable, prefer compact executive depth; roughly 1000-1500 characters is usually appropriate unless the evidence genuinely requires more.\n\n"
            f"Original task:\n{original_task[:1200]}\n\n"
            f"Stage objective:\n{step_description[:1200]}\n\n"
            f"Revision instruction:\n{instruction[:1600]}\n\n"
            f"Current deliverable:\n{current_output[:16000]}"
        )
        rewritten = call_text_response(
            system_prompt="You revise workflow-stage deliverables for accuracy, attribution clarity, and premium readability. Return only the revised deliverable.",
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
    if not raw or "subject:" in raw.lower() or _looks_like_email_draft(raw):
        return False
    if not _has_strong_citation_scaffold(raw):
        return False
    heading_count = len(re.findall(r"(?m)^##\s+", raw))
    return len(raw) > 1800 or heading_count > 2 or "## recommended next steps" in raw.lower()


def _compact_research_brief_output(
    *,
    step: WorkflowStep | None,
    step_inputs: dict[str, Any],
    result: Any,
    tenant_id: str,
    ops: Any,
) -> Any:
    if not _should_compact_research_brief(step, result):
        return result

    raw = str(result or "").strip()
    compacted = ops._rewrite_stage_output_with_llm(
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
    compacted = ops._verify_and_clean_citations(_normalize_numbered_citation_section(str(compacted or "").strip()), tenant_id)
    if _has_strong_citation_scaffold(compacted) and len(compacted) > 1700:
        retry = ops._rewrite_stage_output_with_llm(
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
        retry = ops._verify_and_clean_citations(_normalize_numbered_citation_section(str(retry or "").strip()), tenant_id)
        if _has_strong_citation_scaffold(retry) and len(retry) < len(compacted):
            compacted = retry
    return compacted if _has_strong_citation_scaffold(compacted) and len(compacted) < len(raw) else raw


def _normalize_numbered_citation_section(text: str) -> str:
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
        entries.append({"old_idx": old_idx, "remainder": remainder, "url": url})

    if not entries:
        return body

    body_refs = [int(match.group(1)) for match in _INLINE_CITATION_RE.finditer(body)]
    referenced = set(body_refs)
    kept_entries = [entry for entry in entries if (not referenced or entry["old_idx"] in referenced)]
    if not kept_entries:
        return re.sub(r"\s{2,}", " ", _INLINE_CITATION_RE.sub("", body)).strip()

    old_to_new = {entry["old_idx"]: idx for idx, entry in enumerate(kept_entries, start=1)}
    normalized_body = _INLINE_CITATION_RE.sub(lambda match: f"[{old_to_new.get(int(match.group(1)))}]" if old_to_new.get(int(match.group(1))) else "", body)
    normalized_body = re.sub(r"\s+\.", ".", normalized_body)
    normalized_body = re.sub(r"\s+,", ",", normalized_body)
    normalized_body = re.sub(r"\[\](?:\s*\[\])+", "", normalized_body)
    normalized_body = re.sub(r"\n{3,}", "\n\n", normalized_body).strip()

    normalized_rows = []
    for new_idx, entry in enumerate(kept_entries, start=1):
        remainder = re.sub(r"^\[\d+\]\s*", "", entry["remainder"]).strip()
        if remainder:
            normalized_rows.append(f"- [{new_idx}] {remainder}")
    if not normalized_rows:
        return normalized_body
    return f"{normalized_body}\n\n## Evidence Citations\n" + "\n".join(normalized_rows)


def _is_citation_hygiene_dialogue(*, interaction_type: Any, interaction_label: Any, operation_label: Any, question: Any, reason: Any) -> bool:
    normalized_turn = str(ops_normalize_dialogue_turn_type(interaction_type)).strip()
    if "citation" in normalized_turn or "reference" in normalized_turn:
        return True
    haystack = " ".join(str(part or "").strip().lower() for part in (interaction_label, operation_label, question, reason) if str(part or "").strip())
    return bool(haystack) and any(marker in haystack for marker in ("citation", "citations", "evidence citations", "source numbering", "reference format", "formatting consistency", "source details", "complete incomplete arxiv citation"))


def ops_normalize_dialogue_turn_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return "_".join(part for part in raw.replace("-", "_").split("_") if part) or "question"


def _should_skip_dialogue_need_for_reviewed_output(*, output: str, interaction_type: Any, interaction_label: Any, operation_label: Any, question: Any, reason: Any) -> bool:
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


def _seconds_until_deadline(step_deadline_ts: float | None, *, now_fn=time.monotonic) -> float | None:
    if not step_deadline_ts:
        return None
    return max(0.0, float(step_deadline_ts) - now_fn())


def _should_skip_post_review_collaboration(*, step_deadline_ts: float | None, minimum_seconds_required: float, now_fn=time.monotonic) -> bool:
    remaining = _seconds_until_deadline(step_deadline_ts, now_fn=now_fn)
    return remaining is not None and remaining < float(minimum_seconds_required)


def _run_brain_review(
    step: WorkflowStep,
    result: Any,
    step_inputs: dict[str, Any],
    tenant_id: str,
    run_id: str,
    on_event: Optional[Any],
    step_deadline_ts: float | None = None,
    ops: Any | None = None,
) -> Any:
    if step.step_type not in ("agent", ""):
        return result
    text_result = str(result or "").strip() or str(step.description or step.step_id or "").strip()
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
            return str(ops._run_agent_step(agent_id, {"message": prompt}, tenant_id, run_id=run_id, on_event=on_event) or "") if agent_id else ""

        def _revise_output(feedback: str, current_output: str, round_num: int) -> str:
            revised = ops._rewrite_stage_output_with_llm(
                current_output=current_output,
                instruction=f"Revision round {round_num}/3. Address this feedback precisely:\n{feedback}",
                original_task=original_task,
                step_description=str(step.description or ""),
                tenant_id=tenant_id,
            )
            return ops._verify_and_clean_citations(_normalize_numbered_citation_section(revised), tenant_id)

        def _answer_question(question: str, current_output: str, round_num: int) -> str:
            revised = ops._rewrite_stage_output_with_llm(
                current_output=current_output,
                instruction=(
                    f"Question round {round_num}/3. Revise the deliverable so it directly answers this reviewer question while preserving supported citations:\n{question}"
                ),
                original_task=original_task,
                step_description=str(step.description or ""),
                tenant_id=tenant_id,
            )
            return ops._verify_and_clean_citations(_normalize_numbered_citation_section(revised), tenant_id)

        def _answer_as_teammate(target_agent: str, prompt: str) -> str:
            try:
                from api.services.agent.llm_runtime import call_text_response
                from api.services.agents.workflow_context import WorkflowRunContext
                roster_map: dict[str, dict[str, Any]] = {}
                if run_id:
                    raw_roster = WorkflowRunContext(run_id).read("__workflow_agent_roster")
                    if isinstance(raw_roster, list):
                        for row in raw_roster:
                            if isinstance(row, dict):
                                roster_map[str(row.get("agent_id") or row.get("id") or "").strip()] = row
                target_meta = roster_map.get(str(target_agent or "").strip(), {})
                target_name = str(target_meta.get("name") or target_meta.get("role") or target_agent or "Teammate").strip()
                response = call_text_response(
                    system_prompt=(
                        f"You are {target_name}, a workflow teammate contributing a short, evidence-grounded reply. Answer only from the current shared output and task context. Do not use tools, do not search, do not mention internal orchestration, and do not invent new evidence."
                    ),
                    user_prompt=(
                        f"Original task:\n{original_task[:1200]}\n\nCurrent stage objective:\n{str(step.description or '')[:1200]}\n\nCurrent reviewed draft:\n{reviewed_output[:5000]}\n\nTeammate request:\n{prompt[:2400]}"
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
                run_agent_fn=lambda prompt: _run_agent_as(str(step.agent_id or step.step_id), prompt),
                revise_output_fn=_revise_output,
                answer_question_fn=_answer_question,
            )
            if review_history:
                revisions = sum(1 for r in review_history if r.get("decision") == "revise")
                questions = sum(1 for r in review_history if r.get("decision") == "question")
                if revisions or questions:
                    _emit(on_event, {"event_type": "brain_review_summary", "step_id": step.step_id, "data": {"revisions": revisions, "questions": questions, "rounds": len(review_history)}})
            if _review_exhausted_without_proceed(review_history):
                _emit(on_event, {"event_type": "brain_halt", "title": f"Brain review capped for {step.agent_id or step.step_id}", "detail": "Proceeding with the best cleaned draft after max review rounds.", "data": {"step_id": step.step_id, "agent_id": step.agent_id or step.step_id, "run_id": run_id, "reason": "max_review_rounds_reached"}})
                return ops._verify_and_clean_citations(_normalize_numbered_citation_section(reviewed_output), tenant_id)

        reviewed_output = ops._verify_and_clean_citations(_normalize_numbered_citation_section(reviewed_output), tenant_id)
        if dialogue_enabled and ops._should_skip_post_review_collaboration(step_deadline_ts=step_deadline_ts, minimum_seconds_required=150.0):
            _emit(on_event, {"event_type": "brain_collaboration_skipped", "title": f"Finalizing {step.agent_id or step.step_id}", "detail": "Skipping extra teammate discussion to preserve step completion time.", "data": {"step_id": step.step_id, "agent_id": step.agent_id or step.step_id, "run_id": run_id, "reason": "step_deadline_near"}})
            return reviewed_output

        if dialogue_enabled:
            try:
                from api.services.agent.brain.team_chat import get_team_chat_service
                from api.services.agents.workflow_context import WorkflowRunContext
                roster = WorkflowRunContext(run_id).read("__workflow_agent_roster") if run_id else []
                if roster and len(roster) > 1:
                    conv = get_team_chat_service().start_conversation(run_id=run_id, topic=original_task, initiated_by=step.agent_id or step.step_id, step_id=step.step_id, on_event=on_event)
                    get_team_chat_service().brain_facilitates(conversation=conv, step_output=reviewed_output, original_task=original_task, agents=roster, step_id=step.step_id, tenant_id=tenant_id, on_event=on_event)
            except Exception as exc:
                logger.debug("Team chat skipped: %s", exc)
            try:
                reviewed_output = ops._run_dialogue_detection(step=step, output=reviewed_output, tenant_id=tenant_id, run_id=run_id, on_event=on_event, run_agent_for_agent_fn=_answer_as_teammate)
            except Exception as exc:
                logger.debug("Dialogue detection skipped inside brain review: %s", exc)

        return ops._verify_and_clean_citations(_normalize_numbered_citation_section(reviewed_output), tenant_id)
    except Exception as exc:
        logger.debug("Brain review skipped: %s", exc)
        return result
