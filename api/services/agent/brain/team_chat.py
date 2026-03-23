"""Agent Team Chat — LLM-driven conversations between agents.

Agents talk like real teammates with distinct personalities.
The Brain creates productive tension — challenges, questions, debates.
Messages are short and punchy. Agents think out loud before responding.
The user watches live in the Theatre like watching a team Slack channel.

No hardcoded routing. No keyword matching. Pure LLM-driven conversation.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Optional

from .team_chat_guidance import anti_repetition_prompt, recent_message_lines

logger = logging.getLogger(__name__)

MAX_CHAT_TURNS = 16


# ── Message types ─────────────────────────────────────────────────────────────

class ChatMessage:
    """A single message in a team conversation."""

    __slots__ = (
        "message_id", "conversation_id", "run_id", "step_id",
        "speaker_id", "speaker_name", "speaker_role",
        "speaker_avatar", "speaker_color",
        "content", "reply_to_id", "timestamp",
        "message_type", "mood", "reaction_to_id", "reaction",
    )

    _COLORS = [
        "#ef4444", "#3b82f6", "#10b981", "#f59e0b",
        "#8b5cf6", "#ec4899", "#06b6d4", "#f97316",
    ]
    _color_map: dict[str, str] = {}
    _color_idx = 0

    def __init__(
        self,
        *,
        conversation_id: str,
        run_id: str,
        step_id: str = "",
        speaker_id: str,
        speaker_name: str = "",
        speaker_role: str = "",
        content: str,
        reply_to_id: str = "",
        message_type: str = "message",
        mood: str = "neutral",
        reaction_to_id: str = "",
        reaction: str = "",
    ):
        self.message_id = f"msg_{int(time.time() * 1000)}_{speaker_id[:6]}"
        self.conversation_id = conversation_id
        self.run_id = run_id
        self.step_id = step_id
        self.speaker_id = speaker_id
        self.speaker_name = speaker_name or speaker_id
        self.speaker_role = speaker_role
        self.content = content
        self.reply_to_id = reply_to_id
        self.timestamp = time.time()
        self.message_type = message_type  # message | thinking | searching | reaction | summary
        self.mood = mood  # neutral | curious | confident | skeptical | excited | concerned
        self.reaction_to_id = reaction_to_id
        self.reaction = reaction  # agree | disagree | interesting | question | good_point
        if speaker_id not in ChatMessage._color_map:
            ChatMessage._color_map[speaker_id] = ChatMessage._COLORS[
                ChatMessage._color_idx % len(ChatMessage._COLORS)
            ]
            ChatMessage._color_idx += 1
        self.speaker_color = ChatMessage._color_map[speaker_id]
        self.speaker_avatar = (speaker_name or speaker_id or "?")[0].upper()

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "speaker_id": self.speaker_id,
            "speaker_name": self.speaker_name,
            "speaker_role": self.speaker_role,
            "speaker_avatar": self.speaker_avatar,
            "speaker_color": self.speaker_color,
            "content": self.content,
            "reply_to_id": self.reply_to_id,
            "timestamp": self.timestamp,
            "message_type": self.message_type,
            "mood": self.mood,
            "reaction_to_id": self.reaction_to_id,
            "reaction": self.reaction,
        }


class TeamConversation:
    """A conversation thread between agents."""

    def __init__(self, *, conversation_id: str, run_id: str, topic: str = ""):
        self.conversation_id = conversation_id
        self.run_id = run_id
        self.topic = topic
        self.messages: list[ChatMessage] = []
        self.started_at = time.time()

    def add(self, **kwargs: Any) -> ChatMessage:
        kwargs["conversation_id"] = self.conversation_id
        kwargs["run_id"] = self.run_id
        msg = ChatMessage(**kwargs)
        self.messages.append(msg)
        return msg


# ── Personality system ────────────────────────────────────────────────────────
# The LLM generates personalities, but we give it archetypes to riff on.

PERSONALITY_PROMPT = """You are {name}, a {role} on the team.

Your personality:
- Communication style: {style}
- When you agree: {agree_style}
- When you disagree: {disagree_style}
- Your quirk: {quirk}

Rules for this conversation:
1. Keep messages SHORT — 1-3 sentences max. This is chat, not email.
2. Think out loud — say "Hmm..." or "Let me check..." before big claims.
3. Use specific numbers and examples, not vague generalisations.
4. If you disagree, say so directly but respectfully.
5. If something surprises you, show it — "Wait, really?" or "That's unexpected."
6. Reference what teammates said — "@name good point about X, but..."
7. Don't repeat what others already said. Build on it or challenge it.
8. Do not open with filler or generic acknowledgements. Lead with the next concrete move, risk, evidence, or question.
"""

# Archetype pool — the LLM will pick from these to create personality variety
PERSONALITY_ARCHETYPES = [
    {
        "style": "Direct and data-driven. You lead with numbers.",
        "agree_style": "You nod and add a supporting data point.",
        "disagree_style": "You say 'The data tells a different story' and show evidence.",
        "quirk": "You always quantify things — 'that's roughly a 23% improvement'.",
    },
    {
        "style": "Curious and questioning. You ask 'why' a lot.",
        "agree_style": "You agree but immediately ask a follow-up question.",
        "disagree_style": "You ask 'Have we considered...' and propose alternatives.",
        "quirk": "You spot edge cases others miss.",
    },
    {
        "style": "Concise and action-oriented. You cut to what matters.",
        "agree_style": "You say 'Agreed' and immediately suggest next steps.",
        "disagree_style": "You say 'That won't work because...' with a concrete reason.",
        "quirk": "You always end with a clear action item.",
    },
    {
        "style": "Thoughtful and thorough. You consider multiple angles.",
        "agree_style": "You agree and add context others might have missed.",
        "disagree_style": "You say 'I see it differently' and explain your reasoning.",
        "quirk": "You draw connections between unrelated findings.",
    },
    {
        "style": "Enthusiastic and creative. You get excited about possibilities.",
        "agree_style": "You build on the idea with a creative extension.",
        "disagree_style": "You say 'What if we tried it this way instead' with an alternative.",
        "quirk": "You use analogies to explain complex things.",
    },
    {
        "style": "Skeptical and rigorous. You stress-test everything.",
        "agree_style": "You say 'That checks out' only after verifying.",
        "disagree_style": "You say 'Hold on, that assumption doesn't hold because...'",
        "quirk": "You always ask 'What could go wrong?'",
    },
]


def _get_personality(agent_idx: int) -> dict[str, str]:
    return PERSONALITY_ARCHETYPES[agent_idx % len(PERSONALITY_ARCHETYPES)]


def _humanize_agent_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "Agent"
    return text.replace("_", " ").replace("-", " ").strip().title() or text


def _normalize_agents(agents: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in agents:
        if not isinstance(row, dict):
            continue
        agent_id = str(
            row.get("id")
            or row.get("agent_id")
            or row.get("name")
            or ""
        ).strip()
        if not agent_id:
            continue
        key = agent_id.lower()
        if key in seen:
            continue
        seen.add(key)
        name = str(row.get("name") or "").strip() or _humanize_agent_id(agent_id)
        role = str(row.get("role") or "").strip() or "agent"
        step_description = str(row.get("step_description") or "").strip()
        normalized.append(
            {
                "id": agent_id,
                "agent_id": agent_id,
                "name": name,
                "role": role,
                "step_description": step_description,
            }
        )
    return normalized


def _resolve_participants(
    *,
    requested: Any,
    normalized_agents: list[dict[str, str]],
    limit: int = 4,
) -> list[str]:
    if not normalized_agents:
        return []
    by_id = {str(agent["id"]).strip().lower(): str(agent["id"]).strip() for agent in normalized_agents}
    by_name = {str(agent["name"]).strip().lower(): str(agent["id"]).strip() for agent in normalized_agents}
    resolved: list[str] = []
    values = requested if isinstance(requested, list) else []
    for raw in values:
        token = str(raw or "").strip().lower()
        if not token:
            continue
        candidate = by_id.get(token) or by_name.get(token)
        if not candidate:
            for agent in normalized_agents:
                agent_id = str(agent["id"]).strip()
                agent_name = str(agent["name"]).strip().lower()
                if token in agent_id.lower() or token in agent_name:
                    candidate = agent_id
                    break
        if not candidate or candidate in resolved:
            continue
        resolved.append(candidate)
        if len(resolved) >= limit:
            break
    if resolved:
        return resolved
    return [str(agent["id"]).strip() for agent in normalized_agents[: min(limit, len(normalized_agents))]]


def _normalized_role(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _resolve_facilitator_agent(normalized_agents: list[dict[str, str]]) -> dict[str, str] | None:
    if not normalized_agents:
        return None
    ranked = sorted(
        normalized_agents,
        key=lambda row: (
            0
            if "supervisor" in _normalized_role(row.get("role", ""))
            else 1
            if _normalized_role(row.get("role", "")) in {"team lead", "lead"}
            else 2
            if "review" in _normalized_role(row.get("role", ""))
            else 3,
            str(row.get("name", "")),
        ),
    )
    best = ranked[0]
    role = _normalized_role(best.get("role", ""))
    if "supervisor" in role or role in {"team lead", "lead"} or "review" in role:
        return best
    return None


def _preferred_watcher_agent(
    candidates: list[dict[str, str]],
    *,
    exclude_id: str = "",
) -> dict[str, str] | None:
    pool = [row for row in candidates if str(row.get("id") or "").strip() != str(exclude_id or "").strip()]
    if not pool:
        return None
    ranked = sorted(
        pool,
        key=lambda row: (
            0
            if "review" in _normalized_role(row.get("role", ""))
            else 1
            if "analyst" in _normalized_role(row.get("role", ""))
            else 2
            if "supervisor" in _normalized_role(row.get("role", ""))
            else 3,
            str(row.get("name", "")),
        ),
    )
    return ranked[0]


# ── Main service ──────────────────────────────────────────────────────────────

class AgentTeamChatService:
    """Manages real-time agent conversations with personality and tension."""

    def __init__(self) -> None:
        self._conversations: dict[str, TeamConversation] = {}

    def start_conversation(
        self,
        *,
        run_id: str,
        topic: str,
        initiated_by: str,
        step_id: str = "",
        on_event: Optional[Callable] = None,
    ) -> TeamConversation:
        conv_id = f"conv_{int(time.time() * 1000)}"
        conv = TeamConversation(conversation_id=conv_id, run_id=run_id, topic=topic)
        self._conversations[conv_id] = conv
        return conv

    def send_message(
        self,
        *,
        conversation: TeamConversation,
        speaker_id: str,
        speaker_name: str = "",
        speaker_role: str = "",
        content: str,
        step_id: str = "",
        reply_to_id: str = "",
        message_type: str = "message",
        mood: str = "neutral",
        reaction_to_id: str = "",
        reaction: str = "",
        to_agent: str = "team",
        on_event: Optional[Callable] = None,
    ) -> ChatMessage:
        msg = conversation.add(
            speaker_id=speaker_id,
            speaker_name=speaker_name,
            speaker_role=speaker_role,
            content=content,
            step_id=step_id,
            reply_to_id=reply_to_id,
            message_type=message_type,
            mood=mood,
            reaction_to_id=reaction_to_id,
            reaction=reaction,
        )
        _emit_chat_message(msg, on_event, to_agent=to_agent)
        try:
            from api.services.agent.collaboration_logs import get_collaboration_service
            metadata = msg.to_dict()
            metadata.update(
                {
                    "event_type": "team_chat_message",
                    "from_agent": msg.speaker_id,
                    "to_agent": to_agent,
                    "message": msg.content,
                    "entry_type": "chat",
                }
            )
            get_collaboration_service().record(
                run_id=msg.run_id, from_agent=msg.speaker_id,
                to_agent=to_agent, message=msg.content,
                entry_type="chat", metadata=metadata,
            )
        except Exception:
            pass
        return msg

    def kickoff_step(
        self,
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
        facilitator_name = str(facilitator.get("name")).strip() if facilitator else "Maia Brain"
        facilitator_role = str(facilitator.get("role")).strip() if facilitator else "team_lead"

        teammate_pool = [row for row in normalized_agents if str(row["id"]).strip() != current_id]
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

        preferred_watcher = _preferred_watcher_agent(teammate_pool, exclude_id=facilitator_id)
        watcher_candidates = _resolve_participants(
            requested=[kickoff_plan.get("watcher_agent", "")],
            normalized_agents=teammate_pool,
            limit=1,
        )
        watcher_id = watcher_candidates[0] if watcher_candidates else str((preferred_watcher or teammate_pool[0])["id"]).strip()
        watcher_info = agent_map.get(watcher_id, preferred_watcher or teammate_pool[0])

        brain_message = " ".join(str(kickoff_plan.get("brain_message", "")).split()).strip()
        assignee_message = " ".join(str(kickoff_plan.get("assignee_message", "")).split()).strip()
        watcher_message = " ".join(str(kickoff_plan.get("watcher_message", "")).split()).strip()
        watcher_follow_up = " ".join(str(kickoff_plan.get("watcher_follow_up", "")).split()).strip()
        assignee_follow_up = " ".join(str(kickoff_plan.get("assignee_follow_up", "")).split()).strip()

        if not brain_message:
            brain_message = (
                f"{current_info.get('name', current_id)}, take this step: "
                f"{' '.join(str(step_description or original_task).split())[:160]}"
            )
        if not assignee_message:
            assignee_message = "I'm taking first pass on the evidence and I'll flag anything weak before handoff."
        if not watcher_message:
            watcher_message = "I'm watching for unsupported claims or shaky assumptions before this moves forward."
        if not watcher_follow_up:
            watcher_follow_up = "Call out uncertain claims early so I can pressure-test them before handoff."
        if not assignee_follow_up:
            assignee_follow_up = "I'll keep the pass tight and surface the weak spots as soon as I hit them."

        messages: list[ChatMessage] = []
        messages.append(
            self.send_message(
                conversation=conversation,
                speaker_id=facilitator_id,
                speaker_name=facilitator_name,
                speaker_role=facilitator_role,
                content=brain_message,
                step_id=step_id,
                message_type="message",
                mood="confident",
                to_agent=current_id,
                on_event=on_event,
            )
        )
        messages.append(
            self.send_message(
                conversation=conversation,
                speaker_id=current_id,
                speaker_name=current_info.get("name", current_id),
                speaker_role=current_info.get("role", "agent"),
                content=assignee_message,
                step_id=step_id,
                message_type="message",
                mood="curious",
                to_agent=facilitator_id,
                on_event=on_event,
            )
        )
        messages.append(
            self.send_message(
                conversation=conversation,
                speaker_id=watcher_id,
                speaker_name=watcher_info.get("name", watcher_id),
                speaker_role=watcher_info.get("role", "agent"),
                content=watcher_message,
                step_id=step_id,
                message_type="message",
                mood="skeptical",
                to_agent=current_id,
                on_event=on_event,
            )
        )
        messages.append(
            self.send_message(
                conversation=conversation,
                speaker_id=watcher_id,
                speaker_name=watcher_info.get("name", watcher_id),
                speaker_role=watcher_info.get("role", "agent"),
                content=watcher_follow_up,
                step_id=step_id,
                message_type="message",
                mood="skeptical",
                to_agent=current_id,
                on_event=on_event,
            )
        )
        messages.append(
            self.send_message(
                conversation=conversation,
                speaker_id=current_id,
                speaker_name=current_info.get("name", current_id),
                speaker_role=current_info.get("role", "agent"),
                content=assignee_follow_up,
                step_id=step_id,
                message_type="message",
                mood="confident",
                to_agent=watcher_id,
                on_event=on_event,
            )
        )
        return messages

    def brain_facilitates(
        self,
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

        agent_roster = ", ".join(
            f"{a.get('name', a.get('id', 'Agent'))} ({a.get('role', 'agent')})"
            for a in normalized_agents
        )

        # Step 1: Brain decides if discussion is needed and creates tension
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
                f"Decide:\n"
                f"1. Does this need discussion? (yes if there's anything debatable, "
                f"   unclear, improvable, or worth a second opinion)\n"
                f"2. Which 2-3 team members should weigh in?\n"
                f"3. What provocative question should you ask to spark real discussion?\n"
                f"   (not 'what do you think?' but a specific challenge)\n\n"
                f"JSON: {{"
                f'"needs_discussion": bool, '
                f'"participants": ["id1", "id2"], '
                f'"topic": "specific debate topic", '
                f'"opening_message": "your provocative opening (under 24 words)", '
                f'"challenge": "the specific thing you want them to debate (under 16 words)"'
                f"}}\n\n"
                f"{anti_repetition_prompt(discussion_recent_lines)}"
            ),
            tenant_id=tenant_id,
        )

        if not decision.get("needs_discussion", False):
            return []

        messages: list[ChatMessage] = []
        topic = str(decision.get("topic", original_task[:200]))
        conversation.topic = topic
        agent_map = {str(a["id"]).strip(): a for a in normalized_agents}
        discussion_recent_lines = recent_message_lines(conversation.messages, limit=8)
        facilitator = _resolve_facilitator_agent(normalized_agents)
        facilitator_id = str(facilitator.get("id")).strip() if facilitator else "brain"
        facilitator_name = str(facilitator.get("name")).strip() if facilitator else "Maia Brain"
        facilitator_role = str(facilitator.get("role")).strip() if facilitator else "team_lead"
        participants = _resolve_participants(
            requested=decision.get("participants", []),
            normalized_agents=normalized_agents,
            limit=4,
        )

        if not participants:
            return []

        # Step 2: Brain opens with a provocative question
        opening = str(decision.get("opening_message", f"Team, let's review this. {decision.get('challenge', '')}"))
        brain_msg = self.send_message(
            conversation=conversation, speaker_id=facilitator_id,
            speaker_name=facilitator_name, speaker_role=facilitator_role,
            content=opening, step_id=step_id,
            message_type="message", mood="curious",
            to_agent="team",
            on_event=on_event,
        )
        messages.append(brain_msg)

        challenge = str(decision.get("challenge", topic))

        # Step 3: Round 1 — each agent responds with personality
        # Emit "thinking" state first, then the actual response
        round1_messages: list[ChatMessage] = []
        for idx, pid in enumerate(participants):
            agent_info = agent_map[pid]
            personality = _get_personality(idx)
            try:
                # Show thinking indicator
                _ = self.send_message(
                    conversation=conversation, speaker_id=pid,
                    speaker_name=agent_info.get("name", pid),
                    speaker_role=agent_info.get("role", "agent"),
                    content="thinking...", step_id=step_id,
                    message_type="thinking", mood="curious",
                    to_agent=facilitator_id,
                    on_event=on_event,
                )

                # Get agent's response with personality
                response = _call_agent_llm(
                    system_prompt=PERSONALITY_PROMPT.format(
                        name=agent_info.get("name", pid),
                        role=agent_info.get("role", "agent"),
                        **personality,
                    ),
                    user_prompt=(
                        f"The Brain asked: {challenge}\n\n"
                        f"Context — the output being discussed:\n{step_output[:1500]}\n\n"
                        f"Reply like a teammate in a live thread. "
                        f"1-3 short sentences. One concrete point. "
                        f"If you disagree, say exactly what is wrong. "
                        f"If you need proof, ask for it directly. "
                        f"Do not explain the workflow or the user goal. "
                        f"Do not give a mini essay or justify why this step exists.\n\n"
                        f"{anti_repetition_prompt(recent_message_lines(messages, limit=8))}"
                    ),
                    tenant_id=tenant_id,
                    max_tokens=150,
                )

                # Determine mood from response
                mood = _infer_mood_from_response(response)

                agent_msg = self.send_message(
                    conversation=conversation, speaker_id=pid,
                    speaker_name=agent_info.get("name", pid),
                    speaker_role=agent_info.get("role", "agent"),
                    content=response, step_id=step_id,
                    reply_to_id=brain_msg.message_id,
                    message_type="message", mood=mood,
                    to_agent=facilitator_id,
                    on_event=on_event,
                )
                messages.append(agent_msg)
                round1_messages.append(agent_msg)
            except Exception as exc:
                logger.warning("Agent %s failed to respond: %s", pid, exc)

        if len(round1_messages) < 2:
            return messages

        # Step 4: Round 2 — agents react to each other (the interesting part)
        # Brain picks the most debatable point and asks agents to respond to each other
        history_text = "\n".join(f"{m.speaker_name}: {m.content}" for m in round1_messages)

        followup = _call_json_llm(
            system_prompt=(
                "You are the Brain facilitating a debate. "
                "Find the most interesting disagreement or tension in the discussion "
                "and ask a specific agent to respond to another agent's point."
            ),
            user_prompt=(
                f"Discussion so far:\n{history_text}\n\n"
                f"Pick the most interesting tension or disagreement. "
                f"Ask one agent to respond directly to another's specific point.\n\n"
                f"JSON: {{"
                f'"has_tension": bool, '
                f'"target_agent": "who should respond", '
                f'"challenge_from": "whose point they should address", '
                f'"followup_question": "your pointed question (under 30 words)"'
                f"}}"
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
            fq = str(followup.get("followup_question", ""))

            if target in agent_map and fq:
                # Brain pokes the target agent
                poke_msg = self.send_message(
                    conversation=conversation, speaker_id=facilitator_id,
                    speaker_name=facilitator_name, speaker_role=facilitator_role,
                    content=fq, step_id=step_id,
                    message_type="message", mood="curious",
                    to_agent=target,
                    on_event=on_event,
                )
                messages.append(poke_msg)

                # Target agent responds to the challenge
                target_info = agent_map[target]
                target_personality = _get_personality(
                    participants.index(target) if target in participants else 0
                )

                full_history = "\n".join(f"{m.speaker_name}: {m.content}" for m in messages)

                _ = self.send_message(
                    conversation=conversation, speaker_id=target,
                    speaker_name=target_info.get("name", target),
                    speaker_role=target_info.get("role", "agent"),
                    content="thinking...", step_id=step_id,
                    message_type="thinking", mood="curious",
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
                        f"The Brain just asked you: {fq}\n\n"
                        f"Respond directly to {challenge_from}'s point. "
                        f"1-3 short sentences. "
                        f"Agree, push back, or ask for evidence. "
                        f"Do not summarize the process.\n\n"
                        f"{anti_repetition_prompt(recent_message_lines(messages, limit=8))}"
                    ),
                    tenant_id=tenant_id,
                    max_tokens=150,
                )

                mood2 = _infer_mood_from_response(response2)
                resp2_msg = self.send_message(
                    conversation=conversation, speaker_id=target,
                    speaker_name=target_info.get("name", target),
                    speaker_role=target_info.get("role", "agent"),
                    content=response2, step_id=step_id,
                    reply_to_id=poke_msg.message_id,
                    message_type="message", mood=mood2,
                    to_agent=challenge_from or "brain",
                    on_event=on_event,
                )
                messages.append(resp2_msg)

                # Let the challenged agent react
                if challenge_from in agent_map:
                    from_info = agent_map[challenge_from]
                    reaction_response = _call_agent_llm(
                        system_prompt=f"You are {from_info.get('name', challenge_from)}. React briefly to what was just said about your point.",
                        user_prompt=(
                            f"{target_info.get('name', target)} just said: {response2}\n\n"
                            f"React in ONE short sentence. Agree, push back, or acknowledge. "
                            f"Keep it like a real team thread, not a report.\n\n"
                            f"{anti_repetition_prompt(recent_message_lines(messages, limit=8))}"
                        ),
                        tenant_id=tenant_id,
                        max_tokens=60,
                    )
                    react_msg = self.send_message(
                        conversation=conversation, speaker_id=challenge_from,
                        speaker_name=from_info.get("name", challenge_from),
                        speaker_role=from_info.get("role", "agent"),
                        content=reaction_response, step_id=step_id,
                        reply_to_id=resp2_msg.message_id,
                        message_type="message", mood=_infer_mood_from_response(reaction_response),
                        to_agent=target,
                        on_event=on_event,
                    )
                    messages.append(react_msg)

        # Step 5: Brain wraps up with a decision
        full_history = "\n".join(f"{m.speaker_name}: {m.content}" for m in messages if m.message_type == "message")
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
            summary_msg = self.send_message(
                conversation=conversation, speaker_id=facilitator_id,
                speaker_name=facilitator_name, speaker_role=facilitator_role,
                content=summary, step_id=step_id,
                message_type="summary", mood="confident",
                to_agent="team",
                on_event=on_event,
            )
            messages.append(summary_msg)

        return messages

    def get_conversation(self, conversation_id: str) -> TeamConversation | None:
        return self._conversations.get(conversation_id)

    def get_conversations_for_run(self, run_id: str) -> list[TeamConversation]:
        return [c for c in self._conversations.values() if c.run_id == run_id]


# ── Mood inference (LLM-driven, not keyword matching) ─────────────────────────

def _infer_mood_from_response(text: str) -> str:
    """Let the LLM classify the mood — no hardcoded patterns."""
    try:
        result = _call_json_llm(
            system_prompt="Classify the mood of this message in ONE word.",
            user_prompt=(
                f"Message: {text[:300]}\n\n"
                f"Pick exactly ONE mood: neutral, curious, confident, skeptical, "
                f"excited, concerned\n\n"
                f'JSON: {{"mood": "word"}}'
            ),
            tenant_id="",
        )
        mood = str(result.get("mood", "neutral")).strip().lower()
        if mood in ("neutral", "curious", "confident", "skeptical", "excited", "concerned"):
            return mood
    except Exception:
        pass
    return "neutral"


# ── LLM helpers ───────────────────────────────────────────────────────────────

def _call_agent_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    tenant_id: str = "",
    max_tokens: int = 200,
) -> str:
    try:
        from api.services.agent.llm_runtime import call_text_response
        return call_text_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=30,
            max_tokens=max_tokens,
            retries=1,
            enable_thinking=False,
        )
    except Exception:
        pass
    try:
        from api.services.agents.runner import run_agent_task
        parts: list[str] = []
        for chunk in run_agent_task(
            user_prompt, tenant_id=tenant_id,
            system_prompt=system_prompt,
            agent_mode="ask", max_tool_calls=0,
        ):
            text = chunk.get("text") or chunk.get("content") or ""
            if text:
                parts.append(str(text))
        return "".join(parts)
    except Exception as exc:
        logger.warning("Agent LLM call failed: %s", exc)
        return ""


def _call_json_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    tenant_id: str = "",
) -> dict[str, Any]:
    try:
        from api.services.agent.llm_runtime import call_json_response
        result = call_json_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=30,
            max_tokens=300,
            retries=1,
            allow_json_repair=True,
            enable_thinking=False,
        )
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    text = _call_agent_llm(system_prompt=system_prompt, user_prompt=user_prompt, tenant_id=tenant_id)
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {}


# ── Event emission ────────────────────────────────────────────────────────────

def _emit_chat_message(
    msg: ChatMessage,
    on_event: Optional[Callable] = None,
    *,
    to_agent: str = "team",
) -> None:
    entry_type = "summary" if msg.message_type == "summary" else "chat"
    event = {
        "event_type": "team_chat_message",
        "title": msg.speaker_name,
        "detail": msg.content[:300],
        "stage": "execute",
        "status": "info",
        "data": {
            **msg.to_dict(),
            "from_agent": msg.speaker_id,
            "to_agent": to_agent,
            "message": msg.content,
            "entry_type": entry_type,
            "scene_surface": "team_chat",
            "scene_family": "chat",
            "event_family": "chat",
        },
    }
    if on_event:
        try:
            on_event(event)
        except Exception:
            pass
    try:
        from api.services.agent.live_events import get_live_event_broker
        get_live_event_broker().publish(user_id="", run_id=msg.run_id, event=event)
    except Exception:
        pass


# ── Singleton ─────────────────────────────────────────────────────────────────

_service: AgentTeamChatService | None = None


def get_team_chat_service() -> AgentTeamChatService:
    global _service
    if _service is None:
        _service = AgentTeamChatService()
    return _service

