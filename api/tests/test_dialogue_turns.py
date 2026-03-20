from __future__ import annotations

from api.services.agent.dialogue_turns import DialogueService


def test_dialogue_ask_uses_target_agent_callback_signature() -> None:
    service = DialogueService()
    captured: dict[str, str] = {}

    def answer_fn(target_agent: str, prompt: str) -> str:
        captured["target_agent"] = target_agent
        captured["prompt"] = prompt
        return "Here is the teammate response."

    answer = service.ask(
        run_id="run_1",
        from_agent="researcher",
        to_agent="analyst",
        question="Can you validate the margin assumption?",
        answer_fn=answer_fn,
    )

    assert answer == "Here is the teammate response."
    assert captured["target_agent"] == "analyst"
    assert "researcher" in captured["prompt"].lower()


def test_dialogue_ask_keeps_backward_compat_for_one_arg_callback() -> None:
    service = DialogueService()

    def answer_fn(prompt: str) -> str:
        return f"legacy:{prompt[:20]}"

    answer = service.ask(
        run_id="run_2",
        from_agent="writer",
        to_agent="reviewer",
        question="Is this summary clear enough?",
        answer_fn=answer_fn,
    )

    assert answer.startswith("legacy:")


def test_dialogue_ask_supports_custom_turn_types() -> None:
    service = DialogueService()

    def answer_fn(target_agent: str, prompt: str) -> str:
        assert target_agent == "researcher"
        assert "evidence" in prompt.lower()
        return "Evidence attached: source A, source B."

    answer = service.ask(
        run_id="run_3",
        from_agent="analyst",
        to_agent="researcher",
        question="Provide evidence for your claim.",
        answer_fn=answer_fn,
        ask_turn_type="evidence_request",
        answer_turn_type="evidence_response",
        interaction_label="request evidence",
        prompt_preamble="Respond with citations and confidence level.",
    )

    assert "Evidence attached" in answer
    dialogue = service.get_dialogue("run_3")
    assert len(dialogue) == 2
    assert dialogue[0]["turn_type"] == "evidence_request"
    assert dialogue[1]["turn_type"] == "evidence_response"
    assert dialogue[0]["turn_role"] == "request"
    assert dialogue[1]["turn_role"] == "response"
    assert dialogue[0]["interaction_label"] == "request evidence"
