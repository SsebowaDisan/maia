from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.services.agent import llm_execution_support
from api.services.agent.llm_runtime import has_openai_credentials

from ..browser_live_utils import excerpt
from .capture import capture_page_state, move_cursor
from .detection import first_visible

LLM_CONTACT_INTENTS: tuple[str, ...] = (
    "name",
    "email",
    "phone",
    "company",
    "subject",
    "message",
)
_LLM_INTENT_SET = set(LLM_CONTACT_INTENTS)
_DEFAULT_LLM_CONFIDENCE_THRESHOLD = 0.68


def _field_from_label(form: Any, *, label_terms: tuple[str, ...]) -> Any | None:
    try:
        labels = form.locator("label")
        total = min(labels.count(), 40)
    except Exception:
        return None
    for idx in range(total):
        label = labels.nth(idx)
        try:
            text = " ".join(str(label.inner_text() or "").split()).strip().lower()
        except Exception:
            text = ""
        if not text:
            continue
        if not any(term in text for term in label_terms):
            continue
        try:
            html_for = str(label.get_attribute("for") or "").strip()
        except Exception:
            html_for = ""
        if html_for:
            by_id = first_visible(form, [f"[id='{html_for}']"])
            if by_id is not None:
                return by_id
        nested = first_visible(label, ["input, textarea, select"])
        if nested is not None:
            return nested
        parent = first_visible(label, ["xpath=.."])
        if parent is not None:
            candidate = first_visible(parent, ["input, textarea, select"])
            if candidate is not None:
                return candidate
    return None


def _intent_value_map(
    *,
    sender_name: str,
    sender_email: str,
    sender_company: str,
    sender_phone: str,
    subject: str,
    message: str,
) -> dict[str, str]:
    return {
        "name": " ".join(str(sender_name or "").split()).strip(),
        "email": " ".join(str(sender_email or "").split()).strip(),
        "company": " ".join(str(sender_company or "").split()).strip(),
        "phone": " ".join(str(sender_phone or "").split()).strip(),
        "subject": " ".join(str(subject or "").split()).strip(),
        "message": " ".join(str(message or "").split()).strip(),
    }


def _parse_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        pass
    token = str(value or "").strip().lower()
    if token in {"very_high", "very-high", "very high"}:
        return 0.95
    if token == "high":
        return 0.9
    if token in {"medium", "med", "moderate"}:
        return 0.7
    if token in {"low", "weak"}:
        return 0.45
    return 0.0


def scan_required_empty_fields(*, form: Any) -> list[dict[str, Any]]:
    try:
        raw = form.evaluate(
            """
            (formEl) => {
                const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const requiredWords = /(required|obligatoire|obligatorio|erforderlich|obrigat[oó]rio|必須|必填|필수|необх)/i;
                const elements = Array.from(formEl.querySelectorAll("input, textarea, select"));
                const items = [];

                const labelTextFor = (el) => {
                    if (el.labels && el.labels.length) {
                        const text = Array.from(el.labels)
                            .map((label) => normalize(label.innerText || label.textContent || ""))
                            .filter(Boolean)
                            .join(" ");
                        if (text) return text;
                    }
                    const parentLabel = el.closest("label");
                    if (parentLabel) {
                        const text = normalize(parentLabel.innerText || parentLabel.textContent || "");
                        if (text) return text;
                    }
                    const id = normalize(el.getAttribute("id"));
                    if (!id) return "";
                    const escaped = id.replace(/["\\\\]/g, "\\\\$&");
                    const byFor = formEl.querySelector(`label[for="${escaped}"]`);
                    if (!byFor) return "";
                    return normalize(byFor.innerText || byFor.textContent || "");
                };

                for (let index = 0; index < elements.length; index += 1) {
                    const el = elements[index];
                    if (!el || el.disabled) continue;
                    const tag = normalize(el.tagName).toLowerCase();
                    const type = normalize(el.getAttribute("type") || el.type).toLowerCase();
                    if (
                        type === "hidden" ||
                        type === "submit" ||
                        type === "button" ||
                        type === "reset" ||
                        type === "image" ||
                        type === "checkbox" ||
                        type === "radio" ||
                        type === "file"
                    ) {
                        continue;
                    }
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const visible =
                        rect.width > 0 &&
                        rect.height > 0 &&
                        style.visibility !== "hidden" &&
                        style.display !== "none";
                    if (!visible) continue;
                    const value = normalize("value" in el ? el.value : "");
                    if (value) continue;
                    const label = labelTextFor(el);
                    const placeholder = normalize(el.getAttribute("placeholder"));
                    const ariaLabel = normalize(el.getAttribute("aria-label"));
                    const fieldName = normalize(el.getAttribute("name"));
                    const fieldId = normalize(el.getAttribute("id"));
                    const autocomplete = normalize(el.getAttribute("autocomplete")).toLowerCase();
                    const requiredLikeText = `${label} ${placeholder} ${ariaLabel}`;
                    const requiredAttr = Boolean(el.required || el.hasAttribute("required"));
                    const ariaRequired = normalize(el.getAttribute("aria-required")).toLowerCase() === "true";
                    const likelyRequired =
                        requiredAttr ||
                        ariaRequired ||
                        requiredLikeText.includes("*") ||
                        requiredWords.test(requiredLikeText);
                    if (!likelyRequired) continue;

                    let errorText = "";
                    const describedBy = normalize(el.getAttribute("aria-describedby"));
                    if (describedBy) {
                        const ids = describedBy.split(/\\s+/).filter(Boolean);
                        for (const token of ids) {
                            let node = document.getElementById(token);
                            if (!node) {
                                const tagged = Array.from(formEl.querySelectorAll("[id]"));
                                node = tagged.find((candidate) => String(candidate.id || "") === token) || null;
                            }
                            if (!node) continue;
                            const text = normalize(node.innerText || node.textContent || "");
                            if (text) {
                                errorText = text;
                                break;
                            }
                        }
                    }
                    if (!errorText) {
                        const group = el.closest(".form-group, .field, .wpcf7-form-control-wrap, .gfield, li, div");
                        if (group) {
                            const hint = group.querySelector(
                                ".error, .errors, .invalid-feedback, .wpcf7-not-valid-tip, [role='alert'], .hs-error-msg, .help-block"
                            );
                            if (hint) {
                                errorText = normalize(hint.innerText || hint.textContent || "");
                            }
                        }
                    }
                    items.push({
                        scan_index: items.length,
                        dom_index: index,
                        tag,
                        input_type: type,
                        label,
                        placeholder,
                        aria_label: ariaLabel,
                        field_name: fieldName,
                        field_id: fieldId,
                        autocomplete,
                        error_text: errorText,
                    });
                }
                return items.slice(0, 16);
            }
            """
        )
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(raw[:16]):
        if not isinstance(item, dict):
            continue
        try:
            dom_index = int(item.get("dom_index", idx))
        except Exception:
            dom_index = idx
        normalized.append(
            {
                "scan_index": int(idx),
                "dom_index": max(0, dom_index),
                "tag": str(item.get("tag") or "").strip().lower(),
                "input_type": str(item.get("input_type") or "").strip().lower(),
                "label": " ".join(str(item.get("label") or "").split()).strip(),
                "placeholder": " ".join(str(item.get("placeholder") or "").split()).strip(),
                "aria_label": " ".join(str(item.get("aria_label") or "").split()).strip(),
                "field_name": " ".join(str(item.get("field_name") or "").split()).strip(),
                "field_id": " ".join(str(item.get("field_id") or "").split()).strip(),
                "autocomplete": " ".join(str(item.get("autocomplete") or "").split()).strip().lower(),
                "error_text": " ".join(str(item.get("error_text") or "").split()).strip(),
            }
        )
    return normalized


def parse_llm_required_field_mappings(
    *,
    payload: dict[str, Any] | None,
    unresolved_fields: list[dict[str, Any]],
    intent_values: dict[str, str],
    minimum_confidence: float = _DEFAULT_LLM_CONFIDENCE_THRESHOLD,
) -> list[dict[str, Any]]:
    rows = payload.get("mappings") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not unresolved_fields:
        return []
    best_by_field: dict[int, dict[str, Any]] = {}
    threshold = max(0.0, min(1.0, float(minimum_confidence)))
    for entry in rows[:24]:
        if not isinstance(entry, dict):
            continue
        raw_index = entry.get("field_index")
        if raw_index is None:
            raw_index = entry.get("scan_index")
        try:
            field_index = int(raw_index)
        except Exception:
            continue
        if field_index < 0 or field_index >= len(unresolved_fields):
            continue
        intent = str(entry.get("intent") or "").strip().lower()
        if intent not in _LLM_INTENT_SET:
            continue
        value = " ".join(str(intent_values.get(intent) or "").split()).strip()
        if not value:
            continue
        confidence = _parse_confidence(entry.get("confidence"))
        if confidence < threshold:
            continue
        current = best_by_field.get(field_index)
        if current and float(current.get("confidence") or 0.0) >= confidence:
            continue
        best_by_field[field_index] = {
            "field_index": field_index,
            "intent": intent,
            "value": value,
            "confidence": confidence,
            "reason": " ".join(str(entry.get("reason") or "").split()).strip(),
        }
    return [best_by_field[index] for index in sorted(best_by_field.keys())]


def _safe_field_label(field_meta: dict[str, Any]) -> str:
    for key in ("label", "placeholder", "aria_label", "field_name", "field_id"):
        token = " ".join(str(field_meta.get(key) or "").split()).strip()
        if token:
            return token
    return f"required field #{int(field_meta.get('dom_index') or 0) + 1}"


def _fill_locator_value(*, field: Any, value: str) -> bool:
    clean_value = " ".join(str(value or "").split()).strip()
    if not clean_value:
        return False
    try:
        tag = str(field.evaluate("el => (el.tagName || '').toLowerCase()") or "").strip()
    except Exception:
        tag = ""
    try:
        field.click(timeout=3000)
        if tag == "select":
            try:
                field.select_option(label=clean_value, timeout=3500)
                return True
            except Exception:
                try:
                    field.select_option(value=clean_value, timeout=3500)
                    return True
                except Exception:
                    options = field.evaluate(
                        """
                        (el) => Array.from(el.options || [])
                            .map((opt) => ({
                                value: String(opt.value || ""),
                                label: String(opt.label || opt.text || ""),
                            }))
                        """
                    )
                    if isinstance(options, list):
                        fallback = ""
                        for option in options:
                            if not isinstance(option, dict):
                                continue
                            option_label = str(option.get("label") or "").strip().lower()
                            option_value = str(option.get("value") or "").strip()
                            if not option_label or option_label.startswith("select"):
                                continue
                            if clean_value.lower() in option_label and option_value:
                                fallback = option_value
                                break
                            if not fallback and option_value:
                                fallback = option_value
                        if fallback:
                            field.select_option(value=fallback, timeout=3500)
                            return True
            return False
        field.fill(clean_value, timeout=4000)
        return True
    except Exception:
        return False


def _resolve_required_fields_with_llm(
    *,
    unresolved_fields: list[dict[str, Any]],
    intent_values: dict[str, str],
    minimum_confidence: float,
) -> tuple[list[dict[str, Any]], str]:
    if not unresolved_fields:
        return [], "no unresolved required fields"
    if not has_openai_credentials():
        return [], "OpenAI credentials missing; skipped LLM field mapping"
    available_values = {
        key: value
        for key, value in intent_values.items()
        if key in _LLM_INTENT_SET and value
    }
    if not available_values:
        return [], "No sender values available for fallback mapping"
    compact_fields = []
    for idx, item in enumerate(unresolved_fields):
        compact_fields.append(
            {
                "field_index": idx,
                "label": _safe_field_label(item),
                "input_type": str(item.get("input_type") or ""),
                "tag": str(item.get("tag") or ""),
                "autocomplete": str(item.get("autocomplete") or ""),
                "error_text": str(item.get("error_text") or "")[:120],
            }
        )
    user_payload = {
        "required_fields": compact_fields,
        "available_values": {key: value[:220] for key, value in available_values.items()},
    }
    llm_response = llm_execution_support.call_json_response(
        system_prompt=(
            "You map unresolved website contact-form fields to known sender intents. "
            "Return only one JSON object with schema "
            '{"mappings":[{"field_index":0,"intent":"phone","confidence":0.0,"reason":""}]}. '
            "Allowed intents: name,email,phone,company,subject,message. "
            "Never map consent, captcha, newsletter, or anti-bot fields."
        ),
        user_prompt=(
            "Map unresolved required fields to the best matching intents.\n"
            "Only include mappings you are confident about.\n"
            f"Input data:\n{json.dumps(user_payload, ensure_ascii=True)}"
        ),
        temperature=0.0,
        timeout_seconds=12,
        max_tokens=420,
    )
    mappings = parse_llm_required_field_mappings(
        payload=llm_response,
        unresolved_fields=unresolved_fields,
        intent_values=intent_values,
        minimum_confidence=minimum_confidence,
    )
    if mappings:
        return mappings, f"LLM mapped {len(mappings)} required field(s)"
    return [], "LLM did not return confident field mappings"


def fill_contact_fields(
    *,
    page: Any,
    form: Any,
    sender_name: str,
    sender_email: str,
    sender_company: str,
    sender_phone: str,
    subject: str,
    message: str,
    output_dir: Path,
    stamp_prefix: str,
    enable_llm_fallback: bool = True,
    llm_min_confidence: float = _DEFAULT_LLM_CONFIDENCE_THRESHOLD,
) -> tuple[list[str], list[dict[str, Any]]]:
    pending_events: list[dict[str, Any]] = []
    fields_filled: list[str] = []
    intent_values = _intent_value_map(
        sender_name=sender_name,
        sender_email=sender_email,
        sender_company=sender_company,
        sender_phone=sender_phone,
        subject=subject,
        message=message,
    )

    def _fill_field(
        *,
        selector_list: list[str],
        value: str,
        event_type: str,
        title: str,
        label_terms: tuple[str, ...] = (),
        max_preview: int = 140,
    ) -> None:
        if not value.strip():
            return
        field = first_visible(form, selector_list)
        if field is None and label_terms:
            field = _field_from_label(form, label_terms=label_terms)
        if field is None:
            return
        cursor = move_cursor(page=page, locator=field)
        if not _fill_locator_value(field=field, value=value):
            return
        field_token = event_type.rsplit("_", 1)[-1]
        if field_token not in fields_filled:
            fields_filled.append(field_token)
        capture = capture_page_state(
            page=page,
            label=event_type,
            output_dir=output_dir,
            stamp_prefix=stamp_prefix,
        )
        yield_payload = {
            "event_type": event_type,
            "title": title,
            "detail": excerpt(value, limit=max_preview),
            "data": {
                "url": capture["url"],
                "title": capture["title"],
                "contact_target_url": capture["url"],
                "typed_preview": value[:800],
                "field": event_type.rsplit("_", 1)[-1],
                **cursor,
            },
            "snapshot_ref": capture["screenshot_path"],
        }
        pending_events.append(yield_payload)

    _fill_field(
        selector_list=[
            "input[autocomplete='name']",
            "input[name='name' i]",
            "input[id*='name' i]",
            "input[placeholder*='name' i]",
        ],
        value=sender_name,
        event_type="browser_contact_fill_name",
        title="Fill contact name",
        label_terms=("name", "full name"),
    )
    _fill_field(
        selector_list=[
            "input[type='email']",
            "input[name='email' i]",
            "input[id*='email' i]",
            "input[placeholder*='email' i]",
            "input[aria-label*='email' i]",
        ],
        value=sender_email,
        event_type="browser_contact_fill_email",
        title="Fill contact email",
        label_terms=("email", "e-mail"),
    )
    _fill_field(
        selector_list=[
            "input[name*='company' i]",
            "input[id*='company' i]",
            "input[placeholder*='company' i]",
            "input[aria-label*='company' i]",
            "input[name*='organisation' i]",
            "input[name*='organization' i]",
            "input[id*='organisation' i]",
            "input[id*='organization' i]",
        ],
        value=sender_company,
        event_type="browser_contact_fill_company",
        title="Fill contact company",
        label_terms=("company", "organisation", "organization"),
    )
    _fill_field(
        selector_list=[
            "input[type='tel']",
            "input[name*='phone' i]",
            "input[id*='phone' i]",
            "input[name*='telephone' i]",
            "input[id*='telephone' i]",
            "input[name*='tel' i]",
            "input[id*='tel' i]",
            "input[name*='mobile' i]",
            "input[id*='mobile' i]",
            "input[placeholder*='phone' i]",
            "input[placeholder*='telephone' i]",
            "input[aria-label*='phone' i]",
            "input[aria-label*='telephone' i]",
            "input[autocomplete='tel']",
        ],
        value=sender_phone,
        event_type="browser_contact_fill_phone",
        title="Fill contact phone",
        label_terms=("phone", "telephone", "mobile", "tel"),
    )
    _fill_field(
        selector_list=[
            "input[name*='subject' i]",
            "input[id*='subject' i]",
            "input[placeholder*='subject' i]",
            "input[name*='topic' i]",
            "input[aria-label*='subject' i]",
        ],
        value=subject,
        event_type="browser_contact_fill_subject",
        title="Fill contact subject",
        label_terms=("subject", "topic"),
    )
    _fill_field(
        selector_list=[
            "textarea[name*='message' i]",
            "textarea[id*='message' i]",
            "textarea[placeholder*='message' i]",
            "textarea[aria-label*='message' i]",
            "textarea",
            "input[name*='message' i]",
            "input[id*='message' i]",
        ],
        value=message,
        event_type="browser_contact_fill_message",
        title="Fill contact message",
        label_terms=("message", "details", "inquiry", "enquiry"),
        max_preview=220,
    )

    unresolved_before = scan_required_empty_fields(form=form)
    scan_capture = capture_page_state(
        page=page,
        label="browser_contact_required_scan",
        output_dir=output_dir,
        stamp_prefix=stamp_prefix,
    )
    pending_events.append(
        {
            "event_type": "browser_contact_required_scan",
            "title": "Scan required contact fields",
            "detail": f"{len(unresolved_before)} required field(s) remain empty",
            "data": {
                "url": scan_capture["url"],
                "title": scan_capture["title"],
                "contact_target_url": scan_capture["url"],
                "required_empty_count": len(unresolved_before),
                "required_empty_fields": [
                    _safe_field_label(item) for item in unresolved_before[:8]
                ],
                "llm_fallback_enabled": bool(enable_llm_fallback),
            },
            "snapshot_ref": scan_capture["screenshot_path"],
        }
    )

    if unresolved_before:
        mapped_fields: list[dict[str, Any]] = []
        llm_detail = "LLM fallback disabled for contact field mapping"
        if enable_llm_fallback:
            mapped_fields, llm_detail = _resolve_required_fields_with_llm(
                unresolved_fields=unresolved_before,
                intent_values=intent_values,
                minimum_confidence=llm_min_confidence,
            )
        for mapped in mapped_fields:
            field_index = int(mapped.get("field_index") or -1)
            if field_index < 0 or field_index >= len(unresolved_before):
                continue
            field_meta = unresolved_before[field_index]
            dom_index = int(field_meta.get("dom_index") or 0)
            field = form.locator("input, textarea, select").nth(dom_index)
            intent = str(mapped.get("intent") or "").strip().lower()
            value = str(mapped.get("value") or "")
            confidence = float(mapped.get("confidence") or 0.0)
            if not _fill_locator_value(field=field, value=value):
                continue
            if intent and intent not in fields_filled:
                fields_filled.append(intent)
            cursor = move_cursor(page=page, locator=field)
            fill_capture = capture_page_state(
                page=page,
                label="browser_contact_llm_fill",
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
            )
            pending_events.append(
                {
                    "event_type": "browser_contact_llm_fill",
                    "title": "LLM fallback populated required field",
                    "detail": f"{_safe_field_label(field_meta)} -> {intent}",
                    "data": {
                        "url": fill_capture["url"],
                        "title": fill_capture["title"],
                        "contact_target_url": fill_capture["url"],
                        "typed_preview": value[:800],
                        "field": intent,
                        "mapped_intent": intent,
                        "field_label": _safe_field_label(field_meta),
                        "confidence": round(confidence, 3),
                        "llm_reason": str(mapped.get("reason") or "")[:220],
                        **cursor,
                    },
                    "snapshot_ref": fill_capture["screenshot_path"],
                }
            )
        unresolved_after = scan_required_empty_fields(form=form)
        llm_capture = capture_page_state(
            page=page,
            label="llm-form-field-mapping",
            output_dir=output_dir,
            stamp_prefix=stamp_prefix,
        )
        pending_events.append(
            {
                "event_type": "llm.form_field_mapping",
                "title": "Resolve required form fields with LLM fallback",
                "detail": llm_detail,
                "data": {
                    "url": llm_capture["url"],
                    "title": llm_capture["title"],
                    "contact_target_url": llm_capture["url"],
                    "required_empty_count_before": len(unresolved_before),
                    "required_empty_count_after": len(unresolved_after),
                    "llm_mapped_count": len(mapped_fields),
                    "llm_fallback_enabled": bool(enable_llm_fallback),
                },
                "snapshot_ref": llm_capture["screenshot_path"],
            }
        )
    return fields_filled, pending_events
