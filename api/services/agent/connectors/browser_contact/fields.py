from __future__ import annotations

from pathlib import Path
from typing import Any

from ..browser_live_utils import excerpt
from .capture import capture_page_state, move_cursor
from .field_resolver import (
    build_intent_values,
    fill_form_field_by_index,
    parse_llm_mappings,
    resolve_field_mappings_with_llm,
)
from .field_schema import extract_form_schema, list_required_empty_fields

_DEFAULT_LLM_CONFIDENCE_THRESHOLD = 0.68


def _safe_field_label(field_meta: dict[str, Any]) -> str:
    for key in ("field_label", "label", "placeholder", "aria_label", "field_name", "field_id"):
        token = " ".join(str(field_meta.get(key) or "").split()).strip()
        if token:
            return token
    return f"required field #{int(field_meta.get('dom_index') or 0) + 1}"


def _form_field_locator(form: Any, *, dom_index: int) -> Any | None:
    try:
        locator = form.locator("input, textarea, select, button").nth(max(0, int(dom_index)))
        return locator
    except Exception:
        return None


def scan_required_empty_fields(*, form: Any) -> list[dict[str, Any]]:
    rows = list_required_empty_fields(form=form)
    normalized: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "scan_index": int(row.get("scan_index") or idx),
                "dom_index": int(row.get("dom_index") or idx),
                "tag": str(row.get("tag") or "").strip().lower(),
                "input_type": str(row.get("input_type") or "").strip().lower(),
                "label": " ".join(str(row.get("label") or "").split()).strip(),
                "placeholder": " ".join(str(row.get("placeholder") or "").split()).strip(),
                "aria_label": " ".join(str(row.get("aria_label") or "").split()).strip(),
                "field_name": " ".join(str(row.get("field_name") or "").split()).strip(),
                "field_id": " ".join(str(row.get("field_id") or "").split()).strip(),
                "autocomplete": " ".join(str(row.get("autocomplete") or "").split()).strip().lower(),
                "field_label": _safe_field_label(row),
                "error_text": "",
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
    return parse_llm_mappings(
        payload=payload,
        fields=unresolved_fields,
        values=intent_values,
        minimum_confidence=minimum_confidence,
    )


def _apply_field_mappings(
    *,
    page: Any,
    form: Any,
    schema_rows: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
    output_dir: Path,
    stamp_prefix: str,
    fields_filled: list[str],
    event_title: str,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for mapped in mappings:
        field_index = int(mapped.get("field_index") or -1)
        if field_index < 0 or field_index >= len(schema_rows):
            continue
        field_meta = schema_rows[field_index]
        dom_index = int(field_meta.get("dom_index") or field_index)
        value = str(mapped.get("value") or "")
        intent = str(mapped.get("intent") or "").strip().lower()
        if not value or not intent:
            continue
        locator = _form_field_locator(form, dom_index=dom_index)
        cursor = move_cursor(page=page, locator=locator)
        if not fill_form_field_by_index(form=form, field_index=dom_index, value=value):
            continue
        if intent not in fields_filled:
            fields_filled.append(intent)
        capture = capture_page_state(
            page=page,
            label="browser-type-contact-field",
            output_dir=output_dir,
            stamp_prefix=stamp_prefix,
        )
        events.append(
            {
                "event_type": "browser_type",
                "title": event_title,
                "detail": f"{_safe_field_label(field_meta)} -> {intent}",
                "data": {
                    "url": capture["url"],
                    "title": capture["title"],
                    "contact_target_url": capture["url"],
                    "typed_preview": excerpt(value, limit=240),
                    "field": intent,
                    "mapped_intent": intent,
                    "field_label": _safe_field_label(field_meta),
                    "confidence": float(mapped.get("confidence") or 0.0),
                    "llm_reason": " ".join(str(mapped.get("reason") or "").split()).strip()[:220],
                    **cursor,
                },
                "snapshot_ref": capture["screenshot_path"],
            }
        )
    return events


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
    intent_values = build_intent_values(
        sender_name=sender_name,
        sender_email=sender_email,
        sender_company=sender_company,
        sender_phone=sender_phone,
        subject=subject,
        message=message,
    )
    schema_rows = extract_form_schema(form=form)
    schema_capture = capture_page_state(
        page=page,
        label="browser-contact-schema",
        output_dir=output_dir,
        stamp_prefix=stamp_prefix,
    )
    pending_events.append(
        {
            "event_type": "browser_extract",
            "title": "Inspect contact form schema",
            "detail": f"{len(schema_rows)} control(s) analyzed",
            "data": {
                "url": schema_capture["url"],
                "title": schema_capture["title"],
                "contact_target_url": schema_capture["url"],
                "schema_field_count": len(schema_rows),
                "llm_fallback_enabled": bool(enable_llm_fallback),
            },
            "snapshot_ref": schema_capture["screenshot_path"],
        }
    )

    unresolved_before = scan_required_empty_fields(form=form)
    scan_capture = capture_page_state(
        page=page,
        label="browser-contact-required-scan",
        output_dir=output_dir,
        stamp_prefix=stamp_prefix,
    )
    pending_events.append(
        {
            "event_type": "browser_extract",
            "title": "Scan required contact fields",
            "detail": f"{len(unresolved_before)} required field(s) remain empty",
            "data": {
                "url": scan_capture["url"],
                "title": scan_capture["title"],
                "contact_target_url": scan_capture["url"],
                "required_empty_count": len(unresolved_before),
                "required_empty_fields": [_safe_field_label(item) for item in unresolved_before[:8]],
            },
            "snapshot_ref": scan_capture["screenshot_path"],
        }
    )

    mapped_fields: list[dict[str, Any]] = []
    mapping_detail = "LLM fallback disabled for contact field mapping"
    if enable_llm_fallback:
        mapped_fields, mapping_detail = resolve_field_mappings_with_llm(
            fields=schema_rows,
            intent_values=intent_values,
            minimum_confidence=llm_min_confidence,
        )
    pending_events.extend(
        _apply_field_mappings(
            page=page,
            form=form,
            schema_rows=schema_rows,
            mappings=mapped_fields,
            output_dir=output_dir,
            stamp_prefix=stamp_prefix,
            fields_filled=fields_filled,
            event_title="Type contact field",
        )
    )

    unresolved_after_first_pass = scan_required_empty_fields(form=form)
    recovered_fields: list[dict[str, Any]] = []
    recovery_detail = "No secondary field recovery required"
    if enable_llm_fallback and unresolved_after_first_pass:
        recovered_fields, recovery_detail = resolve_field_mappings_with_llm(
            fields=unresolved_after_first_pass,
            intent_values=intent_values,
            minimum_confidence=max(0.55, float(llm_min_confidence) - 0.1),
        )
        pending_events.extend(
            _apply_field_mappings(
                page=page,
                form=form,
                schema_rows=unresolved_after_first_pass,
                mappings=recovered_fields,
                output_dir=output_dir,
                stamp_prefix=stamp_prefix,
                fields_filled=fields_filled,
                event_title="Recover unresolved required field",
            )
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
            "detail": mapping_detail if not recovered_fields else recovery_detail,
            "data": {
                "url": llm_capture["url"],
                "title": llm_capture["title"],
                "contact_target_url": llm_capture["url"],
                "required_empty_count_before": len(unresolved_before),
                "required_empty_count_after": len(unresolved_after),
                "llm_mapped_count": len(mapped_fields),
                "llm_recovered_count": len(recovered_fields),
                "llm_fallback_enabled": bool(enable_llm_fallback),
            },
            "snapshot_ref": llm_capture["screenshot_path"],
        }
    )
    return fields_filled, pending_events

