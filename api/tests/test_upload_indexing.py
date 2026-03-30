from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from api.services.upload import indexing
from api.services.observability.citation_trace import begin_trace, end_trace, snapshot_trace


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
        lambda _stream, **_: (
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
        str(Path("/tmp/a.txt").resolve()): {"checksum": "a" * 64, "size": 123},
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
    passed_meta = pipeline.calls[0]["kwargs"]["uploaded_file_meta"]
    assert str(Path("/tmp/a.txt").resolve()) in passed_meta
    assert passed_meta[str(Path("/tmp/a.txt").resolve())]["checksum"] == "a" * 64
    assert result["file_ids"] == ["file-1"]
    assert applied["scope"] == "chat_temp"


def test_index_files_respects_explicit_reader_and_quick_mode_settings(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=3, pipeline=pipeline)

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(
        indexing,
        "collect_index_stream",
        lambda _stream, **_: ([], [], [], []),
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
        lambda _stream, **_: ([], [], [], []),
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
        lambda _stream, **_: ([], [], [], []),
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


def test_collect_index_stream_raises_canceled_with_partial_file_ids() -> None:
    responses = iter(
        [
            SimpleNamespace(
                channel="index",
                content={"file_name": "sample.pdf", "status": "success", "file_id": "file-1"},
                text=None,
            ),
            SimpleNamespace(channel="debug", content="still working", text="still working"),
        ]
    )
    checks = {"count": 0}

    def should_cancel() -> bool:
        checks["count"] += 1
        return checks["count"] >= 2

    with pytest.raises(indexing.IndexingCanceledError) as exc_info:
        indexing.collect_index_stream(responses, should_cancel=should_cancel)

    assert exc_info.value.file_ids == ["file-1"]
    assert len(exc_info.value.items) == 1


def test_index_files_routes_heavy_pdf_to_paddle(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=12, pipeline=pipeline)

    paddle_calls: list[dict] = []
    parser_calls: list[dict] = []

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(
        indexing,
        "_classify_pdf_ingestion_route",
        lambda _path, **_kwargs: {"route": "heavy", "use_ocr": True, "reason": "heavy-image-ratio"},
    )
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_ENABLED", True)

    def _fake_paddle(**kwargs):
        paddle_calls.append(dict(kwargs))
        return {"file_ids": ["paddle-1"], "errors": [], "items": [], "debug": ["paddle-ok"]}

    def _fake_parser(**kwargs):
        parser_calls.append(dict(kwargs))
        return {"file_ids": ["parser-1"], "errors": [], "items": [], "debug": []}

    monkeypatch.setattr(indexing, "_index_pdf_with_paddleocr_route", _fake_paddle)
    monkeypatch.setattr(indexing, "_run_index_pipeline_for_file", _fake_parser)
    monkeypatch.setattr(indexing, "apply_upload_scope_to_sources", lambda **kwargs: None)

    result = indexing.index_files(
        context=object(),  # type: ignore[arg-type]
        user_id="u-heavy",
        file_paths=[Path("/tmp/heavy.pdf")],
        index_id=12,
        reindex=False,
        settings={},
    )

    assert result["file_ids"] == ["paddle-1"]
    assert len(paddle_calls) == 1
    assert len(parser_calls) == 0


def test_index_files_keeps_math_native_pdf_off_remote_paddle(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=16, pipeline=pipeline)

    paddle_calls: list[dict] = []
    parser_calls: list[dict] = []

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(
        indexing,
        "_classify_pdf_ingestion_route",
        lambda _path, **_kwargs: {
            "route": "heavy",
            "use_ocr": True,
            "reason": "heavy-low-text-ratio",
            "image_pages_all": 0,
        },
    )
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_ENABLED", True)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_VL_API_ENABLED", True)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_VL_API_URL", "https://example.test/paddle")
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_VL_API_TOKEN", "token")

    def _fake_paddle(**kwargs):
        paddle_calls.append(dict(kwargs))
        return {"file_ids": ["paddle-1"], "errors": [], "items": [], "debug": []}

    def _fake_parser(**kwargs):
        parser_calls.append(dict(kwargs))
        return {"file_ids": ["parser-1"], "errors": [], "items": [], "debug": []}

    monkeypatch.setattr(indexing, "_index_pdf_with_paddleocr_route", _fake_paddle)
    monkeypatch.setattr(indexing, "_run_index_pipeline_for_file", _fake_parser)
    monkeypatch.setattr(indexing, "apply_upload_scope_to_sources", lambda **kwargs: None)

    result = indexing.index_files(
        context=object(),  # type: ignore[arg-type]
        user_id="u-math-native",
        file_paths=[Path("/tmp/math-native.pdf")],
        index_id=16,
        reindex=False,
        settings={},
    )

    assert result["file_ids"] == ["parser-1"]
    assert len(parser_calls) == 1
    assert len(paddle_calls) == 0


def test_index_files_falls_back_to_current_parser_when_paddle_fails(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=13, pipeline=pipeline)

    parser_calls: list[dict] = []

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(
        indexing,
        "_classify_pdf_ingestion_route",
        lambda _path, **_kwargs: {
            "route": "heavy",
            "use_ocr": True,
            "reason": "heavy-image-ratio",
            "image_pages_all": 2,
        },
    )
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_ENABLED", True)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_VL_API_ENABLED", True)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_VL_API_URL", "https://example.test/paddle")
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_VL_API_TOKEN", "token")

    def _raise_paddle(**_kwargs):
        raise RuntimeError("paddle unavailable")

    def _fake_parser(**kwargs):
        parser_calls.append(dict(kwargs))
        return {"file_ids": ["fallback-1"], "errors": [], "items": [], "debug": []}

    monkeypatch.setattr(indexing, "_index_pdf_with_paddleocr_route", _raise_paddle)
    monkeypatch.setattr(indexing, "_run_index_pipeline_for_file", _fake_parser)
    monkeypatch.setattr(indexing, "apply_upload_scope_to_sources", lambda **kwargs: None)

    result = indexing.index_files(
        context=object(),  # type: ignore[arg-type]
        user_id="u-fallback",
        file_paths=[Path("/tmp/heavy-fallback.pdf")],
        index_id=13,
        reindex=True,
        settings={},
    )

    assert result["file_ids"] == ["fallback-1"]
    assert len(parser_calls) == 1
    assert parser_calls[0]["route"] == "heavy-pdf-fallback"
    assert parser_calls[0]["reader_mode"] == "ocr"
    assert any("PaddleOCR failed" in message for message in result["debug"])


def test_classify_pdf_ingestion_route_prefers_native_text_when_fitz_recovers_math_pages(
    monkeypatch, tmp_path: Path
) -> None:
    pdf_path = tmp_path / "math.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    class _FakePypdfPage:
        def extract_text(self):
            return ""

    class _FakePdfReader:
        def __init__(self, _path: str) -> None:
            self.pages = [_FakePypdfPage(), _FakePypdfPage()]

    class _FakeFitzPage:
        def get_text(self, mode: str = "text") -> str:
            assert mode == "text"
            return "E = mc^2 and integral_0^1 x^2 dx = 1/3 with theorem context"

    class _FakeFitzDoc:
        page_count = 2

        def load_page(self, _index: int) -> _FakeFitzPage:
            return _FakeFitzPage()

        def close(self) -> None:
            return None

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=_FakePdfReader))
    monkeypatch.setitem(sys.modules, "fitz", SimpleNamespace(open=lambda _path: _FakeFitzDoc()))

    result = indexing._classify_pdf_ingestion_route_cached(
        str(pdf_path.resolve()),
        0,
        pdf_path.stat().st_size,
    )

    assert result["route"] == "normal"
    assert result["use_ocr"] is False
    assert result["fitz_native_text_pages_sampled"] >= 1


def test_classify_pdf_ingestion_route_skips_ocr_for_image_heavy_pdf_with_majority_native_text(
    monkeypatch, tmp_path: Path
) -> None:
    pdf_path = tmp_path / "technical-heavy.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    class _FakePypdfPage:
        def __init__(self, idx: int) -> None:
            self.idx = idx

        def extract_text(self):
            return (
                ""
                if self.idx < 1
                else "native text present " * 12
            )

    class _FakePdfReader:
        def __init__(self, _path: str) -> None:
            self.pages = [_FakePypdfPage(idx) for idx in range(4)]

    class _FakeFitzPage:
        def __init__(self, idx: int) -> None:
            self.idx = idx

        def get_text(self, mode: str = "text") -> str:
            assert mode == "text"
            return (
                ""
                if self.idx < 1
                else "technical native text recovered from fitz " * 12
            )

    class _FakeFitzDoc:
        page_count = 4

        def load_page(self, index: int) -> _FakeFitzPage:
            return _FakeFitzPage(index)

        def close(self) -> None:
            return None

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=_FakePdfReader))
    monkeypatch.setitem(sys.modules, "fitz", SimpleNamespace(open=lambda _path: _FakeFitzDoc()))
    monkeypatch.setattr(
        indexing,
        "_detect_pdf_images_with_pymupdf",
        lambda *_args, **_kwargs: (set(range(4)), 4),
    )

    result = indexing._classify_pdf_ingestion_route_cached(
        str(pdf_path.resolve()),
        0,
        pdf_path.stat().st_size,
    )

    assert result["route"] == "normal"
    assert result["use_ocr"] is False
    assert result["reason"] == "fitz-native-text-majority"
    assert result["fitz_native_text_pages_sampled"] == 3


def test_index_files_reuses_existing_file_when_duplicate_upload_hits_parser(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=14, pipeline=pipeline)

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(indexing, "apply_upload_scope_to_sources", lambda **kwargs: None)
    monkeypatch.setattr(indexing, "_should_route_pdf_to_paddle", lambda **kwargs: False)
    monkeypatch.setattr(
        indexing,
        "_classify_pdf_ingestion_route",
        lambda _path, **_kwargs: {"route": "normal", "use_ocr": False, "reason": "normal"},
    )
    monkeypatch.setattr(
        indexing,
        "_run_index_pipeline_for_file",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError(
                "File sample.pdf already indexed. Please rerun with reindex=True to force reindexing."
            )
        ),
    )
    monkeypatch.setattr(indexing, "_resolve_existing_file_id_for_upload", lambda **kwargs: "existing-1")
    monkeypatch.setattr(indexing, "_source_ids_have_document_relations", lambda **kwargs: True)

    result = indexing.index_files(
        context=object(),  # type: ignore[arg-type]
        user_id="u-existing",
        file_paths=[Path("/tmp/sample.pdf")],
        index_id=14,
        reindex=False,
        settings={},
        scope="chat_temp",
        uploaded_file_meta={str(Path("/tmp/sample.pdf").resolve()): {"checksum": "a" * 64}},
    )

    assert result["file_ids"] == ["existing-1"]
    assert result["items"]
    assert result["items"][0]["status"] == "success"
    assert result["items"][0]["file_id"] == "existing-1"


def test_index_files_schedules_pdf_precompute_after_success(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=18, pipeline=pipeline)
    scheduled: list[Path] = []

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(indexing, "apply_upload_scope_to_sources", lambda **kwargs: None)
    monkeypatch.setattr(indexing, "_should_route_pdf_to_paddle", lambda **kwargs: False)
    monkeypatch.setattr(
        indexing,
        "_classify_pdf_ingestion_route",
        lambda _path, **_kwargs: {"route": "normal", "use_ocr": False, "reason": "normal"},
    )
    monkeypatch.setattr(
        indexing,
        "_run_index_pipeline_for_file",
        lambda **kwargs: {
            "file_ids": ["fresh-1"],
            "errors": [],
            "items": [
                {
                    "file_name": "sample.pdf",
                    "status": "success",
                    "message": "Indexed",
                    "file_id": "fresh-1",
                }
            ],
            "debug": [],
        },
    )
    monkeypatch.setattr(
        indexing,
        "precompute_page_units_background",
        lambda file_path: scheduled.append(Path(file_path)),
    )

    result = indexing.index_files(
        context=object(),  # type: ignore[arg-type]
        user_id="u-precompute",
        file_paths=[Path("/tmp/sample.pdf")],
        index_id=18,
        reindex=False,
        settings={},
        scope="chat_temp",
    )

    assert result["file_ids"] == ["fresh-1"]
    assert scheduled == [Path("/tmp/sample.pdf")]
    assert any("scheduled page-unit precompute" in message for message in result["debug"])


def test_index_files_reuses_existing_file_when_paddle_fallback_hits_duplicate(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=15, pipeline=pipeline)

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(indexing, "apply_upload_scope_to_sources", lambda **kwargs: None)
    monkeypatch.setattr(
        indexing,
        "_classify_pdf_ingestion_route",
        lambda _path, **_kwargs: {"route": "heavy", "use_ocr": True, "reason": "heavy-low-text-ratio"},
    )
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_ENABLED", True)
    monkeypatch.setattr(indexing, "_index_pdf_with_paddleocr_route", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("paddle unavailable")))
    monkeypatch.setattr(
        indexing,
        "_run_index_pipeline_for_file",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError(
                "File sample.pdf already indexed. Please rerun with reindex=True to force reindexing."
            )
        ),
    )
    monkeypatch.setattr(indexing, "_resolve_existing_file_id_for_upload", lambda **kwargs: "existing-fallback-1")
    monkeypatch.setattr(indexing, "_source_ids_have_document_relations", lambda **kwargs: True)

    result = indexing.index_files(
        context=object(),  # type: ignore[arg-type]
        user_id="u-existing-fallback",
        file_paths=[Path("/tmp/sample.pdf")],
        index_id=15,
        reindex=False,
        settings={},
        scope="chat_temp",
        uploaded_file_meta={str(Path("/tmp/sample.pdf").resolve()): {"checksum": "a" * 64}},
    )

    assert result["file_ids"] == ["existing-fallback-1"]
    assert result["items"]
    assert result["items"][0]["status"] == "success"
    assert result["items"][0]["file_id"] == "existing-fallback-1"


def test_index_files_schedules_pdf_precompute_after_duplicate_reuse(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=19, pipeline=pipeline)
    scheduled: list[Path] = []

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(indexing, "apply_upload_scope_to_sources", lambda **kwargs: None)
    monkeypatch.setattr(indexing, "_should_route_pdf_to_paddle", lambda **kwargs: False)
    monkeypatch.setattr(
        indexing,
        "_classify_pdf_ingestion_route",
        lambda _path, **_kwargs: {"route": "normal", "use_ocr": False, "reason": "normal"},
    )
    monkeypatch.setattr(
        indexing,
        "_run_index_pipeline_for_file",
        lambda **kwargs: (_ for _ in ()).throw(
            ValueError(
                "File sample.pdf already indexed. Please rerun with reindex=True to force reindexing."
            )
        ),
    )
    monkeypatch.setattr(indexing, "_resolve_existing_file_id_for_upload", lambda **kwargs: "existing-2")
    monkeypatch.setattr(indexing, "_source_ids_have_document_relations", lambda **kwargs: True)
    monkeypatch.setattr(
        indexing,
        "precompute_page_units_background",
        lambda file_path: scheduled.append(Path(file_path)),
    )

    result = indexing.index_files(
        context=object(),  # type: ignore[arg-type]
        user_id="u-existing-2",
        file_paths=[Path("/tmp/sample.pdf")],
        index_id=19,
        reindex=False,
        settings={},
        scope="chat_temp",
        uploaded_file_meta={str(Path("/tmp/sample.pdf").resolve()): {"checksum": "c" * 64}},
    )

    assert result["file_ids"] == ["existing-2"]
    assert result["items"][0]["status"] == "success"
    assert scheduled == [Path("/tmp/sample.pdf")]
    assert any("scheduled page-unit precompute" in message for message in result["debug"])


def test_index_files_emits_trace_events_for_pdf_route(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=22, pipeline=pipeline)

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(indexing, "apply_upload_scope_to_sources", lambda **kwargs: None)
    monkeypatch.setattr(
        indexing,
        "_classify_pdf_ingestion_route",
        lambda _path, **_kwargs: {
            "route": "heavy",
            "use_ocr": True,
            "reason": "heavy-image-ratio",
            "image_ratio_all": 0.8,
            "low_text_ratio_sampled": 0.9,
        },
    )
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_ENABLED", True)
    monkeypatch.setattr(
        indexing,
        "_index_pdf_with_paddleocr_route",
        lambda **kwargs: {
            "file_ids": ["trace-1"],
            "errors": [],
            "items": [{"file_name": "trace.pdf", "status": "success", "file_id": "trace-1"}],
            "debug": [],
        },
    )
    monkeypatch.setattr(indexing, "precompute_page_units_background", lambda _path: None)

    handle = begin_trace(kind="upload", user_id="trace-user")
    try:
        indexing.index_files(
            context=object(),  # type: ignore[arg-type]
            user_id="trace-user",
            file_paths=[Path("/tmp/trace.pdf")],
            index_id=22,
            reindex=False,
            settings={},
        )
        trace = snapshot_trace()
    finally:
        end_trace(handle, emit_log=False)

    event_types = [event["type"] for event in trace["events"]]
    assert "index.started" in event_types
    assert "index.route_selected" in event_types
    assert "index.ocr_route_started" in event_types
    assert "index.file_completed" in event_types


def test_index_files_reuses_existing_file_when_pipeline_returns_duplicate_failure_item(
    monkeypatch,
) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=17, pipeline=pipeline)

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(indexing, "apply_upload_scope_to_sources", lambda **kwargs: None)
    monkeypatch.setattr(indexing, "_should_route_pdf_to_paddle", lambda **kwargs: False)
    monkeypatch.setattr(
        indexing,
        "_classify_pdf_ingestion_route",
        lambda _path, **_kwargs: {"route": "normal", "use_ocr": False, "reason": "normal"},
    )
    monkeypatch.setattr(
        indexing,
        "_run_index_pipeline_for_file",
        lambda **kwargs: {
            "file_ids": [],
            "errors": [
                "File sample.pdf already indexed. Please rerun with reindex=True to force reindexing."
            ],
            "items": [
                {
                    "file_name": "sample.pdf",
                    "status": "failed",
                    "message": "File sample.pdf already indexed. Please rerun with reindex=True to force reindexing.",
                    "file_id": None,
                }
            ],
            "debug": ["Indexing [1/1]: sample.pdf"],
        },
    )
    monkeypatch.setattr(indexing, "_resolve_existing_file_id_for_upload", lambda **kwargs: "existing-item-1")
    monkeypatch.setattr(indexing, "_source_ids_have_document_relations", lambda **kwargs: True)

    result = indexing.index_files(
        context=object(),  # type: ignore[arg-type]
        user_id="u-existing-item",
        file_paths=[Path("/tmp/sample.pdf")],
        index_id=17,
        reindex=False,
        settings={},
        scope="chat_temp",
        uploaded_file_meta={str(Path("/tmp/sample.pdf").resolve()): {"checksum": "b" * 64}},
    )

    assert result["file_ids"] == ["existing-item-1"]
    assert result["errors"] == []
    assert result["items"][0]["status"] == "success"
    assert result["items"][0]["file_id"] == "existing-item-1"


def test_run_upload_startup_checks_warns_when_dependencies_missing(monkeypatch) -> None:
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_STARTUP_CHECK", True)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_STARTUP_STRICT", False)
    monkeypatch.setattr(indexing, "UPLOAD_INDEX_READER_MODE", "default")
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_ENABLED", True)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_STARTUP_WARMUP", False)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_VL_API_ENABLED", False)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_VL_API_URL", "")
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_VL_API_TOKEN", "")

    imported_modules: list[str] = []
    real_import = __import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        imported_modules.append(str(name))
        if name in {"fitz", "paddleocr"}:
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    warnings: list[str] = []
    monkeypatch.setattr("builtins.__import__", _fake_import)
    monkeypatch.setattr(indexing.logger, "info", lambda msg: warnings.append(str(msg)))

    notices = indexing.run_upload_startup_checks()

    assert notices
    assert "dependencies missing" in notices[0]
    assert warnings
    assert "fitz" in ",".join(imported_modules)
    assert "paddleocr" in ",".join(imported_modules)


def test_run_upload_startup_checks_strict_mode_raises_for_missing_dependencies(
    monkeypatch,
) -> None:
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_STARTUP_CHECK", True)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_STARTUP_STRICT", False)
    monkeypatch.setattr(indexing, "UPLOAD_INDEX_READER_MODE", "paddleocr")
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_ENABLED", True)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_STARTUP_WARMUP", False)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_VL_API_ENABLED", False)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_VL_API_URL", "")
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_VL_API_TOKEN", "")
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_STARTUP_STRICT", True)

    real_import = __import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name in {"fitz", "paddleocr"}:
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _fake_import)

    with pytest.raises(RuntimeError) as exc_info:
        indexing.run_upload_startup_checks()

    assert "dependencies missing" in str(exc_info.value)


def test_apply_vlm_review_upgrade_only_upgrades_normal(monkeypatch) -> None:
    monkeypatch.setattr(indexing, "UPLOAD_PDF_VLM_REVIEW_ENABLED", True)
    monkeypatch.setattr(
        indexing,
        "_review_pdf_route_with_vlm",
        lambda *_args, **_kwargs: {
            "enabled": True,
            "upgrade": True,
            "checked_pages": 3,
            "reason": "vlm-visual-trigger",
        },
    )

    result = indexing._apply_vlm_review_upgrade(
        Path("/tmp/sample.pdf"),
        {
            "route": "normal",
            "use_ocr": False,
            "reason": "normal",
            "total_pages": 10,
        },
        sampled_indexes=[0, 1, 2],
    )

    assert result["route"] == "heavy"
    assert result["use_ocr"] is True
    assert result["reason"] == "vlm-visual-trigger"
    assert result["vlm_review"] == "upgraded-to-heavy"
    assert result["vlm_review_checked_pages"] == 3


def test_apply_vlm_review_upgrade_never_downgrades_heavy(monkeypatch) -> None:
    monkeypatch.setattr(indexing, "UPLOAD_PDF_VLM_REVIEW_ENABLED", True)
    monkeypatch.setattr(
        indexing,
        "_review_pdf_route_with_vlm",
        lambda *_args, **_kwargs: {
            "enabled": True,
            "upgrade": False,
            "checked_pages": 2,
            "reason": "kept-normal",
        },
    )

    result = indexing._apply_vlm_review_upgrade(
        Path("/tmp/heavy.pdf"),
        {
            "route": "heavy",
            "use_ocr": True,
            "reason": "heavy-any-image-page",
            "total_pages": 6,
        },
        sampled_indexes=[0, 1],
    )

    assert result["route"] == "heavy"
    assert result["use_ocr"] is True
    assert result["vlm_review"] == "skipped-non-normal"


def test_run_vlm_startup_checks_warns_when_model_missing(monkeypatch) -> None:
    monkeypatch.setattr(indexing, "UPLOAD_PDF_VLM_STARTUP_CHECK", True)
    monkeypatch.setattr(indexing, "UPLOAD_PDF_VLM_STARTUP_STRICT", False)
    monkeypatch.setattr(indexing, "UPLOAD_PDF_VLM_REVIEW_ENABLED", True)
    monkeypatch.setattr(indexing, "UPLOAD_PDF_VLM_EXTRACT_ENABLED", False)
    monkeypatch.setattr(indexing, "UPLOAD_PDF_VLM_REVIEW_MODEL", "qwen2.5vl:7b")
    monkeypatch.setattr(indexing, "UPLOAD_PDF_VLM_EXTRACT_MODEL", "qwen2.5vl:7b")
    monkeypatch.setattr(indexing.OllamaService, "list_models", lambda self: [])
    warnings: list[str] = []
    monkeypatch.setattr(indexing.logger, "info", lambda msg: warnings.append(str(msg)))

    notices = indexing._run_vlm_startup_checks()

    assert notices
    assert "required model(s) not available" in notices[0]
    assert warnings
