from __future__ import annotations

import logging
from typing import Callable, Optional

from api.services.agent.brain.team_chat_guidance import (
    anti_repetition_prompt,
    recent_message_lines,
)

from .llm import (
    PERSONALITY_PROMPT,
    _call_agent_llm,
    _call_json_llm,
    _get_personality,
    _infer_mood_from_response,
)
from .models import ChatMessage, TeamConversation
from .participants import (
    _normalize_agents,
    _resolve_facilitator_agent,
    _resolve_participants,
)

logger = logging.getLogger(__name__)


def _thread_id(conversation: TeamConversation, step_id: str, lane: str) -> str:
    step_token = str(step_id or "general").strip() or "general"
    lane_token = str(lane or "thread").strip() or "thread"
    return f"{conversation.conversation_id}:{step_token}:{lane_token}"


def brain_facilitates(
    service,
    *,
    conversation: TeamConversation,
    step_output: str,
    original_task: str,
    agents: list[dict[str, str]],
    step_id: str = "",
    tenant_id: str = "",
    on_event: Optional[Callable] = None,
) -> list[ChatMessage]:
    """Brain facilitates a multi-round team discussion with tension and personality."""
    normalized_agents = _normalize_agents(agents)
    if len(normalized_agents) < 2:
        return []

    discussion_recent_lines = recent_message_lines(conversation.messages, limit=8)
    agent_roster = ", ".join(
        f"{a.get('name', a.get('id', 'Agent'))} ({a.get('role', 'agent')})"
        for a in normalized_agents
    )

    decision = _call_json_llm(
        system_prompt=(
            "You are Maia Brain in a live team chat. "
            "Create a useful debate, not a memo. "
            "Your opening should sound like a teammate pulling others into a thread."
        ),
        user_prompt=(
            f"Task: {original_task}\n\n"
            f"Output to review:\n{step_output[:2500]}\n\n"
            f"Team: {agent_roster}\n\n"
            "Decide:\n"
            "1. Does this need discussion? (yes if there's anything debatable, unclear, improvable, or worth a second opinion)\n"
            "2. Which 2-3 team members should weigh in?\n"
            "3. What provocative question should you ask to spark real discussion?\n"
            "   (not 'what do you think?' but a specific challenge)\n\n"
            "JSON: {"
            '"needs_discussion": bool, '
            '"participants": ["id1", "id2"], '
            '"topic": "specific debate topic", '
            '"opening_message": "your provocative opening (under 24 words)", '
            '"challenge": "the specific thing you want them to debate (under 16 words)"'
            "}\n\n"
            f"{anti_repetition_prompt(discussion_recent_lines)}"
        ),
        tenant_id=tenant_id,
    )

    if not decision.get("needs_discussion", False):
        return []

    messages: list[ChatMessage] = []
    topic = str(decision.get("topic", original_task[:200]))
    conversation.topic = topic
    discussion_thread_id = _thread_id(conversation, step_id, "discussion")
    task_id = str(step_id or conversation.conversation_id).strip() or conversation.conversation_id
    task_title = " ".join(str(topic or original_task or conversation.topic).split()).strip()
    agent_map = {str(a["id"]).strip(): a for a in normalized_agents}
    facilitator = _resolve_facilitator_agent(normalized_agents)
    facilitator_id = str(facilitator.get("id")).strip() if facilitator else "brain"
    facilitator_name = (
        str(facilitator.get("name")).strip() if facilitator else "Maia Brain"
    )
    facilitator_role = (
        str(facilitator.get("role")).strip() if facilitator else "team_lead"
    )
    participants = _resolve_participants(
        requested=decision.get("participants", []),
        normalized_agents=normalized_agents,
        limit=4,
    )
    if not participants:
        return []

    opening = str(
        decision.get(
            "opening_message",
            f"Team, let's review this. {decision.get('challenge', '')}",
        )
    )
    brain_msg = service.send_message(
        conversation=conversation,
        speaker_id=facilitator_id,
        speaker_name=facilitator_name,
        speaker_role=facilitator_role,
        content=opening,
        step_id=step_id,
        thread_id=discussion_thread_id,
        task_id=task_id,
        task_title=task_title,
        message_type="message",
        mood="curious",
        mentions=list(participants),
        to_agent="team",
        on_event=on_event,
    )
    messages.append(brain_msg)
    challenge = str(decision.get("challenge", topic))

    round1_messages: list[ChatMessage] = []
    for idx, pid in enumerate(participants):
        agent_info = agent_map[pid]
        personality = _get_personality(idx)
        try:
            service.send_message(
                conversation=conversation,
                speaker_id=pid,
                speaker_name=agent_info.get("name", pid),
                speaker_role=agent_info.get("role", "agent"),
                content="thinking...",
                step_id=step_id,
                thread_id=discussion_thread_id,
                task_id=task_id,
                task_title=task_title,
                message_type="thinking",
                mood="curious",
                mentions=[facilitator_id],
                to_agent=facilitator_id,
                on_event=on_event,
            )

            response = _call_agent_llm(
                system_prompt=PERSONALITY_PROMPT.format(
                    name=agent_info.get("name", pid),
                    role=agent_info.get("role", "agent"),
                    **personality,
                ),
                user_prompt=(
                    f"The Brain asked: {challenge}\n\n"
                    f"Context - the output being discussed:\n{step_output[:1500]}\n\n"
                    "Reply like a teammate in a live thread. "
                    "1-3 short sentences. One concrete point. "
                    "If you disagree, say exactly what is wrong. "
                    "If you need proof, ask for it directly. "
                    "Do not explain the workflow or the user goal. "
                    "Do not give a mini essay or justify why this step exists.\n\n"
                    f"{anti_repetition_prompt(recent_message_lines(messages, limit=8))}"
                ),
                tenant_id=tenant_id,
                max_tokens=150,
            )

            mood = _infer_mood_from_response(response)
            agent_msg = service.send_message(
                conversation=conversation,
                speaker_id=pid,
                speaker_name=agent_info.get("name", pid),
                speaker_role=agent_info.get("role", "agent"),
                content=response,
                step_id=step_id,
                thread_id=discussion_thread_id,
                task_id=task_id,
                task_title=task_title,
                reply_to_id=brain_msg.message_id,
                message_type="message",
                mood=mood,
                acked_by=[pid],
                mentions=[facilitator_id],
                to_agent=facilitator_id,
                on_event=on_event,
            )
            messages.append(agent_msg)
            round1_messages.append(agent_msg)
        except Exception as exc:
            logger.warning("Agent %s failed to respond: %s", pid, exc)

    if len(round1_messages) < 2:
        return messages

    history_text = "\n".join(f"{m.speaker_name}: {m.content}" for m in round1_messages)
    followup = _call_json_llm(
        system_prompt=(
            "You are the Brain facilitating a debate. "
            "Find the most interesting disagreement or tension in the discussion "
            "and ask a specific agent to respond to another agent's point."
        ),
        user_prompt=(
            f"Discussion so far:\n{history_text}\n\n"
            "Pick the most interesting tension or disagreement. "
            "Ask one agent to respond directly to another's specific point.\n\n"
            "JSON: {"
            '"has_tension": bool, '
            '"target_agent": "who should respond", '
            '"challenge_from": "whose point they should address", '
            '"followup_question": "your pointed question (under 30 words)"'
            "}"
        ),
        tenant_id=tenant_id,
    )

    if followup.get("has_tension", False):
        target_candidates = _resolve_participants(
            requested=[followup.get("target_agent", "")],
            normalized_agents=normalized_agents,
            limit=1,
        )
        challenge_candidates = _resolve_participants(
            requested=[followup.get("challenge_from", "")],
            normalized_agents=normalized_agents,
            limit=1,
        )
        target = target_candidates[0] if target_candidates else ""
        challenge_from = challenge_candidates[0] if challenge_candidates else ""
        followup_question = str(followup.get("followup_question", ""))

        if target in agent_map and followup_question:
            poke_msg = service.send_message(
                conversation=conversation,
                speaker_id=facilitator_id,
                speaker_name=facilitator_name,
                speaker_role=facilitator_role,
                content=followup_question,
                step_id=step_id,
                thread_id=discussion_thread_id,
                task_id=task_id,
                task_title=task_title,
                message_type="message",
                mood="curious",
                mentions=[target, challenge_from] if challenge_from else [target],
                requires_ack=True,
                to_agent=target,
                on_event=on_event,
            )
            messages.append(poke_msg)

            target_info = agent_map[target]
            target_personality = _get_personality(
                participants.index(target) if target in participants else 0
            )
            full_history = "\n".join(f"{m.speaker_name}: {m.content}" for m in messages)

            service.send_message(
                conversation=conversation,
                speaker_id=target,
                speaker_name=target_info.get("name", target),
                speaker_role=target_info.get("role", "agent"),
                content="thinking...",
                step_id=step_id,
                thread_id=discussion_thread_id,
                task_id=task_id,
                task_title=task_title,
                message_type="thinking",
                mood="curious",
                mentions=[facilitator_id],
                to_agent=facilitator_id,
                on_event=on_event,
            )

            response2 = _call_agent_llm(
                system_prompt=PERSONALITY_PROMPT.format(
                    name=target_info.get("name", target),
                    role=target_info.get("role", "agent"),
                    **target_personality,
                ),
                user_prompt=(
                    f"Conversation:\n{full_history}\n\n"
                    f"The Brain just asked you: {followup_question}\n\n"
                    f"Respond directly to {challenge_from}'s point. "
                    "1-3 short sentences. "
                    "Agree, push back, or ask for evidence. "
                    "Do not summarize the process.\n\n"
                    f"{anti_repetition_prompt(recent_message_lines(messages, limit=8))}"
                ),
                tenant_id=tenant_id,
                max_tokens=150,
            )

            mood2 = _infer_mood_from_response(response2)
            resp2_msg = service.send_message(
                conversation=conversation,
                speaker_id=target,
                speaker_name=target_info.get("name", target),
                speaker_role=target_info.get("role", "agent"),
                content=response2,
                step_id=step_id,
                thread_id=discussion_thread_id,
                task_id=task_id,
                task_title=task_title,
                reply_to_id=poke_msg.message_id,
                message_type="message",
                mood=mood2,
                acked_by=[target],
                mentions=[challenge_from] if challenge_from else [facilitator_id],
                to_agent=challenge_from or "brain",
                on_event=on_event,
            )
            messages.append(resp2_msg)

            if challenge_from in agent_map:
                from_info = agent_map[challenge_from]
                reaction_response = _call_agent_llm(
                    system_prompt=(
                        f"You are {from_info.get('name', challenge_from)}. "
                        "React briefly to what was just said about your point."
                    ),
                    user_prompt=(
                        f"{target_info.get('name', target)} just said: {response2}\n\n"
                        "React in ONE short sentence. Agree, push back, or acknowledge. "
                        "Keep it like a real team thread, not a report.\n\n"
                        f"{anti_repetition_prompt(recent_message_lines(messages, limit=8))}"
                    ),
                    tenant_id=tenant_id,
                    max_tokens=60,
                )
                react_msg = service.send_message(
                    conversation=conversation,
                    speaker_id=challenge_from,
                    speaker_name=from_info.get("name", challenge_from),
                    speaker_role=from_info.get("role", "agent"),
                    content=reaction_response,
                    step_id=step_id,
                    thread_id=discussion_thread_id,
                    task_id=task_id,
                    task_title=task_title,
                    reply_to_id=resp2_msg.message_id,
                    message_type="message",
                    mood=_infer_mood_from_response(reaction_response),
                    mentions=[target],
                    to_agent=target,
                    on_event=on_event,
                )
                messages.append(react_msg)

    full_history = "\n".join(
        f"{m.speaker_name}: {m.content}"
        for m in messages
        if m.message_type == "message"
    )
    summary = _call_agent_llm(
        system_prompt=(
            "You are Maia Brain wrapping up a team thread. "
            "Be decisive and short. "
            "State the decision and the next action in natural chat language."
        ),
        user_prompt=f"Discussion:\n{full_history}\n\nWrap up decisively.",
        tenant_id=tenant_id,
        max_tokens=100,
    )

    if summary.strip():
        summary_msg = service.send_message(
            conversation=conversation,
            speaker_id=facilitator_id,
            speaker_name=facilitator_name,
            speaker_role=facilitator_role,
            content=summary,
            step_id=step_id,
            thread_id=discussion_thread_id,
            task_id=task_id,
            task_title=task_title,
            message_type="summary",
            mood="confident",
            mentions=list(participants),
            to_agent="team",
            on_event=on_event,
        )
        messages.append(summary_msg)

    return messages
