from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
for rel in ("libs/ktem", "libs/maia"):
    path = ROOT / rel
    if path.exists():
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)

from api.services import conversation_service
from api.services.chat import conversation_naming
from api.services.chat.conversation_naming import (
    CONVERSATION_ICON_KEY_FIELD,
    CONVERSATION_ICON_REVIEWED_FIELD,
    DEFAULT_CONVERSATION_ICON_KEY,
)


class _FakeQuery:
    def where(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self


class _FakeExecResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = list(rows)
        self.commit_called = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def exec(self, _query):
        return _FakeExecResult(self._rows)

    def add(self, _row):
        return None

    def commit(self):
        self.commit_called = True

    def refresh(self, _row):
        return None


def _conversation_row(*, name: str, icon_key: str, icon_reviewed: bool) -> SimpleNamespace:
    return SimpleNamespace(
        id="conv-1",
        user="u1",
        is_public=False,
        name=name,
        data_source={
            "messages": [["make research about machine learning", ""]],
            "state": {"mode": "ask"},
            CONVERSATION_ICON_KEY_FIELD: icon_key,
            CONVERSATION_ICON_REVIEWED_FIELD: icon_reviewed,
        },
        date_created=datetime.now(timezone.utc),
        date_updated=datetime.now(timezone.utc),
    )


def test_list_conversations_backfills_legacy_default_icon(monkeypatch) -> None:
    row = _conversation_row(
        name="Machine Learning Research",
        icon_key=DEFAULT_CONVERSATION_ICON_KEY,
        icon_reviewed=False,
    )
    fake_session = _FakeSession([row])
    monkeypatch.setattr(conversation_service, "Session", lambda _engine: fake_session)
    monkeypatch.setattr(conversation_service, "select", lambda *_args, **_kwargs: _FakeQuery())
    monkeypatch.setattr(
        conversation_service,
        "generate_conversation_identity",
        lambda *_args, **_kwargs: ("Machine Learning Research", "search"),
    )

    rows = conversation_service.list_conversations(user_id="u1")

    assert rows[0]["icon_key"] == "search"
    assert row.data_source[CONVERSATION_ICON_KEY_FIELD] == "search"
    assert row.data_source[CONVERSATION_ICON_REVIEWED_FIELD] is True
    assert fake_session.commit_called is True


def test_list_conversations_skips_reclassification_when_reviewed_and_generic(monkeypatch) -> None:
    row = _conversation_row(
        name="General follow up",
        icon_key=DEFAULT_CONVERSATION_ICON_KEY,
        icon_reviewed=True,
    )
    row.data_source["messages"] = [["hello there", ""]]
    fake_session = _FakeSession([row])
    called = {"count": 0}

    def _count_call(*_args, **_kwargs):
        called["count"] += 1
        return ("Machine Learning Research", "search")

    monkeypatch.setattr(conversation_service, "Session", lambda _engine: fake_session)
    monkeypatch.setattr(conversation_service, "select", lambda *_args, **_kwargs: _FakeQuery())
    monkeypatch.setattr(conversation_service, "generate_conversation_identity", _count_call)
    monkeypatch.setattr(
        conversation_service,
        "infer_conversation_icon_key",
        lambda *_args, **_kwargs: DEFAULT_CONVERSATION_ICON_KEY,
    )

    rows = conversation_service.list_conversations(user_id="u1")

    assert rows[0]["icon_key"] == DEFAULT_CONVERSATION_ICON_KEY
    assert called["count"] == 0
    assert fake_session.commit_called is False


def test_infer_conversation_icon_key_uses_keyword_fallback_for_documents(monkeypatch) -> None:
    monkeypatch.setattr(conversation_naming, "call_json_response", lambda **_kwargs: {})

    icon_key = conversation_naming.infer_conversation_icon_key(
        "what is this pdf about?",
        agent_mode="ask",
    )

    assert icon_key == "file-text"


def test_list_conversations_upgrades_reviewed_default_icon_when_prompt_is_specific(monkeypatch) -> None:
    row = _conversation_row(
        name="what is this pdf about",
        icon_key=DEFAULT_CONVERSATION_ICON_KEY,
        icon_reviewed=True,
    )
    fake_session = _FakeSession([row])

    monkeypatch.setattr(conversation_service, "Session", lambda _engine: fake_session)
    monkeypatch.setattr(conversation_service, "select", lambda *_args, **_kwargs: _FakeQuery())
    monkeypatch.setattr(
        conversation_service,
        "infer_conversation_icon_key",
        lambda *_args, **_kwargs: "file-text",
    )

    rows = conversation_service.list_conversations(user_id="u1")

    assert rows[0]["icon_key"] == "file-text"
    assert row.data_source[CONVERSATION_ICON_KEY_FIELD] == "file-text"
    assert row.data_source[CONVERSATION_ICON_REVIEWED_FIELD] is True
    assert fake_session.commit_called is True
