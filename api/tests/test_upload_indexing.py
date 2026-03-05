from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
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
        lambda _path: {"route": "heavy", "use_ocr": True, "reason": "heavy-image-ratio"},
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


def test_index_files_falls_back_to_current_parser_when_paddle_fails(monkeypatch) -> None:
    pipeline = _DummyPipeline()
    index = _DummyIndex(index_id=13, pipeline=pipeline)

    parser_calls: list[dict] = []

    monkeypatch.setattr(indexing, "get_index", lambda context, index_id: index)
    monkeypatch.setattr(
        indexing,
        "_classify_pdf_ingestion_route",
        lambda _path: {"route": "heavy", "use_ocr": True, "reason": "heavy-low-text-ratio"},
    )
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_ENABLED", True)

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


def test_run_upload_startup_checks_warns_when_dependencies_missing(monkeypatch) -> None:
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_STARTUP_CHECK", True)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_STARTUP_STRICT", False)
    monkeypatch.setattr(indexing, "UPLOAD_INDEX_READER_MODE", "default")
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_ENABLED", True)
    monkeypatch.setattr(indexing, "UPLOAD_PADDLEOCR_STARTUP_WARMUP", False)

    imported_modules: list[str] = []
    real_import = __import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        imported_modules.append(str(name))
        if name in {"fitz", "paddleocr"}:
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    warnings: list[str] = []
    monkeypatch.setattr("builtins.__import__", _fake_import)
    monkeypatch.setattr(indexing.logger, "warning", lambda msg: warnings.append(str(msg)))

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
    monkeypatch.setattr(indexing.logger, "warning", lambda msg: warnings.append(str(msg)))

    notices = indexing._run_vlm_startup_checks()

    assert notices
    assert "required model(s) not available" in notices[0]
    assert warnings
