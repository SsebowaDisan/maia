from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.services.agent.llm_runtime import call_json_response, has_openai_credentials

from ..base import ConnectorError
from ..browser_live_utils import excerpt
from .capture import capture_page_state, move_cursor
from .field_schema import find_submit_control, list_required_empty_fields


def _safe_text(value: Any, *, max_len: int = 240) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[: max(1, int(max_len))]


def _visible_form_signature(form: Any) -> dict[str, Any]:
    try:
        return form.evaluate(
            """
            (formEl) => {
                const controls = Array.from(formEl.querySelectorAll("input, textarea, select"));
                const enabledControls = controls.filter((el) => !el.disabled).length;
                const requiredControls = controls.filter((el) =>
                    el.required ||
                    el.hasAttribute("required") ||
                    String(el.getAttribute("aria-required") || "").toLowerCase() === "true"
                ).length;
                const rect = formEl.getBoundingClientRect();
                const style = window.getComputedStyle(formEl);
                return {
                    enabled_controls: enabledControls,
                    required_controls: requiredControls,
                    visible:
                        rect.width > 0 &&
                        rect.height > 0 &&
                        style.visibility !== "hidden" &&
                        style.display !== "none",
                };
            }
            """
        )
    except Exception:
        return {}


def _page_text_excerpt(page: Any, *, max_len: int = 420) -> str:
    try:
        body_text = str(page.evaluate("() => document.body ? document.body.innerText : ''") or "")
    except Exception:
        body_text = ""
    return excerpt(body_text, limit=max(120, int(max_len)))


def _submission_state(*, page: Any, form: Any) -> dict[str, Any]:
    required_empty = list_required_empty_fields(form=form)
    signature = _visible_form_signature(form)
    return {
        "url": str(page.url or ""),
        "title": _safe_text(page.title(), max_len=180),
        "required_empty_count": len(required_empty),
        "required_empty_labels": [
            _safe_text(item.get("field_label"), max_len=120)
            for item in required_empty[:8]
            if isinstance(item, dict)
        ],
        "form_visible": bool(signature.get("visible", True)),
        "enabled_controls": int(signature.get("enabled_controls") or 0),
        "required_controls": int(signature.get("required_controls") or 0),
        "page_text_excerpt": _page_text_excerpt(page, max_len=420),
    }


def _heuristic_submission_status(
    *,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> tuple[str, float, str]:
    before_required = int(before_state.get("required_empty_count") or 0)
    after_required = int(after_state.get("required_empty_count") or 0)
    url_before = str(before_state.get("url") or "")
    url_after = str(after_state.get("url") or "")
    form_visible_after = bool(after_state.get("form_visible", True))
    if not form_visible_after and after_required <= before_required:
        return "submitted", 0.82, "Form is no longer visible after submit action."
    if after_required < before_required:
        if url_before and url_after and url_before != url_after:
            return "submitted", 0.78, "Required empty fields decreased and page URL changed."
        return "submitted_unconfirmed", 0.72, "Required empty fields decreased after submit action."
    if url_before and url_after and url_before != url_after:
        return "submitted_unconfirmed", 0.65, "Page URL changed after submit action."
    return "not_submitted", 0.62, "No structural change indicated successful submission."


def _llm_submission_status(
    *,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> tuple[str, float, str]:
    if not has_openai_credentials():
        return _heuristic_submission_status(before_state=before_state, after_state=after_state)
    payload = {
        "before_state": before_state,
        "after_state": after_state,
    }
    try:
        response = call_json_response(
            system_prompt=(
                "You assess whether a website contact form submission appears successful. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Return JSON only in this schema:\n"
                '{ "status":"submitted|submitted_unconfirmed|not_submitted", "confidence":0.0, "reason":"..." }\n'
                "Rules:\n"
                "- Use structural evidence before lexical page text evidence.\n"
                "- Never invent page changes not present in input.\n"
                "- Keep confidence within [0,1].\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=10,
            max_tokens=260,
        )
    except Exception:
        response = None
    if not isinstance(response, dict):
        return _heuristic_submission_status(before_state=before_state, after_state=after_state)
    status = str(response.get("status") or "").strip().lower()
    if status not in {"submitted", "submitted_unconfirmed", "not_submitted"}:
        return _heuristic_submission_status(before_state=before_state, after_state=after_state)
    try:
        confidence = max(0.0, min(1.0, float(response.get("confidence"))))
    except Exception:
        confidence = 0.0
    reason = _safe_text(response.get("reason"), max_len=220)
    if not reason:
        _, fallback_confidence, fallback_reason = _heuristic_submission_status(
            before_state=before_state,
            after_state=after_state,
        )
        confidence = max(confidence, fallback_confidence * 0.8)
        reason = fallback_reason
    return status, confidence, reason


def _heuristic_human_verification_barrier(
    *,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> tuple[bool, float, str, str]:
    before_required = int(before_state.get("required_empty_count") or 0)
    after_required = int(after_state.get("required_empty_count") or 0)
    form_visible_after = bool(after_state.get("form_visible", True))
    enabled_controls_after = int(after_state.get("enabled_controls") or 0)
    if before_required > after_required and after_required == 0 and form_visible_after and enabled_controls_after > 0:
        return (
            True,
            0.56,
            "Submission is still awaiting an interactive verification step.",
            "verification_challenge",
        )
    return False, 0.0, "", ""


def _detect_human_verification_barrier(
    *,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> tuple[bool, float, str, str]:
    fallback = _heuristic_human_verification_barrier(
        before_state=before_state,
        after_state=after_state,
    )
    if not has_openai_credentials():
        return fallback
    payload = {
        "before_state": before_state,
        "after_state": after_state,
    }
    try:
        response = call_json_response(
            system_prompt=(
                "You detect whether a web form requires human verification after submit interaction. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Return JSON only in this schema:\n"
                '{ "human_verification_required": true, "confidence": 0.0, '
                '"barrier_type":"captcha|consent|verification_challenge|none", "reason":"..." }\n'
                "Rules:\n"
                "- Use semantic understanding of the page state.\n"
                "- Never rely on hardcoded keyword matching.\n"
                "- If a human challenge is present, set human_verification_required=true.\n"
                "- Keep confidence within [0,1].\n\n"
                f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
            ),
            temperature=0.0,
            timeout_seconds=10,
            max_tokens=280,
        )
    except Exception:
        return fallback
    if not isinstance(response, dict):
        return fallback
    required = bool(response.get("human_verification_required"))
    try:
        confidence = max(0.0, min(1.0, float(response.get("confidence"))))
    except Exception:
        confidence = 0.0
    barrier_type = _safe_text(response.get("barrier_type"), max_len=64).lower()
    if barrier_type not in {"captcha", "consent", "verification_challenge", "none"}:
        barrier_type = "verification_challenge" if required else "none"
    reason = _safe_text(response.get("reason"), max_len=220)
    if not required and confidence < 0.6 and fallback[0]:
        return fallback
    if required and not reason:
        reason = "Human verification is required before the contact form can be submitted."
    return required, confidence, reason, barrier_type


def submit_and_confirm(
    *,
    page: Any,
    form: Any,
    fields_filled: list[str],
    wait_ms: int,
    timeout_ms: int,
    output_dir: Path,
    stamp_prefix: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    submit_control, submit_meta = find_submit_control(form=form)
    if submit_control is None:
        raise ConnectorError("Contact form submit button could not be located.")

    before_state = _submission_state(page=page, form=form)
    submit_cursor = move_cursor(page=page, locator=submit_control)
    try:
        submit_control.click(timeout=4500)
        page.wait_for_timeout(max(900, int(wait_ms)))
        page.wait_for_load_state("networkidle", timeout=max(2500, int(timeout_ms) // 2))
    except Exception:
        pass

    submit_capture = capture_page_state(
        page=page,
        label="contact-submit",
        output_dir=output_dir,
        stamp_prefix=stamp_prefix,
    )
    submit_event = {
        "event_type": "browser_contact_submit",
        "title": "Submit contact form",
        "detail": "Click submit control",
        "data": {
            "url": submit_capture["url"],
            "title": submit_capture["title"],
            "contact_target_url": submit_capture["url"],
            "fields_filled": fields_filled,
            "selector": "form submit control",
            "submit_control": {
                "tag": str((submit_meta or {}).get("tag") or ""),
                "input_type": str((submit_meta or {}).get("input_type") or ""),
                "label": _safe_text((submit_meta or {}).get("label"), max_len=120),
            },
            **submit_cursor,
        },
        "snapshot_ref": submit_capture["screenshot_path"],
    }

    after_state = _submission_state(page=page, form=form)
    status, confidence, reason = _llm_submission_status(
        before_state=before_state,
        after_state=after_state,
    )
    human_verification_required, barrier_confidence, barrier_reason, barrier_type = _detect_human_verification_barrier(
        before_state=before_state,
        after_state=after_state,
    )
    if human_verification_required:
        status = "human_verification_required"
        confidence = max(confidence, barrier_confidence)
        reason = barrier_reason or reason or "Human verification is required."
    confirm_capture = capture_page_state(
        page=page,
        label="contact-confirm",
        output_dir=output_dir,
        stamp_prefix=stamp_prefix,
    )
    confirm_event_type = "browser_contact_human_verification_required" if human_verification_required else "browser_contact_confirmation"
    confirm_event_title = "Human verification required" if human_verification_required else "Verify contact form confirmation"
    confirm_event = {
        "event_type": confirm_event_type,
        "title": confirm_event_title,
        "detail": reason,
        "data": {
            "url": confirm_capture["url"],
            "title": confirm_capture["title"],
            "contact_target_url": confirm_capture["url"],
            "contact_status": status,
            "verification_confidence": round(confidence, 3),
            "required_empty_before": before_state.get("required_empty_count"),
            "required_empty_after": after_state.get("required_empty_count"),
            "form_visible_after": after_state.get("form_visible"),
            "human_verification_required": human_verification_required,
            "barrier_type": barrier_type if human_verification_required else "",
            "barrier_confidence": round(barrier_confidence, 3) if human_verification_required else 0.0,
        },
        "snapshot_ref": confirm_capture["screenshot_path"],
    }
    submitted = status in {"submitted", "submitted_unconfirmed"} and not human_verification_required
    return submit_event, confirm_event, {
        "submitted": submitted,
        "status": status,
        "confirmation_text": reason,
        "verification_confidence": round(confidence, 3),
        "url": confirm_capture["url"],
        "title": confirm_capture["title"],
        "screenshot_path": confirm_capture["screenshot_path"],
        "fields_filled": fields_filled,
        "human_handoff_required": human_verification_required,
        "handoff_reason": reason if human_verification_required else "",
        "handoff_type": barrier_type if human_verification_required else "",
    }
