from __future__ import annotations

from typing import Any

from api.services.google.docs import GoogleDocsService


class _FakeSession:
    def __init__(self) -> None:
        self.user_id = "user_1"
        self.run_id = "run_1"
        self.calls: list[dict[str, Any]] = []

    def request_json(
        self,
        *,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int = 30,
        retry_on_unauthorized: bool = True,
    ) -> dict[str, Any]:
        _ = (headers, timeout, retry_on_unauthorized)
        call = {
            "method": method,
            "url": url,
            "params": params or {},
            "payload": payload or {},
        }
        self.calls.append(call)
        if method == "GET" and "/documents/" in url:
            return {"body": {"content": [{"endIndex": 2}]}}
        if method == "POST" and url.endswith(":batchUpdate"):
            return {"ok": True}
        raise AssertionError(f"Unexpected request: {call}")


def test_insert_markdown_builds_heading_list_and_link_requests() -> None:
    session = _FakeSession()
    service = GoogleDocsService(session=session)  # type: ignore[arg-type]

    result = service.insert_markdown(
        doc_id="doc-1",
        markdown_text=(
            "## Machine Learning Report\n"
            "- Practical application in forecasting\n"
            "1. Define metrics\n"
            "Reference: [OpenAI](https://openai.com)\n"
        ),
    )

    assert result["ok"] is True
    assert int(result["inserted_chars"]) > 0
    batch_calls = [call for call in session.calls if call["method"] == "POST"]
    assert len(batch_calls) == 1
    requests = batch_calls[0]["payload"].get("requests") or []
    assert isinstance(requests, list) and requests

    insert_request = requests[0].get("insertText") if isinstance(requests[0], dict) else None
    assert isinstance(insert_request, dict)
    inserted_text = str(insert_request.get("text") or "")
    assert "Machine Learning Report" in inserted_text
    assert "## " not in inserted_text
    assert "- Practical" not in inserted_text

    assert any("updateParagraphStyle" in req for req in requests if isinstance(req, dict))
    assert any("createParagraphBullets" in req for req in requests if isinstance(req, dict))
    assert any("updateTextStyle" in req for req in requests if isinstance(req, dict))

    link_requests = [req for req in requests if isinstance(req, dict) and "updateTextStyle" in req]
    assert link_requests
    first_link = link_requests[0]["updateTextStyle"]["textStyle"]["link"]["url"]
    assert first_link == "https://openai.com"
