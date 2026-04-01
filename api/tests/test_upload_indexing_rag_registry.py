from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from api.services.rag.types import IngestionStatus, SourceRecord, SourceType
from api.services.upload import indexing


def _source(
    *,
    source_id: str,
    owner_id: str,
    path: str,
    scope: str,
    index_id: int,
    created_at: str,
) -> SourceRecord:
    return SourceRecord(
        id=source_id,
        filename=f"{source_id}.pdf",
        source_type=SourceType.PDF,
        file_size=123,
        owner_id=owner_id,
        upload_url=path,
        status=IngestionStatus.CITATION_READY,
        metadata={"scope": scope, "index_id": index_id},
        created_at=created_at,
        updated_at=created_at,
        rag_ready=True,
        citation_ready=True,
    )


def test_list_indexed_files_reads_rag_registry(monkeypatch, tmp_path: Path) -> None:
    source_one_path = tmp_path / "one.pdf"
    source_one_path.write_bytes(b"one")
    source_two_path = tmp_path / "two.pdf"
    source_two_path.write_bytes(b"two")

    rows = [
        _source(
            source_id="s1",
            owner_id="u1",
            path=str(source_one_path),
            scope="chat_temp",
            index_id=9,
            created_at="2026-03-31T12:00:00+00:00",
        ),
        _source(
            source_id="s2",
            owner_id="u1",
            path=str(source_two_path),
            scope="persistent",
            index_id=9,
            created_at="2026-03-31T11:00:00+00:00",
        ),
        _source(
            source_id="s3",
            owner_id="u2",
            path=str(source_two_path),
            scope="persistent",
            index_id=9,
            created_at="2026-03-31T10:00:00+00:00",
        ),
    ]
    monkeypatch.setattr(
        indexing,
        "list_registered_sources",
        lambda **kwargs: [
            row
            for row in rows
            if row.owner_id == kwargs["owner_id"]
            and (kwargs["include_chat_temp"] or row.metadata.get("scope") != "chat_temp")
            and int(row.metadata.get("index_id") or 0) == int(kwargs["index_id"] or 0)
        ],
    )

    hidden = indexing.list_indexed_files(
        context=None,
        user_id="u1",
        include_chat_temp=False,
        index_id=9,
    )
    assert [item.id for item in hidden.files] == ["s2"]

    shown = indexing.list_indexed_files(
        context=None,
        user_id="u1",
        include_chat_temp=True,
        index_id=9,
    )
    assert [item.id for item in shown.files] == ["s1", "s2"]
    assert shown.files[0].scope == "chat_temp"


def test_resolve_indexed_file_path_uses_registry(monkeypatch, tmp_path: Path) -> None:
    source_path = tmp_path / "resolve.pdf"
    source_path.write_bytes(b"resolve")

    monkeypatch.setattr(
        indexing,
        "resolve_registered_source_path",
        lambda **kwargs: (source_path, "resolve.pdf")
        if kwargs.get("source_id") == "ok"
        else None,
    )

    resolved_path, resolved_name = indexing.resolve_indexed_file_path(
        context=None,
        user_id="u1",
        file_id="ok",
        index_id=9,
    )
    assert Path(resolved_path) == source_path
    assert resolved_name == "resolve.pdf"

    with pytest.raises(HTTPException) as exc_info:
        indexing.resolve_indexed_file_path(
            context=None,
            user_id="u1",
            file_id="missing",
            index_id=9,
        )
    assert exc_info.value.status_code == 404
