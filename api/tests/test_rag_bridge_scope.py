from __future__ import annotations

import asyncio
from types import SimpleNamespace

from api.services.rag import bridge


def test_run_query_unscoped_uses_accessible_source_ids(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "list_registered_sources",
        lambda **kwargs: [SimpleNamespace(id="lib-1"), SimpleNamespace(id="tmp-2")],
    )
    captured: dict[str, object] = {}

    async def _fake_query_sources(question: str, source_ids: list[str], owner_id: str, config, web_context: str = ""):
        captured["question"] = question
        captured["source_ids"] = source_ids
        captured["owner_id"] = owner_id
        captured["web_context"] = web_context
        return {"ok": True}

    monkeypatch.setattr(bridge, "query_sources", _fake_query_sources)

    result = asyncio.run(
        bridge._run_query_unscoped(
            question="what is the pdf about",
            owner_id="user-1",
            config={},
            web_context="",
        )
    )

    assert result == {"ok": True}
    assert captured["source_ids"] == ["lib-1", "tmp-2"]
    assert captured["owner_id"] == ""


def test_run_rag_query_bridge_filters_selected_source_ids_to_accessible(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "list_registered_sources",
        lambda **kwargs: [SimpleNamespace(id="allowed-1")],
    )
    monkeypatch.setattr(bridge, "_payload_to_legacy_format", lambda payload: payload)
    captured: dict[str, object] = {}

    async def _fake_query_file(question: str, source_id: str, owner_id: str, cfg, web_context: str = ""):
        captured["question"] = question
        captured["source_id"] = source_id
        captured["owner_id"] = owner_id
        return {"ok": True}

    monkeypatch.setattr(bridge, "query_file", _fake_query_file)

    result = asyncio.run(
        bridge.run_rag_query_bridge(
            question="summary",
            source_ids=["denied-1", "allowed-1"],
            owner_id="user-1",
        )
    )

    assert result == {"ok": True}
    assert captured["source_id"] == "allowed-1"
    assert captured["owner_id"] == ""
