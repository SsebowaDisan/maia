"""Tests for the LLM interaction suggestion backend feature.

Coverage:
- Schema validation and clamping (including new highlight/search actions and highlight_text)
- advisory / __no_execution safety invariants
- Feature flag gating (disabled → no LLM call, no event)
- Confidence threshold gating (per-suggestion filtering)
- Non-interactive tool filtering
- LLM adapter behaviour (via mock) — list return, array parsing, deterministic skip
- Emitter end-to-end (via mocks) — multiple events emitted, cap enforced
- No-action side-effect guarantee (only local list mutated)
"""
from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from api.services.agent.interaction_suggestion.schema import (
    VALID_ACTIONS,
    InteractionSuggestionPayload,
    payload_to_metadata,
    validate_and_clamp,
)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestValidateAndClamp(unittest.TestCase):
    def _valid_raw(self, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "action": "click",
            "target_label": "Submit button",
            "cursor_x": 50.0,
            "cursor_y": 75.0,
            "scroll_percent": 0.0,
            "confidence": 0.85,
            "reason": "The form is ready to submit.",
            "highlight_text": "",
        }
        base.update(overrides)
        return base

    def test_valid_payload_parses(self) -> None:
        result = validate_and_clamp(self._valid_raw())
        assert result is not None
        assert result.action == "click"
        assert result.confidence == 0.85
        assert result.advisory is True

    def test_all_valid_actions_accepted(self) -> None:
        for action in VALID_ACTIONS:
            result = validate_and_clamp(self._valid_raw(action=action))
            assert result is not None, f"action={action!r} should be valid"

    def test_highlight_action_accepted(self) -> None:
        result = validate_and_clamp(
            self._valid_raw(action="highlight", highlight_text="important clause")
        )
        assert result is not None
        assert result.action == "highlight"
        assert result.highlight_text == "important clause"

    def test_search_action_accepted(self) -> None:
        result = validate_and_clamp(
            self._valid_raw(action="search", highlight_text="pricing plans")
        )
        assert result is not None
        assert result.action == "search"
        assert result.highlight_text == "pricing plans"

    def test_unknown_action_rejected(self) -> None:
        result = validate_and_clamp(self._valid_raw(action="delete"))
        assert result is None

    def test_empty_action_rejected(self) -> None:
        result = validate_and_clamp(self._valid_raw(action=""))
        assert result is None

    def test_non_dict_input_returns_none(self) -> None:
        assert validate_and_clamp(None) is None  # type: ignore[arg-type]
        assert validate_and_clamp("click") is None  # type: ignore[arg-type]
        assert validate_and_clamp([]) is None  # type: ignore[arg-type]

    def test_cursor_x_clamped_to_0_100(self) -> None:
        result = validate_and_clamp(self._valid_raw(cursor_x=-20.0))
        assert result is not None
        assert result.cursor_x == 0.0

        result = validate_and_clamp(self._valid_raw(cursor_x=150.0))
        assert result is not None
        assert result.cursor_x == 100.0

    def test_cursor_y_clamped_to_0_100(self) -> None:
        result = validate_and_clamp(self._valid_raw(cursor_y=-1.0))
        assert result is not None
        assert result.cursor_y == 0.0

        result = validate_and_clamp(self._valid_raw(cursor_y=999.0))
        assert result is not None
        assert result.cursor_y == 100.0

    def test_confidence_clamped_to_0_1(self) -> None:
        result = validate_and_clamp(self._valid_raw(confidence=-5.0))
        assert result is not None
        assert result.confidence == 0.0

        result = validate_and_clamp(self._valid_raw(confidence=10.0))
        assert result is not None
        assert result.confidence == 1.0

    def test_scroll_percent_clamped(self) -> None:
        result = validate_and_clamp(self._valid_raw(scroll_percent=200.0))
        assert result is not None
        assert result.scroll_percent == 100.0

    def test_target_label_truncated_to_200(self) -> None:
        long_label = "x" * 300
        result = validate_and_clamp(self._valid_raw(target_label=long_label))
        assert result is not None
        assert len(result.target_label) == 200

    def test_reason_truncated_to_280(self) -> None:
        long_reason = "y" * 400
        result = validate_and_clamp(self._valid_raw(reason=long_reason))
        assert result is not None
        assert len(result.reason) == 280

    def test_highlight_text_truncated_to_200(self) -> None:
        long_text = "z" * 300
        result = validate_and_clamp(self._valid_raw(highlight_text=long_text))
        assert result is not None
        assert len(result.highlight_text) == 200

    def test_highlight_text_defaults_to_empty(self) -> None:
        raw = self._valid_raw()
        raw.pop("highlight_text", None)
        result = validate_and_clamp(raw)
        assert result is not None
        assert result.highlight_text == ""


# ---------------------------------------------------------------------------
# Advisory / safety invariant tests
# ---------------------------------------------------------------------------


class TestAdvisoryInvariant(unittest.TestCase):
    def test_advisory_always_true_on_payload(self) -> None:
        raw = {
            "action": "navigate",
            "target_label": "Homepage",
            "cursor_x": 10.0,
            "cursor_y": 10.0,
            "scroll_percent": 0.0,
            "confidence": 0.9,
            "reason": "Go to homepage.",
        }
        result = validate_and_clamp(raw)
        assert result is not None
        assert result.advisory is True

    def test_advisory_cannot_be_overridden_via_raw(self) -> None:
        raw = {
            "action": "click",
            "target_label": "Send button",
            "cursor_x": 50.0,
            "cursor_y": 50.0,
            "scroll_percent": 0.0,
            "confidence": 0.8,
            "reason": "Click send.",
            "advisory": False,  # attacker-supplied override attempt
        }
        result = validate_and_clamp(raw)
        assert result is not None
        # advisory must still be True regardless of what the raw dict says
        assert result.advisory is True

    def test_payload_to_metadata_always_sets_no_execution(self) -> None:
        payload = validate_and_clamp(
            {
                "action": "scroll",
                "target_label": "Article body",
                "cursor_x": 50.0,
                "cursor_y": 50.0,
                "scroll_percent": 40.0,
                "confidence": 0.7,
                "reason": "Scroll to see more.",
            }
        )
        assert payload is not None
        meta = payload_to_metadata(payload)
        assert meta["advisory"] is True
        assert meta["__no_execution"] is True

    def test_payload_to_metadata_includes_highlight_text(self) -> None:
        payload = validate_and_clamp(
            {
                "action": "highlight",
                "target_label": "Key sentence",
                "cursor_x": 40.0,
                "cursor_y": 60.0,
                "scroll_percent": 0.0,
                "confidence": 0.8,
                "reason": "Highlight this clause.",
                "highlight_text": "key performance indicator",
            }
        )
        assert payload is not None
        meta = payload_to_metadata(payload)
        assert meta["highlight_text"] == "key performance indicator"
        assert meta["advisory"] is True
        assert meta["__no_execution"] is True

    def test_frozen_payload_cannot_mutate_advisory(self) -> None:
        payload = validate_and_clamp(
            {
                "action": "verify",
                "target_label": "Status",
                "cursor_x": 50.0,
                "cursor_y": 50.0,
                "scroll_percent": 0.0,
                "confidence": 0.5,
                "reason": "Verify status.",
            }
        )
        assert payload is not None
        with self.assertRaises((AttributeError, TypeError)):
            payload.advisory = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# LLM adapter tests (mocked)
# ---------------------------------------------------------------------------


class TestLlmAdapter(unittest.TestCase):
    def _make_raw_item(self, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "action": "click",
            "target_label": "Next page button",
            "cursor_x": 80.0,
            "cursor_y": 90.0,
            "scroll_percent": 0.0,
            "confidence": 0.75,
            "reason": "Advance to the next page.",
            "highlight_text": "",
        }
        base.update(overrides)
        return base

    def _make_interactions_response(self, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if items is None:
            items = [
                self._make_raw_item(action="navigate", cursor_x=24.0, cursor_y=9.0),
                self._make_raw_item(action="click", cursor_x=50.0, cursor_y=30.0),
                self._make_raw_item(action="scroll", cursor_x=88.0, cursor_y=50.0, scroll_percent=40.0),
                self._make_raw_item(action="highlight", cursor_x=40.0, cursor_y=60.0, highlight_text="key phrase"),
                self._make_raw_item(action="search", cursor_x=50.0, cursor_y=10.0, highlight_text="pricing"),
            ]
        return {"interactions": items}

    def _call_adapter(self, **overrides: Any) -> Any:
        from api.services.agent.interaction_suggestion.llm_adapter import (
            generate_interaction_suggestion,
        )

        defaults: dict[str, Any] = dict(
            tool_id="browser.playwright.inspect",
            step_title="Inspect landing page",
            step_why="Need to check page structure before clicking.",
            step_params={"url": "https://example.com"},
            task_context="Find the pricing page and compare plans",
            step_index=2,
            total_steps=5,
        )
        defaults.update(overrides)
        return generate_interaction_suggestion(**defaults)

    @patch("api.services.agent.interaction_suggestion.llm_adapter.call_json_response")
    def test_adapter_returns_list_of_suggestions(self, mock_call: MagicMock) -> None:
        mock_call.return_value = self._make_interactions_response()
        result = self._call_adapter()
        assert isinstance(result, list)
        assert len(result) == 5
        assert all(isinstance(s, InteractionSuggestionPayload) for s in result)
        assert all(s.advisory is True for s in result)

    @patch("api.services.agent.interaction_suggestion.llm_adapter.call_json_response")
    def test_adapter_returns_highlight_and_search_suggestions(self, mock_call: MagicMock) -> None:
        mock_call.return_value = self._make_interactions_response()
        result = self._call_adapter()
        actions = {s.action for s in result}
        assert "highlight" in actions
        assert "search" in actions

    @patch("api.services.agent.interaction_suggestion.llm_adapter.call_json_response")
    def test_adapter_preserves_highlight_text(self, mock_call: MagicMock) -> None:
        mock_call.return_value = self._make_interactions_response()
        result = self._call_adapter()
        highlight_items = [s for s in result if s.action == "highlight"]
        assert highlight_items[0].highlight_text == "key phrase"
        search_items = [s for s in result if s.action == "search"]
        assert search_items[0].highlight_text == "pricing"

    @patch("api.services.agent.interaction_suggestion.llm_adapter.call_json_response")
    def test_prompt_includes_task_context_and_step_position(
        self, mock_call: MagicMock
    ) -> None:
        mock_call.return_value = self._make_interactions_response()
        self._call_adapter(
            task_context="Compare competitor pricing",
            step_index=3,
            total_steps=7,
        )
        assert mock_call.called
        prompt_arg = mock_call.call_args[1]["prompt"]
        assert "Compare competitor pricing" in prompt_arg
        assert "3 of 7" in prompt_arg

    @patch("api.services.agent.interaction_suggestion.llm_adapter.call_json_response")
    def test_adapter_returns_empty_on_llm_error(self, mock_call: MagicMock) -> None:
        mock_call.side_effect = RuntimeError("LLM unavailable")
        result = self._call_adapter(step_params={})
        assert result == []

    @patch("api.services.agent.interaction_suggestion.llm_adapter.call_json_response")
    def test_adapter_filters_invalid_actions(self, mock_call: MagicMock) -> None:
        # One invalid action mixed in — it should be silently dropped
        items = self._make_interactions_response()["interactions"].copy()
        items[2] = self._make_raw_item(action="execute_script")
        mock_call.return_value = {"interactions": items}
        result = self._call_adapter()
        assert len(result) == 4
        assert all(s.action in VALID_ACTIONS for s in result)

    @patch("api.services.agent.interaction_suggestion.llm_adapter.call_json_response")
    def test_adapter_returns_empty_when_interactions_key_missing(self, mock_call: MagicMock) -> None:
        mock_call.return_value = {"action": "click", "confidence": 0.8}  # old flat format
        result = self._call_adapter()
        assert result == []

    @patch("api.services.agent.interaction_suggestion.llm_adapter.call_json_response")
    def test_adapter_skips_when_deterministic_params_present(
        self, mock_call: MagicMock
    ) -> None:
        result = self._call_adapter(
            step_params={"x": 55.0, "y": 42.0, "selector": "#submit"}
        )
        assert result == []
        mock_call.assert_not_called()

    @patch("api.services.agent.interaction_suggestion.llm_adapter.call_json_response")
    def test_adapter_skips_when_selector_present(self, mock_call: MagicMock) -> None:
        result = self._call_adapter(
            tool_id="docs.edit",
            step_params={"selector": "input[name=title]", "value": "Hello"},
        )
        assert result == []
        mock_call.assert_not_called()


# ---------------------------------------------------------------------------
# Emitter tests (feature flag gating + multiple events + no side-effects)
# ---------------------------------------------------------------------------


class TestEmitter(unittest.TestCase):
    def _make_mocks(self) -> tuple[MagicMock, MagicMock]:
        emit_event = MagicMock(return_value={"event_type": "interaction_suggestion"})
        factory = MagicMock(return_value=MagicMock())
        return emit_event, factory

    def _make_suggestion_list(self, count: int = 5, confidence: float = 0.8) -> list[Any]:
        from api.services.agent.interaction_suggestion.schema import validate_and_clamp
        actions = ["navigate", "click", "scroll", "highlight", "search"]
        return [
            s for s in (
                validate_and_clamp({
                    "action": actions[i % len(actions)],
                    "target_label": f"Element {i}",
                    "cursor_x": 20.0 + i * 10,
                    "cursor_y": 30.0 + i * 10,
                    "scroll_percent": 0.0,
                    "confidence": confidence,
                    "reason": f"Reason {i}.",
                    "highlight_text": f"term {i}" if actions[i % len(actions)] in ("highlight", "search") else "",
                })
                for i in range(count)
            )
            if s is not None
        ]

    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTIONS_ENABLED",
        False,
    )
    def test_feature_flag_off_returns_empty_no_llm_call(self) -> None:
        from api.services.agent.interaction_suggestion.emitter import (
            maybe_emit_interaction_suggestion,
        )

        emit_event, factory = self._make_mocks()
        result = maybe_emit_interaction_suggestion(
            tool_id="browser.playwright.inspect",
            step_title="Inspect page",
            step_index=0,
            total_steps=3,
            step_why="",
            step_params={},
            task_context="",
            emit_event=emit_event,
            activity_event_factory=factory,
            suggestions_emitted_this_step=[],
        )
        assert result == []
        emit_event.assert_not_called()
        factory.assert_not_called()

    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTIONS_ENABLED",
        True,
    )
    def test_non_interactive_tool_returns_empty(self) -> None:
        from api.services.agent.interaction_suggestion.emitter import (
            maybe_emit_interaction_suggestion,
        )

        emit_event, factory = self._make_mocks()
        result = maybe_emit_interaction_suggestion(
            tool_id="analytics.ga4.report",
            step_title="GA4 report",
            step_index=1,
            total_steps=4,
            step_why="Pull KPI data.",
            step_params={},
            task_context="Generate monthly KPI report",
            emit_event=emit_event,
            activity_event_factory=factory,
            suggestions_emitted_this_step=[],
        )
        assert result == []
        emit_event.assert_not_called()

    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTIONS_ENABLED",
        True,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTION_MAX_PER_STEP",
        2,
    )
    def test_per_step_cap_already_full_returns_empty(self) -> None:
        from api.services.agent.interaction_suggestion.emitter import (
            maybe_emit_interaction_suggestion,
        )

        emit_event, factory = self._make_mocks()
        already_emitted: list[Any] = [0, 0]  # cap is 2, already at limit
        result = maybe_emit_interaction_suggestion(
            tool_id="browser.playwright.inspect",
            step_title="Step",
            step_index=0,
            total_steps=2,
            step_why="",
            step_params={},
            task_context="",
            emit_event=emit_event,
            activity_event_factory=factory,
            suggestions_emitted_this_step=already_emitted,
        )
        assert result == []
        emit_event.assert_not_called()

    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTIONS_ENABLED",
        True,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTION_MAX_PER_STEP",
        5,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTION_MIN_CONFIDENCE",
        0.6,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.generate_interaction_suggestion"
    )
    def test_low_confidence_suggestions_are_filtered(self, mock_gen: MagicMock) -> None:
        from api.services.agent.interaction_suggestion.emitter import (
            maybe_emit_interaction_suggestion,
        )

        # All 5 suggestions below threshold
        low_conf = self._make_suggestion_list(count=5, confidence=0.3)
        mock_gen.return_value = low_conf

        emit_event, factory = self._make_mocks()
        result = maybe_emit_interaction_suggestion(
            tool_id="browser.playwright.inspect",
            step_title="Inspect",
            step_index=2,
            total_steps=6,
            step_why="Scan the page.",
            step_params={"url": "https://example.com"},
            task_context="Audit the competitor site layout",
            emit_event=emit_event,
            activity_event_factory=factory,
            suggestions_emitted_this_step=[],
        )
        assert result == []
        emit_event.assert_not_called()

    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTIONS_ENABLED",
        True,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTION_MAX_PER_STEP",
        5,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTION_MIN_CONFIDENCE",
        0.4,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.generate_interaction_suggestion"
    )
    def test_successful_emission_emits_multiple_events(self, mock_gen: MagicMock) -> None:
        from api.services.agent.interaction_suggestion.emitter import (
            maybe_emit_interaction_suggestion,
        )

        suggestions = self._make_suggestion_list(count=5, confidence=0.9)
        mock_gen.return_value = suggestions

        emit_event = MagicMock(return_value={"event_type": "interaction_suggestion"})
        factory = MagicMock(return_value=MagicMock())

        emitted_list: list[Any] = []
        result = maybe_emit_interaction_suggestion(
            tool_id="browser.playwright.inspect",
            step_title="Navigate to login page",
            step_index=3,
            total_steps=8,
            step_why="User needs to log in before accessing the dashboard.",
            step_params={"url": "https://example.com/login"},
            task_context="Log in and retrieve dashboard metrics",
            emit_event=emit_event,
            activity_event_factory=factory,
            suggestions_emitted_this_step=emitted_list,
        )

        assert len(result) == 5
        assert emit_event.call_count == 5
        # All events must carry advisory guards
        for call in factory.call_args_list:
            kwargs = call[1]
            assert kwargs["event_type"] == "interaction_suggestion"
            assert kwargs["metadata"]["advisory"] is True
            assert kwargs["metadata"]["__no_execution"] is True
        # Per-step list was incremented for each emission
        assert len(emitted_list) == 5

    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTIONS_ENABLED",
        True,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTION_MAX_PER_STEP",
        3,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTION_MIN_CONFIDENCE",
        0.4,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.generate_interaction_suggestion"
    )
    def test_cap_limits_emissions_to_max_per_step(self, mock_gen: MagicMock) -> None:
        from api.services.agent.interaction_suggestion.emitter import (
            maybe_emit_interaction_suggestion,
        )

        # LLM returns 5 but cap is 3
        suggestions = self._make_suggestion_list(count=5, confidence=0.9)
        mock_gen.return_value = suggestions

        emit_event = MagicMock(return_value={"event_type": "interaction_suggestion"})
        factory = MagicMock(return_value=MagicMock())

        emitted_list: list[Any] = []
        result = maybe_emit_interaction_suggestion(
            tool_id="browser.playwright.inspect",
            step_title="Step",
            step_index=0,
            total_steps=3,
            step_why="",
            step_params={},
            task_context="",
            emit_event=emit_event,
            activity_event_factory=factory,
            suggestions_emitted_this_step=emitted_list,
        )
        assert len(result) == 3
        assert emit_event.call_count == 3
        assert len(emitted_list) == 3

    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTIONS_ENABLED",
        True,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.generate_interaction_suggestion"
    )
    def test_emission_only_mutates_local_step_list(
        self, mock_gen: MagicMock
    ) -> None:
        """Verify that emission only appends to the local per-step list —
        no other state is touched."""
        from api.services.agent.interaction_suggestion.emitter import (
            maybe_emit_interaction_suggestion,
        )

        suggestions = self._make_suggestion_list(count=5, confidence=0.8)
        mock_gen.return_value = suggestions

        emit_event = MagicMock(return_value={"event_type": "interaction_suggestion"})
        factory = MagicMock(return_value=MagicMock())

        other_list_a: list[str] = []
        other_list_b: list[dict[str, Any]] = []
        suggestions_emitted: list[Any] = []

        maybe_emit_interaction_suggestion(
            tool_id="docs.create",
            step_title="Create doc",
            step_index=0,
            total_steps=3,
            step_why="Create a new Google Doc for the report.",
            step_params={"title": "Q1 Report"},
            task_context="Create and share Q1 performance report",
            emit_event=emit_event,
            activity_event_factory=factory,
            suggestions_emitted_this_step=suggestions_emitted,
        )

        assert len(suggestions_emitted) >= 1
        assert other_list_a == []
        assert other_list_b == []

    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTIONS_ENABLED",
        True,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTION_MAX_PER_STEP",
        5,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.LLM_INTERACTION_SUGGESTION_MIN_CONFIDENCE",
        0.4,
    )
    @patch(
        "api.services.agent.interaction_suggestion.emitter.generate_interaction_suggestion"
    )
    def test_suggestion_index_included_in_metadata(self, mock_gen: MagicMock) -> None:
        from api.services.agent.interaction_suggestion.emitter import (
            maybe_emit_interaction_suggestion,
        )

        suggestions = self._make_suggestion_list(count=3, confidence=0.9)
        mock_gen.return_value = suggestions

        emit_event = MagicMock(return_value={"event_type": "interaction_suggestion"})
        factory = MagicMock(return_value=MagicMock())

        maybe_emit_interaction_suggestion(
            tool_id="browser.playwright.inspect",
            step_title="Step",
            step_index=1,
            total_steps=4,
            step_why="",
            step_params={},
            task_context="",
            emit_event=emit_event,
            activity_event_factory=factory,
            suggestions_emitted_this_step=[],
        )

        indices = [
            call[1]["metadata"]["suggestion_index"]
            for call in factory.call_args_list
        ]
        assert indices == [0, 1, 2]


if __name__ == "__main__":
    unittest.main()
