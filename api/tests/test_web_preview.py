from __future__ import annotations

import re

from fastapi import HTTPException

from api.routers import web_preview


def test_normalize_target_url_rejects_artifact_path() -> None:
    assert web_preview._normalize_target_url("https://axongroup.com/Extract") == ""
    assert web_preview._normalize_target_url("https://axongroup.com/url") == ""


def test_normalize_target_url_rejects_localhost() -> None:
    assert web_preview._normalize_target_url("http://localhost:8000") == ""
    assert web_preview._normalize_target_url("http://127.0.0.1:8000") == ""


def test_sanitize_and_inject_preview_html_rewrites_links_and_highlight_script() -> None:
    rendered = web_preview._sanitize_and_inject_preview_html(
        html_text=(
            "<html><head><script>bad()</script></head>"
            "<body><a href='/about'>About</a><p>Industrial solutions square</p></body></html>"
        ),
        source_url="https://axongroup.com/",
        highlight_phrases=["Industrial solutions square"],
    )
    assert "<script>bad()</script>" not in rendered
    assert "/api/web/preview?url=https%3A%2F%2Faxongroup.com%2Fabout" in rendered
    assert "mark.maia-citation-highlight" in rendered
    assert "maia-citation-region" in rendered
    assert "Industrial solutions square" in rendered


def test_sanitize_and_inject_preview_html_reveals_cloaked_media_in_static_mode() -> None:
    rendered = web_preview._sanitize_and_inject_preview_html(
        html_text=(
            "<html><head><style>[x-cloak]{display:none!important}.opacity-0{opacity:0}</style></head>"
            "<body><section x-cloak class='js-content opacity-0'>"
            "<img class='js-image' src='https://axongroup.com/image.jpg'/>"
            "</section><div x-cloak class='bg-transparent fixed'>menu overlay</div></body></html>"
        ),
        source_url="https://axongroup.com/",
        highlight_phrases=[],
    )
    assert "x-cloak class='js-content" not in rendered
    assert "x-cloak class='bg-transparent fixed'" in rendered
    assert ".opacity-0{opacity:1 !important;}" in rendered
    assert "img.js-image,img[class*='js-image'],picture img{" in rendered


def test_sanitize_and_inject_preview_html_forces_desktop_viewport_by_default() -> None:
    rendered = web_preview._sanitize_and_inject_preview_html(
        html_text=(
            "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'></head>"
            "<body><p>Axon Group</p></body></html>"
        ),
        source_url="https://axongroup.com/",
        highlight_phrases=[],
    )
    assert "name='viewport' content='width=1280,initial-scale=1'" in rendered
    assert len(re.findall(r"name=['\"]viewport['\"]", rendered, flags=re.IGNORECASE)) == 1


def test_website_preview_supports_mobile_viewport_query(monkeypatch) -> None:
    monkeypatch.setattr(
        web_preview,
        "_fetch_html",
        lambda _url: ("<html><head></head><body><p>Preview body</p></body></html>", "https://axongroup.com/"),
    )
    response = web_preview.website_preview(url="https://axongroup.com/", viewport="mobile")
    body = response.body.decode("utf-8", errors="ignore")
    assert response.status_code == 200
    assert "name='viewport' content='width=device-width,initial-scale=1'" in body


def test_heuristic_highlight_scope_adapts_to_question_intent() -> None:
    assert (
        web_preview._heuristic_highlight_scope(
            question="https://axongroup.com/ what is this company doing?",
            highlight="Industrial solutions square",
            claim="The company provides industrial solutions.",
        )
        == "sentence"
    )
    assert (
        web_preview._heuristic_highlight_scope(
            question="What is the exact quote proving this claim?",
            highlight="industrial solutions",
            claim="",
        )
        == "tight"
    )


def test_resolve_highlight_scope_uses_heuristic_when_llm_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MAIA_WEB_PREVIEW_HIGHLIGHT_SCOPE_LLM_ENABLED", "0")
    resolved = web_preview._resolve_highlight_scope(
        question="Give me a concise summary of this page",
        highlight="Industrial solutions square",
        claim="The page describes grouped domain offerings.",
    )
    assert resolved in {"sentence", "context", "block", "tight"}
    assert resolved == "sentence"


def test_preview_fetch_error_html_google_workspace_auth_failure() -> None:
    rendered = web_preview._preview_fetch_error_html(
        source_url="https://docs.google.com/spreadsheets/d/abc123/edit",
        detail="Website fetch failed: HTTP Error 401: Unauthorized",
    )
    assert "Preview requires Google sign-in" in rendered
    assert "Use Open to view it in your signed-in browser." in rendered


def test_website_preview_returns_html_fallback_when_fetch_fails(monkeypatch) -> None:
    monkeypatch.setattr(
        web_preview,
        "_fetch_html",
        lambda _url: (_ for _ in ()).throw(
            HTTPException(status_code=502, detail="Website fetch failed: HTTP Error 401: Unauthorized")
        ),
    )
    response = web_preview.website_preview(url="https://docs.google.com/document/d/test/edit")
    body = response.body.decode("utf-8", errors="ignore")
    assert response.status_code == 200
    assert "Preview requires Google sign-in" in body
