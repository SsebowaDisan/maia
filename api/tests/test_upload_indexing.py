from __future__ import annotations

from pathlib import Path

from api.services.upload import indexing


class _DummyPipeline:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def stream(self, file_paths, reindex: bool = False, **kwargs):
        self.calls.append(
            {
                "file_paths": list(file_paths),
                "reindex": bool(reindex),
                "kwargs": dict(kwargs),
            }
        )
        return object()


class _DummyIndex:
    def __init__(self, index_id: int, pipeline: _DummyPipeline) -> None:
        self.id = index_id
        self.config = {}
        self._resources = {}
        self.pipeline = pipeline
        self.request_settings: dict | None = None

    def get_indexing_pipeline(self, settings, user_id):
        self.request_settings = dict(settings)
        return self.pipeline


def test_index_files_uses_performance_defaults_and_forwards_upload_meta(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=9, pipeline=pipeline)
    applied: dict[str, object] = {}

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(
        indexing,
        "collect_index_stream",
        lambda _stream: (
            ["file-1"],
            [],
            [{"file_name": "a.txt", "status": "success"}],
            [],
        ),
    )
    monkeypatch.setattr(
        indexing,
        "apply_upload_scope_to_sources",
        lambda **kwargs: applied.update(kwargs),
    )

    uploaded_meta = {
        "/tmp/a.txt": {"checksum": "a" * 64, "size": 123},
    }
    result = indexing.index_files(
        context=object(),  # type: ignore[arg-type]
        user_id="u-1",
        file_paths=[Path("/tmp/a.txt")],
        index_id=9,
        reindex=True,
        settings={},
        scope="chat_temp",
        uploaded_file_meta=uploaded_meta,
    )

    assert index.request_settings is not None
    assert (
        index.request_settings[f"index.options.{index.id}.reader_mode"]
        == indexing.UPLOAD_INDEX_READER_MODE
    )
    assert (
        index.request_settings[f"index.options.{index.id}.quick_index_mode"]
        == indexing.UPLOAD_INDEX_QUICK_MODE
    )
    assert len(pipeline.calls) == 1
    assert pipeline.calls[0]["kwargs"]["uploaded_file_meta"] == uploaded_meta
    assert result["file_ids"] == ["file-1"]
    assert applied["scope"] == "chat_temp"


def test_index_files_respects_explicit_reader_and_quick_mode_settings(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=3, pipeline=pipeline)

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(
        indexing,
        "collect_index_stream",
        lambda _stream: ([], [], [], []),
    )
    monkeypatch.setattr(indexing, "apply_upload_scope_to_sources", lambda **kwargs: None)

    settings = {
        "index.options.3.reader_mode": "ocr",
        "index.options.3.quick_index_mode": False,
    }
    indexing.index_files(
        context=object(),  # type: ignore[arg-type]
        user_id="u-2",
        file_paths=[Path("/tmp/b.pdf")],
        index_id=3,
        reindex=False,
        settings=settings,
        scope="persistent",
    )

    assert index.request_settings is not None
    assert index.request_settings["index.options.3.reader_mode"] == "ocr"
    assert index.request_settings["index.options.3.quick_index_mode"] is False


def test_index_files_auto_switches_to_ocr_for_image_like_files(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=5, pipeline=pipeline)

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(
        indexing,
        "collect_index_stream",
        lambda _stream: ([], [], [], []),
    )
    monkeypatch.setattr(indexing, "apply_upload_scope_to_sources", lambda **kwargs: None)

    indexing.index_files(
        context=object(),  # type: ignore[arg-type]
        user_id="u-3",
        file_paths=[Path("/tmp/photo.webp")],
        index_id=5,
        reindex=False,
        settings={},
        scope="persistent",
    )

    assert index.request_settings is not None
    assert index.request_settings["index.options.5.reader_mode"] == "ocr"


def test_index_files_auto_switches_to_ocr_for_pdf_with_images(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=6, pipeline=pipeline)

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(
        indexing,
        "collect_index_stream",
        lambda _stream: ([], [], [], []),
    )
    monkeypatch.setattr(indexing, "apply_upload_scope_to_sources", lambda **kwargs: None)
    monkeypatch.setattr(indexing, "_pdf_should_use_ocr", lambda path: True)

    indexing.index_files(
        context=object(),  # type: ignore[arg-type]
        user_id="u-4",
        file_paths=[Path("/tmp/notes-with-formulas.pdf")],
        index_id=6,
        reindex=False,
        settings={},
        scope="persistent",
    )

    assert index.request_settings is not None
    assert index.request_settings["index.options.6.reader_mode"] == "ocr"


def test_sample_page_indexes_spreads_across_document() -> None:
    indexes = indexing._sample_page_indexes(total_pages=100, sample_size=5)
    assert indexes[0] == 0
    assert indexes[-1] == 99
    assert len(indexes) == 5
    assert indexes == sorted(indexes)


def test_select_reader_mode_for_pdf_uses_ocr_when_probe_requests(monkeypatch) -> None:
    monkeypatch.setattr(indexing, "_pdf_should_use_ocr", lambda path: True)
    selected = indexing._select_reader_mode_for_file(
        configured_mode="default",
        file_path=Path("/tmp/book.pdf"),
    )
    assert selected == "ocr"


def test_count_image_pages_supports_subset_indexes(monkeypatch) -> None:
    pages = [object(), object(), object(), object()]
    image_page_ids = {id(pages[1]), id(pages[3])}
    monkeypatch.setattr(indexing, "_page_has_images", lambda page: id(page) in image_page_ids)

    assert indexing._count_image_pages(pages) == 2
    assert indexing._count_image_pages(pages, [0, 1, 2]) == 1
