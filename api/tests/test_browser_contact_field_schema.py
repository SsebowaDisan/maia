from __future__ import annotations

from api.services.agent.connectors.browser_contact.field_schema import (
    extract_form_schema,
    find_submit_control,
    list_required_empty_fields,
)


class _NthLocator:
    def __init__(self, index: int, *, visible: bool = True) -> None:
        self.index = index
        self._visible = visible

    def is_visible(self) -> bool:
        return self._visible


class _LocatorCollection:
    def __init__(self, *, hidden_indexes: set[int] | None = None) -> None:
        self._hidden_indexes = hidden_indexes or set()

    def nth(self, index: int):
        return _NthLocator(index, visible=index not in self._hidden_indexes)


class _FormStub:
    def __init__(self, payload):
        self._payload = payload

    def evaluate(self, script: str):
        return self._payload

    def locator(self, _selector: str):
        return _LocatorCollection()


def test_extract_form_schema_normalizes_and_filters_required_empty() -> None:
    form = _FormStub(
        [
            {
                "dom_index": "0",
                "tag": "INPUT",
                "input_type": "EMAIL",
                "label": "E-mail *",
                "placeholder": "",
                "aria_label": "",
                "autocomplete": "EMAIL",
                "required": True,
                "empty": True,
                "disabled": False,
                "visible": True,
            },
            {
                "dom_index": "1",
                "tag": "INPUT",
                "input_type": "TEXT",
                "label": "Optional",
                "required": False,
                "empty": True,
                "disabled": False,
                "visible": True,
            },
        ]
    )
    schema = extract_form_schema(form=form)
    unresolved = list_required_empty_fields(form=form)

    assert len(schema) == 2
    assert schema[0]["input_type"] == "email"
    assert schema[0]["autocomplete"] == "email"
    assert len(unresolved) == 1
    assert unresolved[0]["field_label"] == "E-mail *"


def test_find_submit_control_prefers_submit_input_type() -> None:
    form = _FormStub(
        [
            {
                "dom_index": 0,
                "tag": "button",
                "input_type": "button",
                "label": "Preview",
                "required": False,
                "empty": True,
                "disabled": False,
                "visible": True,
            },
            {
                "dom_index": 1,
                "tag": "button",
                "input_type": "submit",
                "label": "Send",
                "required": False,
                "empty": True,
                "disabled": False,
                "visible": True,
            },
        ]
    )
    control, meta = find_submit_control(form=form)

    assert control is not None
    assert meta is not None
    assert meta["input_type"] == "submit"

