"""Action-linked team chat for live workflow execution.

Turns meaningful runtime actions into short teammate chat lines so the
conversation feed matches what the theatre is currently showing.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Optional

from .team_chat_guidance import anti_repetition_prompt, recent_message_lines

logger = logging.getLogger(__name__)

_MEANINGFUL_EVENT_TYPES = {
    "tool_started",
    "tool_progress",
    "execution_checkpoint",
    "desktop_starting",
    "desktop_ready",
    "task_understanding_started",
    "task_understanding_ready",
    "preflight_started",
    "preflight_check",
    "preflight_completed",
    "planning_started",
    "contract_started",
    "contract_completed",
    "working_context_ready",
    "web_search_started",
    "web_result_opened",
    "retrieval_query_rewrite",
    "brave.search.query",
    "brave.search.results",
    "api_call_started",
    "browser_open",
    "browser_navigate",
    "browser_extract",
    "browser_click",
    "browser_hover",
    "browser_scroll",
    "browser_keyword_highlight",
    "browser_contact_submit",
    "research_branch_started",
    "research_branch_completed",
    "verification_check",
    "evidence_crystallized",
    "approval_required",
}

_MEANINGFUL_PREFIXES = (
    "browser_contact_fill_",
    "llm.",
)


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
        normalized.append(
            {
                "id": agent_id,
                "name": str(row.get("name") or "").strip() or _humanize_agent_id(agent_id),
                "role": str(row.get("role") or "").strip() or "agent",
                "step_description": str(row.get("step_description") or "").strip(),
            }
        )
    return normalized


def _normalized_role(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _pick_counterparty(
    *,
    actor: dict[str, str],
    roster: list[dict[str, str]],
    signal: dict[str, str],
) -> dict[str, str] | None:
    pool = [row for row in roster if row["id"] != actor["id"]]
    if not pool:
        return None
    scene_family = signal.get("scene_family", "")
    event_type = signal.get("event_type", "")

    def _rank(row: dict[str, str]) -> tuple[int, str]:
        role = _normalized_role(row.get("role", ""))
        if "supervisor" in role:
            return (0, row.get("name", ""))
        if scene_family in {"browser", "document"} or event_type.startswith("browser_") or "search" in event_type:
            if "review" in role:
                return (1, row.get("name", ""))
            if "analyst" in role:
                return (2, row.get("name", ""))
        if scene_family in {"email", "chat"}:
            if "review" in role:
                return (1, row.get("name", ""))
            if "writer" in role:
                return (2, row.get("name", ""))
        if "review" in role:
            return (1, row.get("name", ""))
        if "analyst" in role:
            return (2, row.get("name", ""))
        if "writer" in role:
            return (3, row.get("name", ""))
        return (4, row.get("name", ""))

    return sorted(pool, key=_rank)[0]


def _meaningful_event_type(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or event.get("type") or "").strip().lower()
    if not event_type:
        return ""
    if event_type in _MEANINGFUL_EVENT_TYPES:
        return event_type
    if any(event_type.startswith(prefix) for prefix in _MEANINGFUL_PREFIXES):
        return event_type
    return ""


def _as_data_map(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data")
    return data if isinstance(data, dict) else {}


def _action_signal(event: dict[str, Any]) -> dict[str, str] | None:
    event_type = _meaningful_event_type(event)
    if not event_type:
        return None
    data = _as_data_map(event)
    operation_label = str(
        data.get("operation_label")
        or data.get("interaction_label")
        or event.get("title")
        or ""
    ).strip()
    detail = str(event.get("detail") or data.get("detail") or "").strip()
    if not operation_label and not detail:
        return None
    scene_family = str(data.get("scene_family") or event.get("scene_family") or "").strip().lower()
    scene_surface = str(data.get("scene_surface") or event.get("scene_surface") or "").strip().lower()
    action = str(data.get("action") or "").strip().lower()
    detail_key = detail.lower()
    if event_type in {
        "tool_progress",
        "execution_checkpoint",
        "browser_scroll",
        "task_understanding_started",
        "task_understanding_ready",
        "preflight_started",
        "preflight_check",
        "preflight_completed",
        "planning_started",
        "contract_started",
        "contract_completed",
        "working_context_ready",
    } or event_type.startswith("llm."):
        detail_key = detail_key[:120]
    key = "|".join(
        [
            event_type,
            operation_label.lower(),
            detail_key,
            scene_family,
            scene_surface,
            action,
        ]
    )
    return {
        "event_type": event_type,
        "operation_label": operation_label[:180],
        "detail": detail[:260],
        "scene_family": scene_family,
        "scene_surface": scene_surface,
        "action": action,
        "key": key,
    }


def _call_json_response(*, tenant_id: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    try:
        from api.services.agent.llm_runtime import call_json_response

        payload = call_json_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_seconds=12,
            max_tokens=220,
            retries=0,
            allow_json_repair=True,
            enable_thinking=False,
            use_fallback_models=False,
        )
        if isinstance(payload, dict):
            return payload
    except Exception as exc:
        logger.debug("Action chat LLM call failed: %s", exc)
    return {}


class StepActionChatBridge:
    """Observes step runtime events and mirrors key actions into team chat."""

    def __init__(
        self,
        *,
        run_id: str,
        step_id: str,
        agent_id: str,
        step_description: str,
        original_task: str,
        agents: list[dict[str, Any]],
        tenant_id: str,
        on_event: Optional[Callable] = None,
    ) -> None:
        self.run_id = run_id
        self.step_id = step_id
        self.agent_id = str(agent_id or "").strip()
        self.step_description = str(step_description or "").strip()
        self.original_task = str(original_task or "").strip()
        self.tenant_id = tenant_id
        self.on_event = on_event
        self._roster = _normalize_agents(agents)
        self._conversation = None
        self._seen_keys: set[str] = set()
        self._last_emit_at = 0.0
        self._window_started_at = 0.0
        self._window_bursts = 0

    def observe(self, event: dict[str, Any]) -> None:
        signal = _action_signal(event)
        if not signal:
            return
        if signal["key"] in self._seen_keys:
            return
        now = time.time()
        if self._window_started_at <= 0.0 or now - self._window_started_at >= 45.0:
            self._window_started_at = now
            self._window_bursts = 0
        if self._window_bursts >= 6:
            return
        if now - self._last_emit_at < 2.0:
            return
        self._seen_keys.add(signal["key"])
        self._last_emit_at = now
        self._emit(signal)

    def _emit(self, signal: dict[str, str]) -> None:
        if not self.agent_id or len(self._roster) < 2:
            return
        actor = next((row for row in self._roster if row["id"] == self.agent_id), None)
        teammate = _pick_counterparty(actor=actor, roster=self._roster, signal=signal) if actor else None
        if not actor or not teammate:
            return

        from api.services.agent.brain.team_chat import get_team_chat_service

        chat = get_team_chat_service()
        if self._conversation is None:
            self._conversation = chat.start_conversation(
                run_id=self.run_id,
                topic=self.original_task or self.step_description or signal["operation_label"],
                initiated_by=self.agent_id,
                step_id=self.step_id,
                on_event=self.on_event,
            )

        payload = _call_json_response(
            tenant_id=self.tenant_id,
            system_prompt=(
                "You convert a live runtime action into a short teammate exchange. "
                "Return strict JSON only with actor_message and teammate_reply. "
                "The lines must match the action being performed right now and feel like coworkers pressure-testing the work."
            ),
            user_prompt=(
                f"Overall task: {self.original_task}\n"
                f"Current step: {self.step_description}\n"
                f"Actor: {actor['name']} ({actor['role']})\n"
                f"Teammate: {teammate['name']} ({teammate['role']})\n"
                f"Live action event: {signal['event_type']}\n"
                f"Operation label: {signal['operation_label']}\n"
                f"Detail: {signal['detail']}\n"
                f"Scene family: {signal['scene_family']}\n"
                f"Scene surface: {signal['scene_surface']}\n"
                f"Action kind: {signal['action']}\n\n"
                "Return JSON:\n"
                "{\n"
                '  "actor_message": "under 18 words",\n'
                '  "teammate_reply": "under 18 words"\n'
                "}\n"
                "Rules:\n"
                "- Sound like coworkers in a live thread.\n"
                "- Mention the current action, not the whole workflow.\n"
                "- No user-facing narration or methodology explanation.\n"
                "- No process recap, no reasons for why the step exists, no formal summary tone.\n"
                "- Use first-person teammate language like 'I'm checking...' or 'Can you confirm...'.\n"
                "- The actor line must state a concrete check, extraction, revision, or constraint.\n"
                "- The teammate reply must challenge, verify, narrow scope, request proof, or set a quality bar.\n"
                "- Avoid pure acknowledgements and avoid generic status lines.\n"
                f"\n{anti_repetition_prompt(recent_message_lines(self._conversation.messages if self._conversation else [], limit=6))}"
            ),
        )

        actor_message = " ".join(str(payload.get("actor_message", "")).split()).strip()
        teammate_reply = " ".join(str(payload.get("teammate_reply", "")).split()).strip()

        if not actor_message:
            actor_message = (
                signal["operation_label"]
                or signal["detail"]
                or f"Working on {self.step_description[:80]}"
            )
        if not teammate_reply:
            teammate_reply = "Before you move on, confirm the visible evidence actually supports the claim."

        chat.send_message(
            conversation=self._conversation,
            speaker_id=actor["id"],
            speaker_name=actor["name"],
            speaker_role=actor["role"],
            content=actor_message,
            step_id=self.step_id,
            message_type="message",
            mood="confident",
            to_agent=teammate["id"],
            on_event=self.on_event,
        )
        chat.send_message(
            conversation=self._conversation,
            speaker_id=teammate["id"],
            speaker_name=teammate["name"],
            speaker_role=teammate["role"],
            content=teammate_reply,
            step_id=self.step_id,
            message_type="message",
            mood="skeptical",
            to_agent=actor["id"],
            on_event=self.on_event,
        )
        self._window_bursts += 1
