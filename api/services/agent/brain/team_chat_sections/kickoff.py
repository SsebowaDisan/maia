from __future__ import annotations

from typing import Callable, Optional

from api.services.agent.brain.team_chat_guidance import (
    anti_repetition_prompt,
    recent_message_lines,
)

from .llm import _call_json_llm
from .models import ChatMessage, TeamConversation
from .participants import (
    _normalize_agents,
    _preferred_watcher_agent,
    _resolve_facilitator_agent,
    _resolve_participants,
)


def _thread_id(conversation: TeamConversation, step_id: str, lane: str) -> str:
    step_token = str(step_id or "general").strip() or "general"
    lane_token = str(lane or "thread").strip() or "thread"
    return f"{conversation.conversation_id}:{step_token}:{lane_token}"


def kickoff_step(
    service,
    *,
    conversation: TeamConversation,
    current_agent: str,
    step_description: str,
    original_task: str,
    agents: list[dict[str, str]],
    step_id: str = "",
    tenant_id: str = "",
    on_event: Optional[Callable] = None,
) -> list[ChatMessage]:
    """Emit a short, real teammate exchange before a step starts running."""
    normalized_agents = _normalize_agents(agents)
    if len(normalized_agents) < 2:
        return []

    current_candidates = _resolve_participants(
        requested=[current_agent],
        normalized_agents=normalized_agents,
        limit=1,
    )
    current_id = current_candidates[0] if current_candidates else ""
    if not current_id:
        return []

    agent_map = {str(row["id"]).strip(): row for row in normalized_agents}
    current_info = agent_map.get(current_id)
    if not current_info:
        return []
    facilitator = _resolve_facilitator_agent(normalized_agents)
    facilitator_id = str(facilitator.get("id")).strip() if facilitator else "brain"
    facilitator_name = (
        str(facilitator.get("name")).strip() if facilitator else "Maia Brain"
    )
    facilitator_role = (
        str(facilitator.get("role")).strip() if facilitator else "team_lead"
    )

    teammate_pool = [
        row for row in normalized_agents if str(row["id"]).strip() != current_id
    ]
    if not teammate_pool:
        return []

    teammate_roster = ", ".join(
        f"{row.get('name', row.get('id', 'Agent'))} ({row.get('role', 'agent')})"
        for row in teammate_pool
    )
    recent_lines = recent_message_lines(conversation.messages, limit=6)
    kickoff_plan = _call_json_llm(
        system_prompt=(
            "You are Maia Brain opening a real team thread before work starts. "
            "Return only short teammate-style chat lines. "
            "Do not explain the workflow, justify the step, or narrate process."
        ),
        user_prompt=(
            f"Overall task: {original_task}\n\n"
            f"Current step: {step_description}\n"
            f"Current assignee: {current_info.get('name', current_id)} ({current_info.get('role', 'agent')})\n"
            f"Other teammates: {teammate_roster}\n\n"
            "Return JSON only:\n"
            "{\n"
            '  "brain_message": "under 30 words",\n'
            '  "assignee_message": "under 24 words",\n'
            '  "watcher_agent": "one teammate id or name",\n'
            '  "watcher_message": "under 24 words",\n'
            '  "watcher_follow_up": "under 20 words",\n'
            '  "assignee_follow_up": "under 20 words"\n'
            "}\n"
            "Rules:\n"
            "- Sound like teammates in a work chat.\n"
            "- No methodology speeches. No explaining why the step exists.\n"
            "- Do not restate the step description verbatim.\n"
            "- Talk about the next concrete move, risk, evidence, or check.\n"
            "- The Brain line should assign a concrete outcome or risk to watch.\n"
            "- The assignee line should confirm the plan or ask one sharp question.\n"
            "- The watcher line should say what they will verify, challenge, or review.\n"
            "- The watcher follow-up should challenge an assumption, ask for evidence, or narrow scope.\n"
            "- The assignee follow-up should answer briefly or adjust the plan.\n"
            "- Keep every line direct and under the word limit.\n\n"
            f"{anti_repetition_prompt(recent_lines)}"
        ),
        tenant_id=tenant_id,
    )

    preferred_watcher = _preferred_watcher_agent(
        teammate_pool, exclude_id=facilitator_id
    )
    watcher_candidates = _resolve_participants(
        requested=[kickoff_plan.get("watcher_agent", "")],
        normalized_agents=teammate_pool,
        limit=1,
    )
    watcher_id = (
        watcher_candidates[0]
        if watcher_candidates
        else str((preferred_watcher or teammate_pool[0])["id"]).strip()
    )
    watcher_info = agent_map.get(watcher_id, preferred_watcher or teammate_pool[0])

    brain_message = " ".join(str(kickoff_plan.get("brain_message", "")).split()).strip()
    assignee_message = " ".join(
        str(kickoff_plan.get("assignee_message", "")).split()
    ).strip()
    watcher_message = " ".join(
        str(kickoff_plan.get("watcher_message", "")).split()
    ).strip()
    watcher_follow_up = " ".join(
        str(kickoff_plan.get("watcher_follow_up", "")).split()
    ).strip()
    assignee_follow_up = " ".join(
        str(kickoff_plan.get("assignee_follow_up", "")).split()
    ).strip()

    if not brain_message:
        brain_message = (
            f"{current_info.get('name', current_id)}, take this step: "
            f"{' '.join(str(step_description or original_task).split())[:160]}"
        )
    if not assignee_message:
        assignee_message = (
            "I'm taking first pass on the evidence and I'll flag anything weak before handoff."
        )
    if not watcher_message:
        watcher_message = (
            "I'm watching for unsupported claims or shaky assumptions before this moves forward."
        )
    if not watcher_follow_up:
        watcher_follow_up = (
            "Call out uncertain claims early so I can pressure-test them before handoff."
        )
    if not assignee_follow_up:
        assignee_follow_up = (
            "I'll keep the pass tight and surface the weak spots as soon as I hit them."
        )

    messages: list[ChatMessage] = []
    kickoff_thread_id = _thread_id(conversation, step_id, "kickoff")
    task_id = str(step_id or conversation.conversation_id).strip() or conversation.conversation_id
    task_title = " ".join(str(step_description or original_task or conversation.topic).split()).strip()
    messages.append(
        service.send_message(
            conversation=conversation,
            speaker_id=facilitator_id,
            speaker_name=facilitator_name,
            speaker_role=facilitator_role,
            content=brain_message,
            step_id=step_id,
            thread_id=kickoff_thread_id,
            task_id=task_id,
            task_title=task_title,
            message_type="message",
            mood="confident",
            mentions=[current_id],
            requires_ack=True,
            to_agent=current_id,
            on_event=on_event,
        )
    )
    messages.append(
        service.send_message(
            conversation=conversation,
            speaker_id=current_id,
            speaker_name=current_info.get("name", current_id),
            speaker_role=current_info.get("role", "agent"),
            content=assignee_message,
            step_id=step_id,
            thread_id=kickoff_thread_id,
            task_id=task_id,
            task_title=task_title,
            message_type="message",
            mood="curious",
            acked_by=[current_id],
            to_agent=facilitator_id,
            on_event=on_event,
        )
    )
    messages.append(
        service.send_message(
            conversation=conversation,
            speaker_id=watcher_id,
            speaker_name=watcher_info.get("name", watcher_id),
            speaker_role=watcher_info.get("role", "agent"),
            content=watcher_message,
            step_id=step_id,
            thread_id=kickoff_thread_id,
            task_id=task_id,
            task_title=task_title,
            message_type="message",
            mood="skeptical",
            mentions=[current_id],
            to_agent=current_id,
            on_event=on_event,
        )
    )
    messages.append(
        service.send_message(
            conversation=conversation,
            speaker_id=watcher_id,
            speaker_name=watcher_info.get("name", watcher_id),
            speaker_role=watcher_info.get("role", "agent"),
            content=watcher_follow_up,
            step_id=step_id,
            thread_id=kickoff_thread_id,
            task_id=task_id,
            task_title=task_title,
            message_type="message",
            mood="skeptical",
            mentions=[current_id],
            requires_ack=True,
            to_agent=current_id,
            on_event=on_event,
        )
    )
    messages.append(
        service.send_message(
            conversation=conversation,
            speaker_id=current_id,
            speaker_name=current_info.get("name", current_id),
            speaker_role=current_info.get("role", "agent"),
            content=assignee_follow_up,
            step_id=step_id,
            thread_id=kickoff_thread_id,
            task_id=task_id,
            task_title=task_title,
            message_type="message",
            mood="confident",
            acked_by=[current_id],
            mentions=[watcher_id],
            to_agent=watcher_id,
            on_event=on_event,
        )
    )
    return messages
