from pathlib import Path

from maia.indices.ingests import DocumentIngestor
from maia.indices.splitters import TokenSplitter


def test_ingestor_include_src():
    dirpath = Path(__file__).parent
    ingestor = DocumentIngestor(
        pdf_mode="normal",
        text_splitter=TokenSplitter(chunk_size=200, chunk_overlap=10),
    )
    nodes = ingestor(dirpath / "resources" / "table.pdf")
    assert type(nodes) is list
    assert nodes[0].relationships
