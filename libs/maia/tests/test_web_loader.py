from unittest.mock import patch

from maia.base import Document
from maia.loaders.web_loader import WebReader


class MockResponse:
    def __init__(
        self,
        text: str,
        status_code: int = 200,
        headers: dict | None = None,
        content: bytes | None = None,
    ):
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content if content is not None else text.encode("utf-8")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@patch("maia.loaders.web_loader.requests.get")
def test_web_reader_crawls_deeper_urls_same_domain(mock_get):
    calls: list[str] = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        responses = {
            "https://r.jina.ai/https://example.com": MockResponse("root page"),
            "https://example.com": MockResponse(
                "<html><body>"
                "<a href='/about'>About</a>"
                "<a href='https://external.com/skip'>External</a>"
                "</body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
            ),
            "https://r.jina.ai/https://example.com/about": MockResponse("about page"),
            "https://example.com/about": MockResponse(
                "<html><body><a href='/team'>Team</a></body></html>",
                headers={"content-type": "text/html"},
            ),
            "https://r.jina.ai/https://example.com/team": MockResponse("team page"),
            "https://example.com/team": MockResponse(
                "<html><body>No more links</body></html>",
                headers={"content-type": "text/html"},
            ),
        }
        if url not in responses:
            raise AssertionError(f"Unexpected URL called: {url}")
        return responses[url]

    mock_get.side_effect = fake_get

    reader = WebReader(max_depth=2, max_pages=10, same_domain_only=True)
    docs = reader.load_data(
        "https://example.com", extra_info={"file_name": "https://example.com"}
    )

    assert len(docs) == 3
    assert [doc.metadata["page_url"] for doc in docs] == [
        "https://example.com",
        "https://example.com/about",
        "https://example.com/team",
    ]
    assert [doc.metadata["crawl_depth"] for doc in docs] == [0, 1, 2]
    assert docs[1].metadata["parent_url"] == "https://example.com"
    assert docs[2].metadata["parent_url"] == "https://example.com/about"
    assert all("external.com" not in url for url in calls)


@patch("maia.loaders.web_loader.requests.get")
def test_web_reader_respects_max_pages_limit(mock_get):
    calls: list[str] = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        responses = {
            "https://r.jina.ai/https://example.com": MockResponse("root page"),
            "https://example.com": MockResponse(
                "<html><body>"
                "<a href='/a'>A</a>"
                "<a href='/b'>B</a>"
                "<a href='/c'>C</a>"
                "</body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
            ),
            "https://r.jina.ai/https://example.com/a": MockResponse("page a"),
        }
        if url not in responses:
            raise AssertionError(f"Unexpected URL called: {url}")
        return responses[url]

    mock_get.side_effect = fake_get

    reader = WebReader(max_depth=2, max_pages=2, same_domain_only=True)
    docs = reader.load_data("https://example.com")

    assert len(docs) == 2
    assert [doc.metadata["page_url"] for doc in docs] == [
        "https://example.com",
        "https://example.com/a",
    ]
    assert "https://r.jina.ai/https://example.com/b" not in calls
    assert "https://r.jina.ai/https://example.com/c" not in calls


@patch("maia.loaders.web_loader.requests.get")
def test_web_reader_zero_limits_mean_unlimited(mock_get):
    def fake_get(url, headers=None, timeout=None):
        responses = {
            "https://r.jina.ai/https://example.com": MockResponse("root page"),
            "https://example.com": MockResponse(
                "<html><body><a href='/a'>A</a></body></html>",
                headers={"content-type": "text/html"},
            ),
            "https://r.jina.ai/https://example.com/a": MockResponse("page a"),
            "https://example.com/a": MockResponse(
                "<html><body><a href='/b'>B</a></body></html>",
                headers={"content-type": "text/html"},
            ),
            "https://r.jina.ai/https://example.com/b": MockResponse("page b"),
            "https://example.com/b": MockResponse(
                "<html><body>No more links</body></html>",
                headers={"content-type": "text/html"},
            ),
        }
        if url not in responses:
            raise AssertionError(f"Unexpected URL called: {url}")
        return responses[url]

    mock_get.side_effect = fake_get

    reader = WebReader(max_depth=0, max_pages=0, same_domain_only=True)
    docs = reader.load_data("https://example.com")

    assert len(docs) == 3
    assert [doc.metadata["crawl_depth"] for doc in docs] == [0, 1, 2]


@patch("maia.loaders.web_loader.WebReader.extract_pdf_documents")
@patch("maia.loaders.web_loader.requests.get")
def test_web_reader_extracts_linked_pdf_and_images(mock_get, mock_extract_pdf):
    calls: list[str] = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        responses = {
            "https://r.jina.ai/https://example.com": MockResponse("root page"),
            "https://example.com": MockResponse(
                "<html><body>"
                "<a href='/files/report.pdf'>Report</a>"
                "<a href='/images/chart.png'>Chart</a>"
                "</body></html>",
                headers={"content-type": "text/html; charset=utf-8"},
            ),
            "https://example.com/files/report.pdf": MockResponse(
                "",
                headers={"content-type": "application/pdf"},
                content=b"%PDF-1.4\nfake",
            ),
            "https://example.com/images/chart.png": MockResponse(
                "",
                headers={"content-type": "image/png"},
                content=b"\x89PNG\r\n\x1a\nfake",
            ),
            "https://r.jina.ai/https://example.com/images/chart.png": MockResponse(
                "chart image text"
            ),
        }
        if url not in responses:
            raise AssertionError(f"Unexpected URL called: {url}")
        return responses[url]

    mock_get.side_effect = fake_get

    mock_extract_pdf.side_effect = (
        lambda pdf_bytes, metadata, timeout: [Document(text="pdf text", metadata=metadata)]
    )

    reader = WebReader(max_depth=2, max_pages=0, same_domain_only=True)
    docs = reader.load_data("https://example.com")

    assert len(docs) == 3
    assert any(doc.text == "pdf text" for doc in docs)
    image_docs = [doc for doc in docs if doc.metadata.get("type") == "image"]
    assert len(image_docs) == 1
    assert image_docs[0].text == "chart image text"
    assert image_docs[0].metadata["image_origin"].startswith("data:image/png;base64,")
    assert "https://example.com/files/report.pdf" in calls
    assert "https://example.com/images/chart.png" in calls
