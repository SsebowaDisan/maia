from __future__ import annotations

import re
from typing import Any


def read_destinations(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    if not text:
        return []
    parts = re.split(r",|;|\band\b", text, flags=re.IGNORECASE)
    return [part.strip() for part in parts if part.strip()]


def safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except Exception:
        return default


def route_from_prompt(prompt: str) -> tuple[str, list[str]]:
    text = " ".join(str(prompt or "").split()).strip()
    if not text:
        return "", []
    match = re.search(
        r"\bfrom\s+(?P<origin>.+?)\s+to\s+(?P<destinations>.+?)(?:[.?!]|$)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return "", []
    origin = str(match.group("origin") or "").strip()
    destinations = read_destinations(match.group("destinations"))
    return origin, destinations


def email_from_text(text: str) -> str:
    match = re.search(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", str(text or ""))
    return str(match.group(1)).strip() if match else ""


def emails_from_text(text: str) -> list[str]:
    raw = re.findall(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", str(text or ""))
    output: list[str] = []
    for item in raw:
        cleaned = str(item).strip()
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output


def invoice_number_from_text(text: str) -> str:
    match = re.search(
        r"\bINV(?:[-_ ][A-Za-z0-9][A-Za-z0-9_-]*|[0-9][A-Za-z0-9_-]*)\b",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    return str(match.group(0)).replace(" ", "") if match else ""


def amount_from_text(text: str) -> float | None:
    match = re.search(r"(?:\$|usd\s*)(\d+(?:\.\d{1,2})?)", str(text or ""), flags=re.IGNORECASE)
    if not match:
        return None
    try:
        value = float(str(match.group(1)).strip())
    except Exception:
        return None
    if value <= 0:
        return None
    return value
