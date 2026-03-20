"""Agent Dialogue Turns — mid-step conversations between agents.

When an agent needs information from another agent during execution,
this service facilitates the exchange: question → answer → back to work.
Each turn is emitted as a live event for the team chat panel.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

MAX_TURNS_PER_PAIR = 5


class DialogueTurn:
    __slots__ = (
        "turn_id",
        "run_id",
        "from_agent",
        "to_agent",
        "message",
        "turn_type",
        "turn_role",
        "interaction_label",
        "scene_family",
        "scene_surface",
        "operation_label",
        "action",
        "action_phase",
        "action_status",
        "timestamp",
    )

    def __init__(
        self,
        *,
        run_id: str,
        from_agent: str,
        to_agent: str,
        message: str,
        turn_type: str = "question",
        turn_role: str = "message",
        interaction_label: str = "",
        scene_family: str = "",
        scene_surface: str = "",
        operation_label: str = "",
        action: str = "",
        action_phase: str = "",
        action_status: str = "",
    ):
        self.turn_id = f"dt_{int(time.time() * 1000)}"
        self.run_id = run_id
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.message = message
        self.turn_type = turn_type
        self.turn_role = turn_role
        self.interaction_label = interaction_label
        self.scene_family = scene_family
        self.scene_surface = scene_surface
        self.operation_label = operation_label
        self.action = action
        self.action_phase = action_phase
        self.action_status = action_status
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id, "run_id": self.run_id,
            "from_agent": self.from_agent, "to_agent": self.to_agent,
            "message": self.message, "turn_type": self.turn_type,
            "turn_role": self.turn_role, "interaction_label": self.interaction_label,
            "scene_family": self.scene_family, "scene_surface": self.scene_surface,
            "operation_label": self.operation_label,
            "action": self.action, "action_phase": self.action_phase, "action_status": self.action_status,
            "timestamp": self.timestamp,
        }


class DialogueService:
    """Facilitates agent-to-agent dialogue during workflow execution."""

    def __init__(self) -> None:
        self._turns: dict[str, list[DialogueTurn]] = {}

    def ask(
        self,
        *,
        run_id: str,
        from_agent: str,
        to_agent: str,
        question: str,
        tenant_id: str = "",
        on_event: Optional[Callable] = None,
        answer_fn: Optional[Callable[..., str]] = None,
        ask_turn_type: str = "question",
        answer_turn_type: str = "answer",
        ask_turn_role: str = "request",
        answer_turn_role: str = "response",
        interaction_label: str = "",
        scene_family: str = "",
        scene_surface: str = "",
        operation_label: str = "",
        action: str = "",
        action_phase: str = "active",
        action_status: str = "in_progress",
        prompt_preamble: str | None = None,
    ) -> str:
        """Send a question from one agent to another and get an answer."""
        pair_key = f"{run_id}:{from_agent}:{to_agent}"
        turns = self._turns.setdefault(pair_key, [])
        if len(turns) >= MAX_TURNS_PER_PAIR:
            return "[Max dialogue turns reached]"

        # Record and emit question
        q_turn = DialogueTurn(
            run_id=run_id,
            from_agent=from_agent,
            to_agent=to_agent,
            message=question,
            turn_type=str(ask_turn_type or "question").strip().lower() or "question",
            turn_role=str(ask_turn_role or "request").strip().lower() or "request",
            interaction_label=str(interaction_label or "").strip(),
            scene_family=str(scene_family or "").strip().lower(),
            scene_surface=str(scene_surface or "").strip().lower(),
            operation_label=str(operation_label or "").strip(),
            action=str(action or "").strip().lower(),
            action_phase=str(action_phase or "").strip().lower(),
            action_status=str(action_status or "").strip().lower(),
        )
        turns.append(q_turn)
        self._emit_turn(q_turn, on_event)

        # Log in collaboration service
        try:
            from api.services.agent.collaboration_logs import get_collaboration_service
            get_collaboration_service().record_question(
                run_id=run_id,
                from_agent=from_agent,
                to_agent=to_agent,
                question=question,
                metadata={
                    "turn_type": q_turn.turn_type,
                    "turn_role": q_turn.turn_role,
                    "interaction_label": q_turn.interaction_label,
                    "scene_family": q_turn.scene_family,
                    "scene_surface": q_turn.scene_surface,
                    "operation_label": q_turn.operation_label,
                    "action": q_turn.action,
                    "action_phase": q_turn.action_phase,
                    "action_status": q_turn.action_status,
                },
            )
        except Exception:
            pass

        # Get the answer
        answer = ""
        if answer_fn:
            try:
                preamble = str(prompt_preamble or "").strip()
                if preamble:
                    prompt = (
                        f"{preamble}\n\n"
                        f"Your teammate {from_agent} asks: {question}\n\n"
                        "Provide a clear, concise answer with evidence when relevant."
                    )
                else:
                    prompt = (
                        f"Your teammate {from_agent} asks: {question}\n\n"
                        "Provide a clear, concise answer with evidence when relevant."
                    )
                try:
                    # Preferred path: answer with the specific teammate agent.
                    answer = answer_fn(to_agent, prompt)
                except TypeError:
                    # Backward-compatible fallback for legacy one-arg callbacks.
                    answer = answer_fn(prompt)
            except Exception as exc:
                answer = f"[Failed to respond: {exc}]"
        else:
            answer = "[No response handler available]"

        # Record and emit answer
        a_turn = DialogueTurn(
            run_id=run_id,
            from_agent=to_agent,
            to_agent=from_agent,
            message=answer,
            turn_type=str(answer_turn_type or "answer").strip().lower() or "answer",
            turn_role=str(answer_turn_role or "response").strip().lower() or "response",
            interaction_label=str(interaction_label or "").strip(),
            scene_family=str(scene_family or "").strip().lower(),
            scene_surface=str(scene_surface or "").strip().lower(),
            operation_label=str(operation_label or "").strip(),
            action=str(action or "").strip().lower(),
            action_phase="completed",
            action_status="ok",
        )
        turns.append(a_turn)
        self._emit_turn(a_turn, on_event)

        try:
            from api.services.agent.collaboration_logs import get_collaboration_service
            get_collaboration_service().record_response(
                run_id=run_id,
                from_agent=to_agent,
                to_agent=from_agent,
                response=answer[:500],
                metadata={
                    "turn_type": a_turn.turn_type,
                    "turn_role": a_turn.turn_role,
                    "interaction_label": a_turn.interaction_label,
                    "scene_family": a_turn.scene_family,
                    "scene_surface": a_turn.scene_surface,
                    "operation_label": a_turn.operation_label,
                    "action": a_turn.action,
                    "action_phase": a_turn.action_phase,
                    "action_status": a_turn.action_status,
                },
            )
        except Exception:
            pass

        return answer

    def challenge(
        self,
        *,
        run_id: str,
        from_agent: str,
        to_agent: str,
        point: str,
        on_event: Optional[Callable] = None,
        defend_fn: Optional[Callable[..., str]] = None,
    ) -> str:
        """Challenge an agent's claim and get their defense."""
        try:
            from api.services.agent.collaboration_logs import get_collaboration_service
            get_collaboration_service().record_disagreement(
                run_id=run_id,
                from_agent=from_agent,
                to_agent=to_agent,
                point=point,
                metadata={
                    "turn_type": "challenge_request",
                    "turn_role": "request",
                    "interaction_label": "challenge",
                },
            )
        except Exception:
            pass
        return self.ask(
            run_id=run_id,
            from_agent=from_agent,
            to_agent=to_agent,
            question=point,
            on_event=on_event,
            answer_fn=defend_fn,
            ask_turn_type="challenge_request",
            answer_turn_type="challenge_response",
            ask_turn_role="request",
            answer_turn_role="response",
            interaction_label="challenge",
            prompt_preamble="Your teammate is challenging your claim. Defend your position or revise if they are right.",
        )

    def get_dialogue(self, run_id: str) -> list[dict[str, Any]]:
        """Get all dialogue turns for a run."""
        result: list[dict[str, Any]] = []
        for key, turns in self._turns.items():
            if key.startswith(f"{run_id}:"):
                result.extend(t.to_dict() for t in turns)
        result.sort(key=lambda t: t.get("timestamp", 0))
        return result

    def _emit_turn(self, turn: DialogueTurn, on_event: Optional[Callable]) -> None:
        event = {
            "event_type": "agent_dialogue_turn",
            "title": f"{turn.from_agent} → {turn.to_agent}",
            "detail": turn.message[:300],
            "stage": "execute", "status": "info",
            "data": {**turn.to_dict(), "from_agent": turn.from_agent, "to_agent": turn.to_agent},
        }
        if on_event:
            try:
                on_event(event)
            except Exception:
                pass
        try:
            from api.services.agent.live_events import get_live_event_broker
            get_live_event_broker().publish(user_id="", run_id=turn.run_id, event=event)
        except Exception:
            pass


_service: DialogueService | None = None


def get_dialogue_service() -> DialogueService:
    global _service
    if _service is None:
        _service = DialogueService()
    return _service
