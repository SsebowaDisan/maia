"""Computer Use browser connector compatibility layer."""
from __future__ import annotations
import logging
from typing import Any, Generator
from .base import BaseConnector, ConnectorError, ConnectorHealth
from .computer_use_browser_helpers import (
    build_browse_task,
    compact_text,
    cursor_payload,
    quality_profile,
    write_snapshot,
)
from .computer_use_highlight_planner import plan_llm_highlights
from .computer_use_contact_stream import stream_contact_form_live
logger = logging.getLogger(__name__)
_LOW_SIGNAL_TOKENS = ("unable to scroll", "cannot scroll", "can't scroll", "cannot interact", "unable to interact")
class ComputerUseBrowserConnector(BaseConnector):
    connector_id = "computer_use_browser"
    def health_check(self) -> ConnectorHealth:
        try:
            from api.services.computer_use.agent_loop import run_agent_loop  # noqa: F401
            from api.services.computer_use.session_registry import get_session_registry  # noqa: F401
            return ConnectorHealth(self.connector_id, True, "Computer Use available")
        except ImportError:
            return ConnectorHealth(self.connector_id, False, "Computer Use runtime is not available.")

    def execute_tool(self, tool_id: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool_id in {
            "browser.navigate",
            "browser.extract_text",
            "browser.get_meta_tags",
            "browser.get_headings",
            "browser.get_links",
        }:
            capture = self.browse_and_capture(
                url=str(params.get("url") or "").strip(),
                follow_same_domain_links=False,
            )
            return {
                "content": str(capture.get("text_excerpt") or ""),
                "url": str(capture.get("url") or ""),
                "method": "computer_use",
                "render_quality": str(capture.get("render_quality") or "unknown"),
                "content_density": float(capture.get("content_density") or 0.0),
            }
        if tool_id == "contact_form.fill":
            stream = self.submit_contact_form_live_stream(
                url=str(params.get("url") or "").strip(),
                sender_name=str(params.get("name") or "").strip(),
                sender_email=str(params.get("email") or "").strip(),
                subject=str(params.get("subject") or "Business Inquiry").strip(),
                message=str(params.get("message") or "").strip(),
                sender_company=str(params.get("company") or "").strip(),
                sender_phone=str(params.get("phone") or "").strip(),
                auto_accept_cookies=bool(params.get("auto_accept_cookies", True)),
            )
            while True:
                try:
                    next(stream)
                except StopIteration as stop:
                    return stop.value if isinstance(stop.value, dict) else {}
        return {"error": f"Unknown tool: {tool_id}"}

    def browse_and_capture(
        self,
        *,
        url: str,
        timeout_ms: int = 20000,
        wait_ms: int = 1200,
        auto_accept_cookies: bool = True,
        highlight_color: str = "yellow",
        highlight_query: str = "",
        follow_same_domain_links: bool = True,
        interaction_actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        stream = self.browse_live_stream(
            url=url,
            timeout_ms=timeout_ms,
            wait_ms=wait_ms,
            max_pages=1,
            max_scroll_steps=1,
            auto_accept_cookies=auto_accept_cookies,
            highlight_color=highlight_color,
            highlight_query=highlight_query,
            follow_same_domain_links=follow_same_domain_links,
            interaction_actions=interaction_actions,
        )
        while True:
            try:
                next(stream)
            except StopIteration as stop:
                return stop.value if isinstance(stop.value, dict) else {}

    def browse_live_stream(
        self,
        *,
        url: str,
        timeout_ms: int = 20000,
        wait_ms: int = 1200,
        max_pages: int = 3,
        max_scroll_steps: int = 3,
        auto_accept_cookies: bool = True,
        highlight_color: str = "yellow",
        highlight_query: str = "",
        follow_same_domain_links: bool = True,
        interaction_actions: list[dict[str, Any]] | None = None,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        del timeout_ms, wait_ms, auto_accept_cookies
        clean_url = str(url or "").strip()
        if not clean_url:
            raise ConnectorError("A valid URL is required for browser inspection.")
        effective_highlight_color = "green" if str(highlight_color).strip().lower() == "green" else "yellow"

        from api.services.computer_use.agent_loop import run_agent_loop
        from api.services.computer_use.session_registry import get_session_registry

        registry = get_session_registry()
        session = registry.create(user_id=self._connector_user_id(), start_url=clean_url)
        screenshot_path = ""
        text_rows: list[str] = []
        error_text = ""
        event_index = 0
        try:
            session.navigate(clean_url)
            screenshot_path = write_snapshot(
                screenshot_b64=session.screenshot_b64(),
                label="open",
            )
            yield {
                "event_type": "browser_open",
                "title": "Open target website",
                "detail": clean_url,
                "data": {
                    "url": session.current_url(),
                    "title": session.page_title(),
                    "scene_surface": "browser",
                    "connector_id": "computer_use_browser",
                    "connector_label": "Computer Browser",
                },
                "snapshot_ref": screenshot_path,
            }

            task = build_browse_task(
                url=clean_url,
                max_pages=max_pages,
                max_scroll_steps=max_scroll_steps,
                follow_same_domain_links=follow_same_domain_links,
                interaction_actions=interaction_actions,
            )
            for raw_event in run_agent_loop(session, task, max_iterations=12):
                event_index += 1
                event_type = str(raw_event.get("event_type") or "").strip().lower()
                if event_type == "screenshot":
                    screenshot_path = write_snapshot(
                        screenshot_b64=str(raw_event.get("screenshot_b64") or ""),
                        label=f"frame-{event_index}",
                    )
                    yield {
                        "event_type": "browser_verify",
                        "title": "Capture browser frame",
                        "detail": str(raw_event.get("url") or session.current_url()),
                        "data": {
                            "url": str(raw_event.get("url") or session.current_url()),
                            "scene_surface": "browser",
                            "connector_id": "computer_use_browser",
                        },
                        "snapshot_ref": screenshot_path,
                    }
                    continue
                if event_type == "action":
                    action_name = str(raw_event.get("action") or "action").strip() or "action"
                    yield {
                        "event_type": "browser_interaction_started",
                        "title": f"Computer action: {action_name}",
                        "detail": action_name,
                        "data": {
                            "url": session.current_url(),
                            "scene_surface": "browser",
                            "action": action_name,
                            "connector_id": "computer_use_browser",
                            **cursor_payload(raw_event),
                        },
                        "snapshot_ref": screenshot_path or None,
                    }
                    continue
                if event_type == "text":
                    text = str(raw_event.get("text") or raw_event.get("detail") or "").strip()
                    if text:
                        text_rows.append(text)
                        yield {
                            "event_type": "browser_extract",
                            "title": "Extract page findings",
                            "detail": compact_text(text, limit=200),
                            "data": {
                                "url": session.current_url(),
                                "scene_surface": "browser",
                                "connector_id": "computer_use_browser",
                            },
                            "snapshot_ref": screenshot_path or None,
                        }
                    continue
                if event_type == "error":
                    error_text = str(raw_event.get("detail") or "Computer Use browser execution failed").strip()
                    yield {
                        "event_type": "browser_interaction_failed",
                        "title": "Computer browser action failed",
                        "detail": compact_text(error_text, limit=220),
                        "data": {
                            "url": session.current_url(),
                            "scene_surface": "browser",
                            "connector_id": "computer_use_browser",
                        },
                        "snapshot_ref": screenshot_path or None,
                    }
                    break
                if event_type in {"done", "max_iterations"}:
                    yield {
                        "event_type": "browser_interaction_completed",
                        "title": "Browser inspection complete",
                        "detail": str(raw_event.get("url") or session.current_url()),
                        "data": {
                            "url": str(raw_event.get("url") or session.current_url()),
                            "scene_surface": "browser",
                            "connector_id": "computer_use_browser",
                        },
                        "snapshot_ref": screenshot_path or None,
                    }
                    if event_type == "done":
                        break

            forced_scroll_steps = session.scroll_through_page(
                max_steps=max(20, min(90, int(max_scroll_steps) * 30))
            )
            if forced_scroll_steps:
                latest = forced_scroll_steps[-1]
                screenshot_path = write_snapshot(
                    screenshot_b64=session.screenshot_b64(),
                    label="post-scroll",
                )
                yield {
                    "event_type": "browser_scroll",
                    "title": "Scroll through full page",
                    "detail": f"Reached {round(float(latest.get('scroll_percent') or 0.0), 1)}% of the page",
                    "data": {
                        "url": session.current_url(),
                        "scene_surface": "browser",
                        "connector_id": "computer_use_browser",
                        "scroll_percent": round(float(latest.get("scroll_percent") or 0.0), 2),
                        "scroll_steps": len(forced_scroll_steps),
                        "scroll_direction": "down",
                    },
                    "snapshot_ref": screenshot_path or None,
                }

            model_excerpt = "\n\n".join(text_rows).strip()
            dom_excerpt = session.extract_page_text(max_chars=12000)
            lowered_model = model_excerpt.lower()
            low_signal_model = any(token in lowered_model for token in _LOW_SIGNAL_TOKENS)
            if dom_excerpt and (low_signal_model or len(dom_excerpt) > len(model_excerpt) + 200):
                text_excerpt = dom_excerpt
            else:
                text_excerpt = model_excerpt or dom_excerpt

            highlight_plan = plan_llm_highlights(
                user_query=str(highlight_query or clean_url),
                page_text=text_excerpt,
                user_settings=self.settings,
                max_items=8,
            )
            highlight_terms = [str(item).strip() for item in highlight_plan.get("terms", []) if str(item).strip()]
            highlight_regions = session.sentence_regions(terms=highlight_terms, limit=8)
            highlight_sentences = [
                str(item.get("sentence") or "").strip()
                for item in highlight_regions
                if isinstance(item, dict) and str(item.get("sentence") or "").strip()
            ][:8]
            if highlight_regions:
                session.apply_highlight_regions(
                    regions=highlight_regions,
                    color=effective_highlight_color,
                )
                screenshot_path = write_snapshot(
                    screenshot_b64=session.screenshot_b64(),
                    label="highlight",
                )
                yield {
                    "event_type": "browser_keyword_highlight",
                    "title": "Highlight prompt-relevant findings",
                    "detail": ", ".join(highlight_terms[:5]),
                    "data": {
                        "url": session.current_url(),
                        "scene_surface": "browser",
                        "connector_id": "computer_use_browser",
                        "keywords": highlight_terms[:8],
                        "highlight_sentences": highlight_sentences,
                        "highlight_regions": highlight_regions,
                        "highlight_color": effective_highlight_color,
                        "match_count": len(highlight_regions),
                    },
                    "snapshot_ref": screenshot_path or None,
                }
            else:
                highlight_sentences = []

            profile = quality_profile(text=text_excerpt, error_text=error_text)
            try:
                title = session.page_title()
            except Exception:
                title = ""
            try:
                final_url = session.current_url()
            except Exception:
                final_url = clean_url
            page_row = {
                "url": final_url,
                "title": title,
                "text_excerpt": text_excerpt,
                "screenshot_path": screenshot_path,
                "keywords": highlight_terms[:8],
                "highlight_sentences": highlight_sentences,
                "highlight_regions": highlight_regions[:8],
                "highlight_color": effective_highlight_color,
                "render_quality": profile["render_quality"],
                "content_density": profile["content_density"],
                "blocked_signal": profile["blocked_signal"],
                "blocked_reason": profile["blocked_reason"],
            }
            return {
                "url": final_url,
                "title": title or final_url,
                "text_excerpt": text_excerpt,
                "screenshot_path": screenshot_path,
                "cursor_x": 0.0,
                "cursor_y": 0.0,
                "pages": [page_row],
                "render_quality": profile["render_quality"],
                "content_density": profile["content_density"],
                "keywords": highlight_terms[:8],
                "highlight_sentences": highlight_sentences,
                "highlight_regions": highlight_regions[:8],
                "highlight_color": effective_highlight_color,
                "blocked_signal": profile["blocked_signal"],
                "blocked_reason": profile["blocked_reason"],
                "stages": {
                    "initial_render": True,
                    "lazy_load_scroll": max(1, int(max_scroll_steps)),
                    "same_domain_followup": 1 if follow_same_domain_links else 0,
                },
            }
        except Exception as exc:
            raise ConnectorError(f"Computer Use browser task failed: {exc}") from exc
        finally:
            registry.close(session.session_id)

    def submit_contact_form_live_stream(
        self,
        *,
        url: str,
        sender_name: str,
        sender_email: str,
        sender_company: str = "",
        sender_phone: str = "",
        subject: str,
        message: str,
        auto_accept_cookies: bool = True,
        timeout_ms: int = 25000,
        wait_ms: int = 1200,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        del auto_accept_cookies, timeout_ms, wait_ms
        return (
            yield from stream_contact_form_live(
                connector_user_id=self._connector_user_id(),
                url=url,
                sender_name=sender_name,
                sender_email=sender_email,
                sender_company=sender_company,
                sender_phone=sender_phone,
                subject=subject,
                message=message,
            )
        )

    def _connector_user_id(self) -> str:
        return str(self.settings.get("__agent_user_id") or self.settings.get("agent.tenant_id") or "system")
