from __future__ import annotations

from typing import Any


def _clean_text(value: Any, *, limit: int = 220) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[: max(1, int(limit))]


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    token = str(value or "").strip().lower()
    if token in {"1", "true", "yes", "on"}:
        return True
    if token in {"0", "false", "no", "off"}:
        return False
    return False


def _safe_field_label(field_meta: dict[str, Any]) -> str:
    for key in ("label", "placeholder", "aria_label", "field_name", "field_id"):
        value = _clean_text(field_meta.get(key), limit=220)
        if value:
            return value
    return f"field #{max(0, _safe_int(field_meta.get('dom_index')))+1}"


def extract_form_schema(*, form: Any) -> list[dict[str, Any]]:
    try:
        raw = form.evaluate(
            """
            (formEl) => {
                const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const fields = [];
                const controls = Array.from(formEl.querySelectorAll("input, textarea, select, button"));
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                    const style = window.getComputedStyle(el);
                    return style && style.visibility !== "hidden" && style.display !== "none";
                };
                const findLabelText = (el) => {
                    if (!el) return "";
                    const labels = el.labels ? Array.from(el.labels) : [];
                    if (labels.length) {
                        const text = labels
                            .map((node) => normalize(node.innerText || node.textContent || ""))
                            .filter(Boolean)
                            .join(" ");
                        if (text) return text;
                    }
                    const parentLabel = el.closest("label");
                    if (parentLabel) {
                        const text = normalize(parentLabel.innerText || parentLabel.textContent || "");
                        if (text) return text;
                    }
                    const fieldId = normalize(el.getAttribute("id"));
                    if (!fieldId) return "";
                    const escaped = fieldId.replace(/["\\\\]/g, "\\\\$&");
                    const byFor = formEl.querySelector(`label[for="${escaped}"]`);
                    if (!byFor) return "";
                    return normalize(byFor.innerText || byFor.textContent || "");
                };
                for (let index = 0; index < controls.length; index += 1) {
                    const node = controls[index];
                    if (!node) continue;
                    const tag = normalize(node.tagName).toLowerCase();
                    const inputType = normalize(node.getAttribute("type") || node.type).toLowerCase();
                    const role = normalize(node.getAttribute("role")).toLowerCase();
                    const name = normalize(node.getAttribute("name"));
                    const id = normalize(node.getAttribute("id"));
                    const placeholder = normalize(node.getAttribute("placeholder"));
                    const ariaLabel = normalize(node.getAttribute("aria-label"));
                    const autocomplete = normalize(node.getAttribute("autocomplete")).toLowerCase();
                    const requiredAttr = Boolean(node.required || node.hasAttribute("required"));
                    const ariaRequired = normalize(node.getAttribute("aria-required")).toLowerCase() === "true";
                    const hasAsterisk = [findLabelText(node), placeholder, ariaLabel].some((value) => value.includes("*"));
                    const required = requiredAttr || ariaRequired || hasAsterisk;
                    const value = normalize("value" in node ? node.value : "");
                    fields.push({
                        dom_index: index,
                        tag,
                        input_type: inputType,
                        role,
                        field_name: name,
                        field_id: id,
                        label: findLabelText(node),
                        placeholder,
                        aria_label: ariaLabel,
                        autocomplete,
                        required,
                        empty: value.length === 0,
                        disabled: Boolean(node.disabled),
                        visible: isVisible(node),
                    });
                }
                return fields.slice(0, 64);
            }
            """
        )
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    fields: list[dict[str, Any]] = []
    for index, item in enumerate(raw[:64]):
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("label"), limit=220)
        placeholder = _clean_text(item.get("placeholder"), limit=220)
        aria_label = _clean_text(item.get("aria_label"), limit=220)
        required = _safe_bool(item.get("required"))
        if "required" not in item and any("*" in token for token in (label, placeholder, aria_label)):
            required = True
        empty = _safe_bool(item.get("empty"))
        if "empty" not in item:
            empty = True
        disabled = _safe_bool(item.get("disabled"))
        if "disabled" not in item:
            disabled = False
        visible = _safe_bool(item.get("visible"))
        if "visible" not in item:
            visible = True
        field = {
            "scan_index": index,
            "dom_index": max(0, _safe_int(item.get("dom_index"), default=index)),
            "tag": _clean_text(item.get("tag"), limit=24).lower(),
            "input_type": _clean_text(item.get("input_type"), limit=32).lower(),
            "role": _clean_text(item.get("role"), limit=32).lower(),
            "field_name": _clean_text(item.get("field_name"), limit=120),
            "field_id": _clean_text(item.get("field_id"), limit=120),
            "label": label,
            "placeholder": placeholder,
            "aria_label": aria_label,
            "autocomplete": _clean_text(item.get("autocomplete"), limit=64).lower(),
            "required": required,
            "empty": empty,
            "disabled": disabled,
            "visible": visible,
        }
        fields.append(field)
    return fields


def list_required_empty_fields(*, form: Any) -> list[dict[str, Any]]:
    fields = extract_form_schema(form=form)
    output: list[dict[str, Any]] = []
    for field in fields:
        if not field.get("visible"):
            continue
        if field.get("disabled"):
            continue
        if not field.get("required"):
            continue
        if not field.get("empty"):
            continue
        output.append(
            {
                **field,
                "field_label": _safe_field_label(field),
            }
        )
        if len(output) >= 24:
            break
    return output


def find_submit_control(*, form: Any) -> tuple[Any | None, dict[str, Any] | None]:
    schema = extract_form_schema(form=form)
    if not schema:
        return None, None
    preferred_indexes: list[int] = []
    fallback_indexes: list[int] = []
    for item in schema:
        if not item.get("visible") or item.get("disabled"):
            continue
        tag = str(item.get("tag") or "").lower()
        input_type = str(item.get("input_type") or "").lower()
        if tag not in {"button", "input"}:
            continue
        if input_type == "submit":
            preferred_indexes.append(int(item.get("dom_index") or 0))
            continue
        fallback_indexes.append(int(item.get("dom_index") or 0))
    for index in [*preferred_indexes, *fallback_indexes]:
        try:
            locator = form.locator("input, textarea, select, button").nth(index)
            if hasattr(locator, "is_visible") and not locator.is_visible():
                continue
            meta = next(
                (row for row in schema if int(row.get("dom_index") or -1) == index),
                None,
            )
            return locator, meta
        except Exception:
            continue
    return None, None
