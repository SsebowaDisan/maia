from __future__ import annotations

from api.services.agent.connectors.browser_contact.fields import (
    parse_llm_required_field_mappings,
    scan_required_empty_fields,
)


class _FormEvaluateStub:
    def __init__(self, payload):
        self._payload = payload
        self.last_script = ""

    def evaluate(self, script: str):
        self.last_script = script
        return self._payload


def test_scan_required_empty_fields_normalizes_payload() -> None:
    form = _FormEvaluateStub(
        [
            {
                "dom_index": "4",
                "tag": " INPUT ",
                "input_type": " TEXT ",
                "label": " Telefonnummer * ",
                "placeholder": " Ihre Nummer ",
                "aria_label": "",
                "field_name": " phone ",
                "field_id": "contact-phone",
                "autocomplete": "TEL",
                "error_text": " Telefonnummer darf nicht leer sein ",
            },
            "skip",
        ]
    )
    rows = scan_required_empty_fields(form=form)

    assert len(rows) == 1
    assert "querySelectorAll" in form.last_script
    assert rows[0]["scan_index"] == 0
    assert rows[0]["dom_index"] == 4
    assert rows[0]["tag"] == "input"
    assert rows[0]["input_type"] == "text"
    assert rows[0]["label"] == "Telefonnummer *"
    assert rows[0]["autocomplete"] == "tel"


def test_parse_llm_required_field_mappings_filters_invalid_and_low_confidence() -> None:
    unresolved_fields = [
        {"scan_index": 0, "dom_index": 1, "label": "Telefonnummer"},
        {"scan_index": 1, "dom_index": 2, "label": "Ihre E-Mail"},
    ]
    intent_values = {
        "name": "Maia Team",
        "email": "disan@micrurus.com",
        "phone": "+1 617 555 0101",
        "company": "",
        "subject": "Inquiry",
        "message": "Hello",
    }
    payload = {
        "mappings": [
            {"field_index": 0, "intent": "phone", "confidence": 0.91},
            {"field_index": 1, "intent": "email", "confidence": 0.55},
            {"field_index": 1, "intent": "captcha", "confidence": 0.99},
            {"field_index": 9, "intent": "email", "confidence": 0.99},
        ]
    }
    mappings = parse_llm_required_field_mappings(
        payload=payload,
        unresolved_fields=unresolved_fields,
        intent_values=intent_values,
    )

    assert mappings == [
        {
            "field_index": 0,
            "intent": "phone",
            "value": "+1 617 555 0101",
            "confidence": 0.91,
            "reason": "",
        }
    ]


def test_parse_llm_required_field_mappings_prefers_best_confidence_per_field() -> None:
    unresolved_fields = [
        {"scan_index": 0, "dom_index": 3, "label": "Nom complet"},
    ]
    intent_values = {
        "name": "Maia Team",
        "email": "disan@micrurus.com",
        "phone": "",
        "company": "",
        "subject": "",
        "message": "",
    }
    payload = {
        "mappings": [
            {"field_index": 0, "intent": "name", "confidence": "medium", "reason": "name-like label"},
            {"field_index": 0, "intent": "name", "confidence": "high", "reason": "explicit full name field"},
        ]
    }
    mappings = parse_llm_required_field_mappings(
        payload=payload,
        unresolved_fields=unresolved_fields,
        intent_values=intent_values,
    )

    assert len(mappings) == 1
    assert mappings[0]["field_index"] == 0
    assert mappings[0]["intent"] == "name"
    assert mappings[0]["confidence"] == 0.9
    assert "explicit full name" in mappings[0]["reason"]
