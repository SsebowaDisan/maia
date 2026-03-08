from __future__ import annotations

from typing import Any, Callable, Generator
from urllib.parse import quote

from .base import ConnectorError


def run_initial_browser_stage(
    *,
    page: Any,
    url: str,
    timeout_ms: int,
    wait_ms: int,
    auto_accept_cookies: bool,
    actions: list[dict[str, Any]],
    trusted_site: dict[str, Any],
    trusted_headers: dict[str, Any],
    trusted_cookies: list[dict[str, Any]],
    output_dir: Any,
    stamp_prefix: str,
    visited_pages: list[dict[str, Any]],
    open_capture: dict[str, Any],
    open_cursor: dict[str, float],
    movement_rng: Any,
    _quality_profile: Callable[..., dict[str, Any]],
    _safe_selector: Callable[[Any], str],
    _jitter_target: Callable[..., tuple[float, float]],
    _website_payload: Callable[[dict[str, Any] | None], dict[str, Any]],
    _emit_extract_side_events: Callable[..., Generator[dict[str, Any], None, None]],
    _elapsed_ms: Callable[[], int],
    runtime: Any,
    accept_cookie_banner: Callable[..., dict[str, Any]],
    move_cursor: Callable[..., dict[str, float]],
    capture_page_state: Callable[..., dict[str, str]],
    page_metrics: Callable[..., dict[str, float]],
    excerpt: Callable[..., str],
):
        def _goto_with_download_fallback(target_url: str) -> None:
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(max(200, wait_ms))
                return
            except Exception as exc:
                message = str(exc or "").lower()
                looks_like_pdf_download = (
                    "download is starting" in message
                    or "navigation is interrupted by download" in message
                    or ("net::err_aborted" in message and ".pdf" in str(target_url).lower())
                    or str(target_url or "").lower().endswith(".pdf")
                )
                if not looks_like_pdf_download:
                    raise
                viewer_url = (
                    "https://docs.google.com/gview?embedded=1&url="
                    f"{quote(str(target_url or ''), safe=':/?&=%#')}"
                )
                page.goto(viewer_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(max(200, wait_ms))

        try:
            _goto_with_download_fallback(url)
        except Exception as exc:
            raise ConnectorError(f"Failed to open URL: {url}. {exc}") from exc

        open_x, open_y = _jitter_target(124, 88, spread=14.0)
        open_cursor = move_cursor(page=page, x=open_x, y=open_y)
        open_capture = capture_page_state(
            page=page,
            output_dir=output_dir,
            stamp_prefix=stamp_prefix,
            label="open",
        )
        open_metrics = page_metrics(page=page)
        yield {
            "event_type": "browser_open",
            "title": "Start Playwright browser session",
            "detail": open_capture["url"],
            "data": _website_payload(
                {
                    "url": open_capture["url"],
                    "title": open_capture["title"],
                    "page_index": 1,
                    "elapsed_ms": _elapsed_ms(),
                    **open_cursor,
                    **open_metrics,
                }
            ),
            "snapshot_ref": open_capture["screenshot_path"],
        }
        if bool(trusted_site.get("trusted")):
            yield {
                "event_type": "browser_trusted_site_mode",
                "title": "Apply trusted-site browser policy",
                "detail": f"Trusted host: {str(trusted_site.get('host') or '')}",
                "data": _website_payload(
                    {
                        "trusted_host": str(trusted_site.get("host") or ""),
                        "trusted_header_count": len(trusted_headers),
                        "trusted_cookie_count": len(trusted_cookies),
                        **open_cursor,
                    }
                ),
                "snapshot_ref": open_capture["screenshot_path"],
            }

        if auto_accept_cookies:
            consent = accept_cookie_banner(page=page, wait_ms=wait_ms)
            consent_capture = capture_page_state(
                page=page,
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
                label="cookie-accept-1",
            )
            consent_cursor = {
                key: float(consent.get(key))
                for key in ("cursor_x", "cursor_y")
                if isinstance(consent.get(key), (int, float))
            }
            if consent.get("accepted"):
                yield {
                    "event_type": "browser_cookie_accept",
                    "title": "Accept website cookies",
                    "detail": str(consent.get("label") or "Accepted cookie consent banner"),
                    "data": _website_payload(
                        {
                            "url": consent_capture["url"],
                            "title": consent_capture["title"],
                            "page_index": 1,
                            **consent_cursor,
                        }
                    ),
                    "snapshot_ref": consent_capture["screenshot_path"],
                }
            else:
                yield {
                    "event_type": "browser_cookie_check",
                    "title": "Check website cookies",
                    "detail": "No cookie banner detected or consent already stored.",
                    "data": _website_payload(
                        {
                            "url": consent_capture["url"],
                            "title": consent_capture["title"],
                            "page_index": 1,
                        }
                    ),
                    "snapshot_ref": consent_capture["screenshot_path"],
                }

        # Always capture a fast first-pass extract before any scrolling/navigation so
        # the agent can ground an initial answer from the landing page immediately.
        quick_x, quick_y = _jitter_target(220, 192, spread=20.0)
        quick_cursor = move_cursor(page=page, x=quick_x, y=quick_y)
        quick_capture = capture_page_state(
            page=page,
            output_dir=output_dir,
            stamp_prefix=stamp_prefix,
            label="extract-initial-1",
        )
        visited_pages.append(
            {
                "url": quick_capture["url"],
                "title": quick_capture["title"],
                "text_excerpt": quick_capture["text_excerpt"],
                "screenshot_path": quick_capture["screenshot_path"],
                **_quality_profile(text_excerpt=str(quick_capture["text_excerpt"] or "")),
            }
        )
        quick_quality = _quality_profile(text_excerpt=str(quick_capture["text_excerpt"] or ""))
        yield {
            "event_type": "browser_extract",
            "title": "Fast landing-page analysis",
            "detail": quick_capture["title"] or quick_capture["url"],
            "data": _website_payload(
                {
                    "url": quick_capture["url"],
                    "title": quick_capture["title"],
                    "page_index": 1,
                    "extract_pass": "initial",
                    "extract_stage": "initial_render",
                    "characters": len(str(quick_capture["text_excerpt"] or "")),
                    "text_excerpt": str(quick_capture["text_excerpt"] or "")[:1200],
                    "render_quality": quick_quality["render_quality"],
                    "content_density": quick_quality["content_density"],
                    "blocked_signal": quick_quality["blocked_signal"],
                    "blocked_reason": quick_quality["blocked_reason"],
                    "elapsed_ms": _elapsed_ms(),
                    **quick_cursor,
                    **page_metrics(page=page),
                }
            ),
            "snapshot_ref": quick_capture["screenshot_path"],
        }
        for side_event in _emit_extract_side_events(
            capture=quick_capture,
            page_index=1,
            cursor_payload=quick_cursor,
        ):
            yield runtime.normalize(side_event)

        for action_index, action in enumerate(actions[:8], start=1):
            if not isinstance(action, dict):
                continue
            action_type = str(action.get("type") or "").strip().lower()
            selector = _safe_selector(action.get("selector"))
            value = str(action.get("value") or "").strip()
            if action_type not in {"click", "fill"} or not selector:
                yield {
                    "event_type": "browser_interaction_failed",
                    "title": f"Skip browser action {action_index}",
                    "detail": "Invalid action payload",
                    "data": _website_payload(
                        {
                            "action_index": action_index,
                            "action_type": action_type,
                            "selector": selector,
                            "elapsed_ms": _elapsed_ms(),
                        }
                    ),
                }
                continue
            try:
                locator = page.locator(selector).first
                locator.wait_for(timeout=min(timeout_ms, 7000), state="visible")
                interaction_cursor: dict[str, float] = {}
                try:
                    box = locator.bounding_box()
                except Exception:
                    box = None
                if isinstance(box, dict):
                    center_x = float(box.get("x", 0.0)) + (float(box.get("width", 0.0)) / 2.0)
                    center_y = float(box.get("y", 0.0)) + min(16.0, float(box.get("height", 0.0)) / 2.0)
                    center_x, center_y = _jitter_target(center_x, center_y, spread=12.0)
                    interaction_cursor = move_cursor(page=page, x=center_x, y=center_y)
                if not interaction_cursor:
                    fallback_x, fallback_y = _jitter_target(168.0, 142.0, spread=22.0)
                    interaction_cursor = move_cursor(page=page, x=fallback_x, y=fallback_y)
                interaction_start_capture = capture_page_state(
                    page=page,
                    output_dir=output_dir,
                    stamp_prefix=stamp_prefix,
                    label=f"interaction-start-{action_index}",
                )
                yield {
                    "event_type": "browser_hover",
                    "title": f"Hover browser action {action_index}",
                    "detail": f"{action_type} -> {selector}",
                    "data": _website_payload(
                        {
                            "action_index": action_index,
                            "action_type": action_type,
                            "selector": selector,
                            "elapsed_ms": _elapsed_ms(),
                            "url": interaction_start_capture["url"],
                            "title": interaction_start_capture["title"],
                            **interaction_cursor,
                            **page_metrics(page=page),
                        }
                    ),
                    "snapshot_ref": interaction_start_capture["screenshot_path"],
                }
                yield {
                    "event_type": "browser_interaction_started",
                    "title": f"Run browser action {action_index}",
                    "detail": f"{action_type} -> {selector}",
                    "data": _website_payload(
                        {
                            "action_index": action_index,
                            "action_type": action_type,
                            "selector": selector,
                            "elapsed_ms": _elapsed_ms(),
                            "url": interaction_start_capture["url"],
                            "title": interaction_start_capture["title"],
                            **interaction_cursor,
                            **page_metrics(page=page),
                        }
                    ),
                    "snapshot_ref": interaction_start_capture["screenshot_path"],
                }
                if action_type == "click":
                    locator.click(timeout=min(timeout_ms, 7000))
                else:
                    locator.fill(value, timeout=min(timeout_ms, 7000))
                page.wait_for_timeout(max(180, wait_ms // 2))
                interaction_capture = capture_page_state(
                    page=page,
                    output_dir=output_dir,
                    stamp_prefix=stamp_prefix,
                    label=f"interaction-{action_index}",
                )
                yield {
                    "event_type": "browser_interaction_completed",
                    "title": f"Completed browser action {action_index}",
                    "detail": f"{action_type} -> {selector}",
                    "data": _website_payload(
                        {
                            "action_index": action_index,
                            "action_type": action_type,
                            "selector": selector,
                            "value_preview": excerpt(value, limit=80) if action_type == "fill" else "",
                            "url": interaction_capture["url"],
                            "title": interaction_capture["title"],
                            "elapsed_ms": _elapsed_ms(),
                            **interaction_cursor,
                            **page_metrics(page=page),
                        }
                    ),
                    "snapshot_ref": interaction_capture["screenshot_path"],
                }
                if action_type == "click":
                    yield {
                        "event_type": "browser_click",
                        "title": f"Click page element {action_index}",
                        "detail": selector,
                        "data": _website_payload(
                            {
                                "action_index": action_index,
                                "selector": selector,
                                "url": interaction_capture["url"],
                                "title": interaction_capture["title"],
                                "elapsed_ms": _elapsed_ms(),
                                **interaction_cursor,
                                **page_metrics(page=page),
                            }
                        ),
                        "snapshot_ref": interaction_capture["screenshot_path"],
                    }
            except Exception as exc:
                yield {
                    "event_type": "browser_interaction_failed",
                    "title": f"Browser action {action_index} failed",
                    "detail": str(exc)[:180],
                    "data": _website_payload(
                        {
                            "action_index": action_index,
                            "action_type": action_type,
                            "selector": selector,
                            "elapsed_ms": _elapsed_ms(),
                        }
                    ),
                }

        current_url = str(open_capture["url"] or url)
        targets = [current_url]
        final_cursor: dict[str, float] = dict(open_cursor)
        return {
            "current_url": current_url,
            "final_cursor": final_cursor,
            # Return the captures so the caller can use them without needing
            # them defined in its own scope before the call.
            "open_capture": dict(open_capture),
            "open_cursor": dict(open_cursor),
        }
