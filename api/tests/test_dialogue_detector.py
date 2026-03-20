from __future__ import annotations

from api.services.agent.brain.dialogue_detector import _parse_response


def test_parse_response_preserves_interaction_type_from_llm() -> None:
    raw = """
    {
      "needs_dialogue": true,
      "dialogues": [
        {
          "target_agent": "analyst",
          "interaction_type": "evidence-request",
          "interaction_label": "request evidence",
          "scene_family": "browser",
          "scene_surface": "website",
          "operation_label": "Search for supporting sources",
          "question": "Can you provide evidence for the pricing claim?",
          "reason": "The output cites no source.",
          "urgency": "high"
        }
      ]
    }
    """
    parsed = _parse_response(raw, ["analyst", "writer"])
    assert len(parsed) == 1
    assert parsed[0]["target_agent"] == "analyst"
    assert parsed[0]["interaction_type"] == "evidence_request"
    assert parsed[0]["interaction_label"] == "request evidence"
    assert parsed[0]["scene_family"] == "browser"
    assert parsed[0]["scene_surface"] == "website"
    assert parsed[0]["operation_label"] == "Search for supporting sources"
    assert "evidence" in parsed[0]["question"].lower()
