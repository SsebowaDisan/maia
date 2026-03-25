from pathlib import Path

from api.services.observability.citation_trace import begin_trace, end_trace, snapshot_trace
from ktem.index.file.file_pipelines.index_pipeline import IndexPipeline
from maia.base import Document


class _DummyLoader:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def load_data(self, file_path, extra_info=None, **kwargs):
        self.calls.append(
            {
                "file_path": Path(file_path),
                "extra_info": dict(extra_info or {}),
            }
        )
        return [Document(text="sample", metadata=dict(extra_info or {}))]


def test_index_pipeline_forwards_uploaded_file_meta_to_loader(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "sample.txt"
    source_path.write_text("hello", encoding="utf-8")
    stored_path = tmp_path / "stored.txt"
    stored_path.write_text("hello", encoding="utf-8")

    loader = _DummyLoader()
    pipeline = IndexPipeline(
        loader=loader,
        splitter=None,
        Source=object(),
        Index=object(),
        VS=None,
        DS=object(),
        FSPath=tmp_path,
        user_id="u-1",
        private=False,
        embedding=object(),
    )

    monkeypatch.setattr(IndexPipeline, "get_id_if_exists", lambda self, _path: None)
    monkeypatch.setattr(IndexPipeline, "store_file", lambda self, *args, **kwargs: "file-1")
    monkeypatch.setattr(IndexPipeline, "get_stored_file_path", lambda self, _file_id: stored_path)
    monkeypatch.setattr(IndexPipeline, "finish", lambda self, file_id, file_path: file_id)

    def _fake_handle_docs(docs, file_id, file_name):
        if False:
            yield None
        return 0

    monkeypatch.setattr(IndexPipeline, "handle_docs", lambda self, docs, file_id, file_name: _fake_handle_docs(docs, file_id, file_name))

    uploaded_file_meta = {
        str(source_path.resolve()): {
            "checksum": "a" * 64,
            "size": 5,
            "ingestion_route": "heavy-pdf-paddleocr",
            "source_original_name": "sample.pdf",
        }
    }

    list(
        pipeline.stream(
            source_path,
            reindex=False,
            uploaded_file_meta=uploaded_file_meta,
        )
    )

    assert len(loader.calls) == 1
    extra_info = loader.calls[0]["extra_info"]
    assert extra_info["file_id"] == "file-1"
    assert extra_info["ingestion_route"] == "heavy-pdf-paddleocr"
    assert extra_info["source_original_name"] == "sample.pdf"
    assert extra_info["file_path"] == str(stored_path)


def test_index_pipeline_emits_trace_events(tmp_path: Path, monkeypatch) -> None:
    source_path = tmp_path / "sample.txt"
    source_path.write_text("# Page 1\nhello", encoding="utf-8")
    stored_path = tmp_path / "stored.txt"
    stored_path.write_text("# Page 1\nhello", encoding="utf-8")

    loader = _DummyLoader()
    pipeline = IndexPipeline(
        loader=loader,
        splitter=None,
        Source=object(),
        Index=object(),
        VS=None,
        DS=object(),
        FSPath=tmp_path,
        user_id="u-1",
        private=False,
        embedding=object(),
    )

    monkeypatch.setattr(IndexPipeline, "get_id_if_exists", lambda self, _path: None)
    monkeypatch.setattr(IndexPipeline, "store_file", lambda self, *args, **kwargs: "file-1")
    monkeypatch.setattr(IndexPipeline, "get_stored_file_path", lambda self, _file_id: stored_path)
    monkeypatch.setattr(IndexPipeline, "finish", lambda self, file_id, file_path: file_id)
    monkeypatch.setattr(IndexPipeline, "handle_chunks_docstore", lambda self, chunks, file_id: None)
    monkeypatch.setattr(IndexPipeline, "handle_chunks_vectorstore", lambda self, chunks, file_id: None)

    handle = begin_trace(kind="upload", user_id="u-1")
    try:
        list(
            pipeline.stream(
                source_path,
                reindex=False,
                uploaded_file_meta={
                    str(source_path.resolve()): {
                        "checksum": "a" * 64,
                        "size": 5,
                        "ingestion_route": "heavy-pdf-paddleocr",
                        "source_original_name": "sample.pdf",
                    }
                },
            )
        )
        trace = snapshot_trace()
    finally:
        end_trace(handle, emit_log=False)

    event_types = [event["type"] for event in trace["events"]]
    assert "index.stream_started" in event_types
    assert "index.file_stored" in event_types
    assert "index.loader_completed" in event_types
    assert "index.docs_loaded" in event_types
    assert "index.chunks_created" in event_types
    assert "index.persisted" in event_types
    assert "index.stream_completed" in event_types
