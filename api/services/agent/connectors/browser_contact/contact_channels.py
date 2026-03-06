from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def safe_text(value: Any, *, max_len: int = 180) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[: max(1, int(max_len))]


def normalize_url(raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return text


def page_title(page: Any) -> str:
    try:
        return safe_text(page.title(), max_len=180)
    except Exception:
        return ""


def cursor_payload(page: Any) -> dict[str, float]:
    try:
        viewport = page.evaluate(
            "() => ({ width: Number(window.innerWidth || 1366), height: Number(window.innerHeight || 768) })"
        )
        width = float(viewport.get("width") or 1366.0)
        height = float(viewport.get("height") or 768.0)
    except Exception:
        width = 1366.0
        height = 768.0
    return {
        "cursor_x": max(24.0, min(width - 24.0, width * 0.52)),
        "cursor_y": max(24.0, min(height - 24.0, height * 0.22)),
    }


def collect_contact_channels(page: Any) -> dict[str, list[str]]:
    try:
        payload = page.evaluate(
            """
            () => {
                const normalize = (value) => String(value || "").replace(/\\s+/g, " ").trim();
                const unique = (items, limit) => {
                    const out = [];
                    const seen = new Set();
                    for (const item of items || []) {
                        const token = normalize(item).toLowerCase();
                        if (!token || seen.has(token)) continue;
                        seen.add(token);
                        out.push(token);
                        if (out.length >= limit) break;
                    }
                    return out;
                };
                const emailFromMailto = [];
                const phoneFromTel = [];
                for (const link of Array.from(document.querySelectorAll("a[href]"))) {
                    const href = normalize(link.getAttribute("href"));
                    if (!href) continue;
                    if (href.toLowerCase().startsWith("mailto:")) {
                        emailFromMailto.push(href.slice(7).split("?")[0]);
                    } else if (href.toLowerCase().startsWith("tel:")) {
                        phoneFromTel.push(href.slice(4));
                    }
                }
                const bodyText = normalize(document.body ? document.body.innerText : "");
                const emailMatches = bodyText.match(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}/g) || [];
                const phoneMatches = bodyText.match(/\\+?[0-9][0-9\\s().-]{6,}[0-9]/g) || [];
                return {
                    emails: unique([...emailFromMailto, ...emailMatches], 8),
                    phones: unique([...phoneFromTel, ...phoneMatches], 8),
                };
            }
            """
        )
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    deduped_emails: list[str] = []
    deduped_phones: list[str] = []
    seen_emails: set[str] = set()
    seen_phones: set[str] = set()
    for raw_email in (payload.get("emails") if isinstance(payload.get("emails"), list) else []):
        token = str(raw_email).strip()[:180]
        key = token.lower()
        if not token or key in seen_emails:
            continue
        seen_emails.add(key)
        deduped_emails.append(token)
        if len(deduped_emails) >= 8:
            break
    for raw_phone in (payload.get("phones") if isinstance(payload.get("phones"), list) else []):
        token = str(raw_phone).strip()[:64]
        key = token.lower()
        if not token or key in seen_phones:
            continue
        seen_phones.add(key)
        deduped_phones.append(token)
        if len(deduped_phones) >= 8:
            break
    return {
        "emails": deduped_emails,
        "phones": deduped_phones,
    }

