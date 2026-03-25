from pathlib import Path

from maia.loaders.txt_loader import TxtReader


def test_txt_reader_splits_heavy_pdf_ocr_page_blocks(tmp_path: Path) -> None:
    sample = tmp_path / "ocr.txt"
    sample.write_text(
        "# Page 1\nFirst page text.\n\n# Page 2\nSecond page text.\n",
        encoding="utf-8",
    )

    docs = TxtReader().load_data(
        sample,
        extra_info={
            "ingestion_route": "heavy-pdf-paddleocr",
            "source_original_name": "sample.pdf",
        },
    )

    assert len(docs) == 2
    assert docs[0].metadata["page_label"] == "1"
    assert docs[0].text == "First page text."
    assert docs[1].metadata["page_label"] == "2"
    assert docs[1].text == "Second page text."


def test_txt_reader_splits_layout_result_blocks_for_heavy_pdf_route(tmp_path: Path) -> None:
    sample = tmp_path / "ocr.txt"
    sample.write_text(
        "# Layout Result 1\nAlpha\n\n# Layout Result 2\nBeta\n",
        encoding="utf-8",
    )

    docs = TxtReader().load_data(
        sample,
        extra_info={
            "ingestion_route": "heavy-pdf-paddleocr",
            "source_original_name": "sample.pdf",
        },
    )

    assert len(docs) == 2
    assert docs[0].metadata["page_label"] == "1"
    assert docs[1].metadata["page_label"] == "2"


def test_txt_reader_keeps_regular_text_files_as_single_document(tmp_path: Path) -> None:
    sample = tmp_path / "notes.txt"
    sample.write_text("# Page 1\nThis is just normal text.\n", encoding="utf-8")

    docs = TxtReader().load_data(sample, extra_info={"source_original_name": "notes.txt"})

    assert len(docs) == 1
    assert docs[0].text == "# Page 1\nThis is just normal text.\n"
