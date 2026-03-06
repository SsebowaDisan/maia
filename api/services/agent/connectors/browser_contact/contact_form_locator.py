from __future__ import annotations

from typing import Any


def score_form_candidate(form: Any) -> float:
    try:
        payload = form.evaluate(
            """
            (formEl) => {
                const controls = Array.from(formEl.querySelectorAll("input, textarea, select"));
                let visibleControls = 0;
                let textLikeControls = 0;
                let textareaCount = 0;
                let requiredCount = 0;
                for (const el of controls) {
                    if (!el) continue;
                    const type = String(el.getAttribute("type") || el.type || "").toLowerCase();
                    if (["hidden", "submit", "button", "reset", "image", "file"].includes(type)) continue;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    if (style.visibility === "hidden" || style.display === "none") continue;
                    visibleControls += 1;
                    if (el.tagName.toLowerCase() === "textarea") textareaCount += 1;
                    if (["", "text", "email", "tel", "search", "url"].includes(type) || el.tagName.toLowerCase() === "textarea") {
                        textLikeControls += 1;
                    }
                    if (el.required || el.hasAttribute("required") || String(el.getAttribute("aria-required") || "").toLowerCase() === "true") {
                        requiredCount += 1;
                    }
                }
                const submitCount = formEl.querySelectorAll("button[type='submit'], input[type='submit']").length;
                return { visibleControls, textLikeControls, textareaCount, requiredCount, submitCount };
            }
            """
        )
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    visible_controls = int(payload.get("visibleControls") or 0)
    text_like_controls = int(payload.get("textLikeControls") or 0)
    textarea_count = int(payload.get("textareaCount") or 0)
    required_count = int(payload.get("requiredCount") or 0)
    submit_count = int(payload.get("submitCount") or 0)
    score = 0.0
    if visible_controls >= 3:
        score += 1.2
    if text_like_controls >= 2:
        score += 1.0
    if textarea_count > 0:
        score += 0.8
    if required_count > 0:
        score += 0.6
    if submit_count > 0:
        score += 1.0
    return score


def find_best_form(page: Any) -> Any | None:
    try:
        forms = page.locator("form")
        total = min(forms.count(), 16)
    except Exception:
        return None
    best_form: Any | None = None
    best_score = 0.0
    for idx in range(total):
        form = forms.nth(idx)
        score = score_form_candidate(form)
        if score <= best_score:
            continue
        best_form = form
        best_score = score
    if best_score < 2.6:
        return None
    return best_form

