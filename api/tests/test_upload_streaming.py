from __future__ import annotations

import asyncio
import hashlib
from tempfile import SpooledTemporaryFile

import pytest
from fastapi import HTTPException, UploadFile

from api.routers import uploads


def _build_upload(*, filename: str, payload: bytes) -> UploadFile:
    handle = SpooledTemporaryFile()
    handle.write(payload)
    handle.seek(0)
    return UploadFile(filename=filename, file=handle)


def test_store_upload_file_streams_and_records_checksum(tmp_path):
    payload = b"maia upload payload" * 1024
    upload = _build_upload(filename="sample.txt", payload=payload)

    saved = asyncio.run(uploads._store_upload_file(upload, tmp_path))
    saved_path = tmp_path / "sample.txt"

    assert saved["name"] == "sample.txt"
    assert saved["path"] == str(saved_path.resolve())
    assert int(saved["size"]) == len(payload)
    assert str(saved["checksum"]) == hashlib.sha256(payload).hexdigest()
    assert saved_path.exists()
    assert saved_path.read_bytes() == payload


def test_store_upload_file_rejects_oversized_payload_and_cleans_partial_file(monkeypatch, tmp_path):
    payload = b"x" * 24
    upload = _build_upload(filename="big.bin", payload=payload)

    monkeypatch.setattr(uploads, "UPLOAD_MAX_FILE_SIZE_BYTES", 10)
    monkeypatch.setattr(uploads, "UPLOAD_STREAM_CHUNK_BYTES", 4)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(uploads._store_upload_file(upload, tmp_path))

    assert exc_info.value.status_code == 413
    assert not any(tmp_path.iterdir())
