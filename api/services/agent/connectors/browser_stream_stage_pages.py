from __future__ import annotations

import re
from typing import Any, Callable, Generator
from urllib.parse import quote


def run_browser_pages_stage(
    *,
    page: Any,
    browser_context: Any,
    browser: Any,
    current_url: str,
    final_cursor: dict[str, float],
    open_cursor: dict[str, float],
    follow_same_domain_links: bool,
    max_pages: int,
    max_scroll_steps: int,
    timeout_ms: int,
    wait_ms: int,
    auto_accept_cookies: bool,
    output_dir: Any,
    stamp_prefix: str,
    movement_rng: Any,
    visited_pages: list[dict[str, Any]],
    _quality_profile: Callable[..., dict[str, Any]],
    _safe_selector: Callable[[Any], str],
    _jitter_target: Callable[..., tuple[float, float]],
    _website_payload: Callable[[dict[str, Any] | None], dict[str, Any]],
    _emit_extract_side_events: Callable[..., Generator[dict[str, Any], None, None]],
    _elapsed_ms: Callable[[], int],
    extract_same_origin_links: Callable[..., list[str]],
    accept_cookie_banner: Callable[..., dict[str, Any]],
    safe_focus_point: Callable[..., tuple[float, float]],
    smart_scroll_delta: Callable[..., float],
    move_cursor: Callable[..., dict[str, float]],
    capture_page_state: Callable[..., dict[str, str]],
    page_metrics: Callable[..., dict[str, float]],
    runtime: Any,
):
        def _goto_with_download_fallback(target_url: str) -> bool:
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(max(200, wait_ms))
                return True
            except Exception as exc:
                message = str(exc or "").lower()
                looks_like_pdf_download = (
                    "download is starting" in message
                    or "navigation is interrupted by download" in message
                    or ("net::err_aborted" in message and ".pdf" in str(target_url).lower())
                    or str(target_url or "").lower().endswith(".pdf")
                )
                if not looks_like_pdf_download:
                    return False
                viewer_url = (
                    "https://docs.google.com/gview?embedded=1&url="
                    f"{quote(str(target_url or ''), safe=':/?&=%#')}"
                )
                try:
                    page.goto(viewer_url, wait_until="domcontentloaded", timeout=timeout_ms)
                    page.wait_for_timeout(max(200, wait_ms))
                    return True
                except Exception:
                    return False

        # Always include the initial page as page 1. Additional same-origin
        # targets are appended when follow-up navigation is enabled.
        targets: list[str] = [str(current_url or "").strip() or "about:blank"]

        if follow_same_domain_links:
            targets.extend(
                extract_same_origin_links(
                    page=page,
                    origin_url=current_url,
                    limit=max(0, int(max_pages) - 1),
                )
            )

        for page_index, target_url in enumerate(targets, start=1):
            last_cursor = dict(open_cursor)
            final_cursor = dict(last_cursor)
            link_click_emitted = False
            if page_index > 1:
                target_path = ""
                target_match = re.match(r"^https?://[^/]+(?P<path>/[^?#]*)?", str(target_url or ""))
                if target_match:
                    target_path = str(target_match.group("path") or "").strip()
                target_url_selector = str(target_url or "").replace("'", "\\'")
                selector_candidates = [
                    _safe_selector(f"a[href='{target_url_selector}']"),
                ]
                if target_path and target_path not in {"/", ""}:
                    target_path_selector = target_path.replace("'", "\\'")
                    selector_candidates.append(
                        _safe_selector(f"a[href*='{target_path_selector}']")
                    )
                for selector in selector_candidates:
                    if not selector:
                        continue
                    try:
                        locator = page.locator(selector).first
                        locator.wait_for(timeout=min(timeout_ms, 2600), state="visible")
                        click_cursor: dict[str, float] = {}
                        try:
                            box = locator.bounding_box()
                        except Exception:
                            box = None
                        if isinstance(box, dict):
                            center_x = float(box.get("x", 0.0)) + (float(box.get("width", 0.0)) / 2.0)
                            center_y = float(box.get("y", 0.0)) + min(14.0, float(box.get("height", 0.0)) / 2.0)
                            center_x, center_y = _jitter_target(center_x, center_y, spread=14.0)
                            click_cursor = move_cursor(page=page, x=center_x, y=center_y)
                        if not click_cursor:
                            fallback_x, fallback_y = _jitter_target(188.0, 142.0, spread=20.0)
                            click_cursor = move_cursor(page=page, x=fallback_x, y=fallback_y)
                        click_capture = capture_page_state(
                            page=page,
                            output_dir=output_dir,
                            stamp_prefix=stamp_prefix,
                            label=f"same-domain-link-{page_index}",
                        )
                        yield {
                            "event_type": "browser_hover",
                            "title": f"Hover same-domain link {page_index}",
                            "detail": selector,
                            "data": _website_payload(
                                {
                                    "url": click_capture["url"],
                                    "title": click_capture["title"],
                                    "page_index": page_index - 1,
                                    "selector": selector,
                                    "target_url": target_url,
                                    "extract_stage": "same_domain_followup",
                                    "elapsed_ms": _elapsed_ms(),
                                    **click_cursor,
                                    **page_metrics(page=page),
                                }
                            ),
                            "snapshot_ref": click_capture["screenshot_path"],
                        }
                        yield {
                            "event_type": "browser_click",
                            "title": f"Open same-domain link {page_index}",
                            "detail": target_url,
                            "data": _website_payload(
                                {
                                    "url": click_capture["url"],
                                    "title": click_capture["title"],
                                    "page_index": page_index - 1,
                                    "selector": selector,
                                    "target_url": target_url,
                                    "extract_stage": "same_domain_followup",
                                    "elapsed_ms": _elapsed_ms(),
                                    **click_cursor,
                                    **page_metrics(page=page),
                                }
                            ),
                            "snapshot_ref": click_capture["screenshot_path"],
                        }
                        link_click_emitted = True
                        last_cursor = dict(click_cursor)
                        final_cursor = dict(click_cursor)
                        break
                    except Exception:
                        continue
                if not link_click_emitted:
                    fallback_x, fallback_y = _jitter_target(186.0, 142.0, spread=20.0)
                    fallback_cursor = move_cursor(page=page, x=fallback_x, y=fallback_y)
                    last_cursor = dict(fallback_cursor)
                    final_cursor = dict(fallback_cursor)
                    try:
                        page.mouse.click(
                            fallback_x,
                            fallback_y,
                            delay=movement_rng.randint(34, 96),
                        )
                    except Exception:
                        pass
                    fallback_capture = capture_page_state(
                        page=page,
                        output_dir=output_dir,
                        stamp_prefix=stamp_prefix,
                        label=f"same-domain-fallback-{page_index}",
                    )
                    yield {
                        "event_type": "browser_click",
                        "title": f"Open same-domain link {page_index}",
                        "detail": target_url,
                        "data": _website_payload(
                            {
                                "url": fallback_capture["url"],
                                "title": fallback_capture["title"],
                                "page_index": page_index - 1,
                                "selector": "same-domain-fallback",
                                "target_url": target_url,
                                "extract_stage": "same_domain_followup",
                                "elapsed_ms": _elapsed_ms(),
                                **fallback_cursor,
                                **page_metrics(page=page),
                            }
                        ),
                        "snapshot_ref": fallback_capture["screenshot_path"],
                    }
                if not _goto_with_download_fallback(target_url):
                    continue
                nav_x, nav_y = _jitter_target(138, 106, spread=16.0)
                last_cursor = move_cursor(page=page, x=nav_x, y=nav_y)
                final_cursor = dict(last_cursor)
                nav_capture = capture_page_state(
                    page=page,
                    output_dir=output_dir,
                    stamp_prefix=stamp_prefix,
                    label=f"nav-{page_index}",
                )
                nav_metrics = page_metrics(page=page)
                yield {
                    "event_type": "browser_navigate",
                    "title": f"Navigate to page {page_index}",
                    "detail": nav_capture["url"],
                    "data": _website_payload(
                        {
                            "url": nav_capture["url"],
                            "title": nav_capture["title"],
                            "page_index": page_index,
                            "extract_stage": "same_domain_followup",
                            "elapsed_ms": _elapsed_ms(),
                            **last_cursor,
                            **nav_metrics,
                        }
                    ),
                    "snapshot_ref": nav_capture["screenshot_path"],
                }
                if auto_accept_cookies:
                    consent = accept_cookie_banner(page=page, wait_ms=wait_ms)
                    consent_capture = capture_page_state(
                        page=page,
                        output_dir=output_dir,
                        stamp_prefix=stamp_prefix,
                        label=f"cookie-accept-{page_index}",
                    )
                    consent_cursor = {
                        key: float(consent.get(key))
                        for key in ("cursor_x", "cursor_y")
                        if isinstance(consent.get(key), (int, float))
                    }
                    if consent.get("accepted"):
                        yield {
                            "event_type": "browser_cookie_accept",
                            "title": f"Accept website cookies (page {page_index})",
                            "detail": str(consent.get("label") or "Accepted cookie consent banner"),
                            "data": _website_payload(
                                {
                                    "url": consent_capture["url"],
                                    "title": consent_capture["title"],
                                    "page_index": page_index,
                                    **last_cursor,
                                    **consent_cursor,
                                }
                            ),
                            "snapshot_ref": consent_capture["screenshot_path"],
                        }
                    else:
                        yield {
                            "event_type": "browser_cookie_check",
                            "title": f"Check website cookies (page {page_index})",
                            "detail": "No cookie banner detected or consent already stored.",
                            "data": _website_payload(
                                {
                                    "url": consent_capture["url"],
                                    "title": consent_capture["title"],
                                    "page_index": page_index,
                                    **last_cursor,
                                }
                            ),
                            "snapshot_ref": consent_capture["screenshot_path"],
                        }

            for scroll_index in range(max(1, int(max_scroll_steps))):
                metrics_before = page_metrics(page=page)
                viewport_width = int(metrics_before.get("viewport_width") or 1366)
                viewport_height = int(metrics_before.get("viewport_height") or 768)
                cursor_x_px, cursor_y_px = safe_focus_point(
                    page=page,
                    pass_index=scroll_index + page_index,
                    viewport_width=float(viewport_width),
                    viewport_height=float(viewport_height),
                )
                cursor_x_px, cursor_y_px = _jitter_target(cursor_x_px, cursor_y_px, spread=24.0)
                last_cursor = move_cursor(page=page, x=cursor_x_px, y=cursor_y_px)
                final_cursor = dict(last_cursor)
                scroll_delta = smart_scroll_delta(
                    metrics_before=metrics_before,
                    pass_index=scroll_index,
                    total_passes=max(1, int(max_scroll_steps)),
                )
                if abs(scroll_delta) >= 1:
                    scroll_delta *= movement_rng.uniform(0.83, 1.19)
                    max_delta = max(320.0, float(viewport_height) * 1.14)
                    scroll_delta = max(-max_delta, min(max_delta, scroll_delta))
                if abs(scroll_delta) < 1:
                    if scroll_index == 0:
                        scroll_delta = max(140.0, float(viewport_height) * 0.36)
                    elif scroll_index == 1:
                        scroll_delta = -max(120.0, float(viewport_height) * 0.28)
                    else:
                        continue
                page.mouse.wheel(0, scroll_delta)
                pause_ms = max(180, wait_ms // 2) + movement_rng.randint(0, 220)
                page.wait_for_timeout(pause_ms)
                metrics_after = page_metrics(page=page)
                scroll_capture = capture_page_state(
                    page=page,
                    output_dir=output_dir,
                    stamp_prefix=stamp_prefix,
                    label=f"scroll-{page_index}-{scroll_index + 1}",
                )
                yield {
                    "event_type": "browser_scroll",
                    "title": f"Scroll page {page_index}",
                    "detail": f"Viewport pass {scroll_index + 1} ({'down' if scroll_delta >= 0 else 'up'})",
                    "data": _website_payload(
                        {
                            "url": scroll_capture["url"],
                            "title": scroll_capture["title"],
                            "page_index": page_index,
                            "scroll_pass": scroll_index + 1,
                            "scroll_delta": round(float(scroll_delta), 2),
                            "scroll_direction": "down" if scroll_delta >= 0 else "up",
                            "extract_stage": "lazy_load_scroll",
                            "elapsed_ms": _elapsed_ms(),
                            **last_cursor,
                            **metrics_after,
                        }
                    ),
                    "snapshot_ref": scroll_capture["screenshot_path"],
                }

            extract_capture = capture_page_state(
                page=page,
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
                label=f"extract-{page_index}",
            )
            visited_pages.append(
                {
                    "url": extract_capture["url"],
                    "title": extract_capture["title"],
                    "text_excerpt": extract_capture["text_excerpt"],
                    "screenshot_path": extract_capture["screenshot_path"],
                    **_quality_profile(text_excerpt=str(extract_capture["text_excerpt"] or "")),
                }
            )
            extract_quality = _quality_profile(text_excerpt=str(extract_capture["text_excerpt"] or ""))
            yield {
                "event_type": "browser_extract",
                "title": f"Extract web evidence (page {page_index})",
                "detail": extract_capture["title"] or extract_capture["url"],
                "data": _website_payload(
                    {
                        "url": extract_capture["url"],
                        "title": extract_capture["title"],
                        "page_index": page_index,
                        "characters": len(str(extract_capture["text_excerpt"] or "")),
                        "text_excerpt": str(extract_capture["text_excerpt"] or "")[:1200],
                        "extract_stage": "post_scroll_capture",
                        "render_quality": extract_quality["render_quality"],
                        "content_density": extract_quality["content_density"],
                        "blocked_signal": extract_quality["blocked_signal"],
                        "blocked_reason": extract_quality["blocked_reason"],
                        "elapsed_ms": _elapsed_ms(),
                        **last_cursor,
                        **page_metrics(page=page),
                    }
                ),
                "snapshot_ref": extract_capture["screenshot_path"],
            }
            for side_event in _emit_extract_side_events(
                capture=extract_capture,
                page_index=page_index,
                cursor_payload=last_cursor,
            ):
                yield runtime.normalize(side_event)

        browser_context.close()
        browser.close()

        return {
            "targets": targets,
            "final_cursor": final_cursor,
        }
