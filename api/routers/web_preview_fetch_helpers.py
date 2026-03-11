from __future__ import annotations

import html
from time import monotonic
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from fastapi import HTTPException

_PREVIEW_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36 MaiaPreview/1.0"
)

_PLAYWRIGHT_AVAILABLE: bool | None = None  # None = not yet probed
_PLAYWRIGHT_TIMEOUT_MS = 8_000
_PLAYWRIGHT_SETTLE_MS = 1_200
_PLAYWRIGHT_NETWORKIDLE_GRACE_MS = 2_500

_SKELETON_MIN_HTML_BYTES = 5_000  # Ignore tiny pages — they're not skeletons
_SKELETON_TEXT_RATIO = 0.04  # < 4% visible text / raw HTML → JS-rendered skeleton


def fetch_html(
    url: str,
    *,
    preview_cache_ttl_seconds: float,
    preview_max_bytes: int,
    preview_timeout_seconds: int,
    preview_cache_lock: Any,
    preview_html_cache: dict[str, tuple[float, str, str]],
    preview_error_html_builder: Callable[..., str],
) -> tuple[str, str]:
    now = monotonic()
    with preview_cache_lock:
        cached = preview_html_cache.get(url)
        if cached and now < float(cached[0]):
            return cached[1], cached[2]

    request = Request(
        url,
        method="GET",
        headers={
            "User-Agent": _PREVIEW_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
            "Connection": "close",
        },
    )
    try:
        with urlopen(request, timeout=preview_timeout_seconds) as response:
            content_type = " ".join(str(response.headers.get("Content-Type", "")).split()).lower()
            if "html" not in content_type and "xhtml" not in content_type:
                return (
                    preview_error_html_builder(
                        title="Preview unavailable",
                        detail=(
                            "This source is not an HTML page. Use Open to view the original "
                            "resource in a new tab."
                        ),
                        source_url=str(response.geturl() or url),
                    ),
                    str(response.geturl() or url),
                )
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > preview_max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="Website preview payload is too large.",
                    )
                chunks.append(chunk)
            payload = b"".join(chunks)
            charset = str(response.headers.get_content_charset() or "").strip() or "utf-8"
            try:
                html_text = payload.decode(charset, errors="replace")
            except Exception:
                html_text = payload.decode("utf-8", errors="replace")
            final_url = str(response.geturl() or url)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Website fetch failed: {exc}") from exc

    with preview_cache_lock:
        preview_html_cache[url] = (now + preview_cache_ttl_seconds, html_text, final_url)
        if len(preview_html_cache) > 128:
            stale_keys = [
                key
                for key, (expiry, _html, _final_url) in preview_html_cache.items()
                if now >= float(expiry)
            ]
            for key in stale_keys:
                preview_html_cache.pop(key, None)
            overflow = len(preview_html_cache) - 128
            if overflow > 0:
                for key in list(preview_html_cache.keys())[:overflow]:
                    preview_html_cache.pop(key, None)
    return html_text, final_url


def playwright_available() -> bool:
    global _PLAYWRIGHT_AVAILABLE
    if _PLAYWRIGHT_AVAILABLE is None:
        try:
            import playwright.sync_api  # noqa: F401

            _PLAYWRIGHT_AVAILABLE = True
        except ImportError:
            _PLAYWRIGHT_AVAILABLE = False
    return bool(_PLAYWRIGHT_AVAILABLE)


def try_playwright_fetch(url: str) -> tuple[str, str] | None:
    """Render *url* with headless Chromium and return (html, final_url).

    Returns None if Playwright is not installed, the page fails, or times out.
    """
    if not playwright_available():
        return None
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                ctx = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 900},
                )
                page = ctx.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=_PLAYWRIGHT_TIMEOUT_MS)
                page.wait_for_timeout(_PLAYWRIGHT_SETTLE_MS)
                try:
                    page.wait_for_load_state("networkidle", timeout=_PLAYWRIGHT_NETWORKIDLE_GRACE_MS)
                except Exception:
                    pass
                return page.content(), page.url or url
            finally:
                browser.close()
    except Exception:
        return None


def is_skeleton_html(html_text: str) -> bool:
    """Return True when the page has almost no visible text (JS has not run yet)."""
    if len(html_text) < _SKELETON_MIN_HTML_BYTES:
        return False
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return False
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript", "head"]):
        tag.decompose()
    visible = soup.get_text(separator=" ", strip=True)
    return len(visible) / max(1, len(html_text)) < _SKELETON_TEXT_RATIO


def build_reader_page(*, html_text: str, source_url: str) -> str:
    """Extract article content and return a minimal reader-mode HTML page.

    Falls back to the original *html_text* when BeautifulSoup is not installed
    or no main content block can be found.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return html_text

    soup = BeautifulSoup(html_text, "html.parser")

    title_el = soup.find("title")
    page_title = (title_el.get_text(strip=True) if title_el else "")[:200]
    if not page_title:
        h1 = soup.find("h1")
        page_title = (h1.get_text(strip=True) if h1 else urlparse(source_url).netloc)[:200]

    content = (
        soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.find("main")
        or soup.find("body")
    )
    if not content:
        return html_text

    for junk in content(
        ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe", "svg"]
    ):
        junk.decompose()

    for img in content.find_all("img", src=True):
        src = str(img.get("src", ""))
        if src and not src.startswith(("http://", "https://", "data:", "//")):
            img["src"] = urljoin(source_url, src)

    content_html = str(content)
    esc_source = html.escape(source_url, quote=True)
    esc_title = html.escape(page_title, quote=True)
    display_host = html.escape(urlparse(source_url).netloc or source_url)

    return (
        "<!doctype html><html><head>"
        "<meta charset='utf-8'/>"
        f"<title>{esc_title}</title>"
        "<style>"
        "body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;"
        "background:#fff;color:#1d1d1f;line-height:1.65;font-size:16px;}"
        ".maia-reader-wrap{max-width:720px;margin:0 auto;padding:24px 20px 60px;}"
        ".maia-reader-banner{display:flex;align-items:center;gap:8px;padding:7px 12px;"
        "background:#f5f5f7;border-radius:8px;margin-bottom:20px;font-size:12px;color:#86868b;}"
        ".maia-reader-banner a{color:#0a60ff;text-decoration:none;flex:1;"
        "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}"
        ".maia-reader-badge{flex-shrink:0;background:#e5e5ea;border-radius:4px;"
        "padding:2px 6px;font-size:10px;font-weight:600;letter-spacing:.02em;color:#636366;}"
        "h1,h2,h3,h4,h5,h6{line-height:1.3;margin:1.4em 0 .5em;color:#1d1d1f;}"
        "h1{font-size:1.75em;}h2{font-size:1.4em;}h3{font-size:1.2em;}"
        "p{margin:.75em 0;}ul,ol{padding-left:1.5em;margin:.75em 0;}"
        "li{margin:.25em 0;}"
        "img{max-width:100%;height:auto;border-radius:8px;margin:.5em 0;}"
        "a{color:#0a60ff;text-decoration:none;}a:hover{text-decoration:underline;}"
        "blockquote{border-left:3px solid #d2d2d7;margin:1em 0;padding:.5em 1em;"
        "color:#555;font-style:italic;}"
        "pre{background:#f5f5f7;border-radius:6px;padding:1em;overflow:auto;font-size:.875em;}"
        "code{background:#f5f5f7;border-radius:3px;padding:.1em .3em;font-size:.9em;}"
        "pre code{background:transparent;padding:0;}"
        "table{border-collapse:collapse;width:100%;margin:1em 0;font-size:.9em;}"
        "th,td{border:1px solid #d2d2d7;padding:.5em .75em;text-align:left;}"
        "th{background:#f5f5f7;font-weight:600;}"
        "figure{margin:1em 0;}figcaption{font-size:.875em;color:#86868b;margin-top:.3em;}"
        "</style>"
        "</head><body>"
        "<div class='maia-reader-wrap'>"
        "<div class='maia-reader-banner'>"
        "<span class='maia-reader-badge'>Reader view</span>"
        f"<a href='{esc_source}' target='_blank' rel='noopener noreferrer'>{display_host}</a>"
        "</div>"
        f"{content_html}"
        "</div>"
        "</body></html>"
    )
