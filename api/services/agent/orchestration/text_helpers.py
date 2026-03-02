from __future__ import annotations

import re
from typing import Any


def compact(text: str, max_len: int = 140) -> str:
    clean = " ".join(str(text or "").split())
    return clean if len(clean) <= max_len else f"{clean[: max_len - 1].rstrip()}..."


def truncate_text(text: str, max_len: int = 1800) -> str:
    raw = str(text or "")
    return raw if len(raw) <= max_len else f"{raw[: max_len - 1].rstrip()}..."


def chunk_preserve_text(text: str, chunk_size: int = 220, limit: int = 8) -> list[str]:
    if not text:
        return []
    size = max(48, int(chunk_size or 220))
    chunks = [text[idx : idx + size] for idx in range(0, len(text), size)]
    return chunks[: max(1, int(limit or 8))]


def truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def extract_action_artifact_metadata(data: dict[str, Any] | None, *, step: int) -> dict[str, Any]:
    metadata: dict[str, Any] = {"step": step}
    if not isinstance(data, dict):
        return metadata
    for key in (
        "url",
        "document_url",
        "spreadsheet_url",
        "path",
        "pdf_path",
        "document_id",
        "spreadsheet_id",
    ):
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        metadata[key] = text[:320]
    for key in (
        "provider",
        "provider_requested",
        "provider_fallback_enabled",
        "web_provider",
        "quality_band",
        "render_quality",
        "blocked_signal",
        "blocked_reason",
        "routing_mode",
        "adapter",
    ):
        if key not in data:
            continue
        value = data.get(key)
        if isinstance(value, bool):
            metadata[key] = value
            continue
        if isinstance(value, (int, float)):
            metadata[key] = value
            continue
        text = str(value or "").strip()
        if text:
            metadata[key] = text[:120]
    if "content_density" in data:
        try:
            metadata["content_density"] = round(float(data.get("content_density") or 0.0), 4)
        except Exception:
            pass
    for numeric_key in ("quality_score", "schema_coverage", "confidence"):
        if numeric_key not in data:
            continue
        try:
            metadata[numeric_key] = round(float(data.get(numeric_key) or 0.0), 4)
        except Exception:
            continue
    items = data.get("items")
    if isinstance(items, list):
        evidence_rows: list[dict[str, str]] = []
        for row in items[:5]:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip()[:120]
            url = str(row.get("url") or "").strip()[:220]
            if not label and not url:
                continue
            evidence_rows.append({"label": label, "url": url})
        if evidence_rows:
            metadata["evidence_items"] = evidence_rows
    copied = data.get("copied_snippets")
    if isinstance(copied, list):
        cleaned = [str(item).strip() for item in copied if str(item).strip()]
        if cleaned:
            metadata["copied_snippets"] = cleaned[:4]
    plot_payload = _sanitize_plot_payload(data.get("plot"))
    if plot_payload:
        metadata["plot"] = plot_payload
    return metadata


def _sanitize_plot_point(point: Any) -> dict[str, Any] | None:
    if not isinstance(point, dict):
        return None
    x_value = point.get("x")
    if x_value is None:
        return None
    sanitized: dict[str, Any] = {"x": x_value if isinstance(x_value, (int, float)) else str(x_value)[:120]}
    metric_count = 0
    for raw_key, raw_value in list(point.items())[:12]:
        key = str(raw_key or "").strip()[:80]
        if not key or key == "x":
            continue
        if isinstance(raw_value, (int, float)):
            sanitized[key] = raw_value
            metric_count += 1
            continue
        value_text = str(raw_value or "").strip()
        if value_text:
            sanitized[key] = value_text[:120]
            metric_count += 1
    if metric_count <= 0:
        return None
    if "y" not in sanitized:
        for key in sanitized:
            if key != "x":
                sanitized["y"] = sanitized[key]
                break
    return sanitized


def _sanitize_plot_series(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in payload[:8]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("data_key") or "").strip()[:80]
        if not key:
            continue
        cleaned.append(
            {
                "key": key,
                "label": str(item.get("label") or key).strip()[:120],
                "type": str(item.get("type") or "").strip().lower()[:16],
                "color": str(item.get("color") or "").strip()[:24],
            }
        )
    return cleaned


def _sanitize_plot_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    kind = str(payload.get("kind") or "").strip().lower()
    if kind != "chart":
        return None
    chart_type = str(payload.get("chart_type") or "").strip().lower()
    if chart_type not in {"line", "bar", "scatter", "histogram"}:
        return None
    points = payload.get("points")
    clean_points: list[dict[str, Any]] = []
    if isinstance(points, list):
        for point in points[:600]:
            normalized = _sanitize_plot_point(point)
            if normalized:
                clean_points.append(normalized)
    if not clean_points:
        return None
    series = _sanitize_plot_series(payload.get("series"))
    if not series:
        y_name = str(payload.get("y") or "y").strip()[:80] or "y"
        series = [{"key": y_name, "label": y_name, "type": chart_type, "color": ""}]
    row_count_value = payload.get("row_count")
    try:
        row_count = int(row_count_value)
    except Exception:
        row_count = len(clean_points)
    interactive_payload = payload.get("interactive")
    interactive: dict[str, Any] = {}
    if isinstance(interactive_payload, dict):
        if "brush" in interactive_payload:
            interactive["brush"] = bool(interactive_payload.get("brush"))
    return {
        "kind": "chart",
        "library": "recharts",
        "chart_type": chart_type,
        "title": str(payload.get("title") or "").strip()[:180],
        "x": str(payload.get("x") or "").strip()[:120],
        "y": str(payload.get("y") or "").strip()[:120],
        "x_type": str(payload.get("x_type") or "").strip()[:24],
        "row_count": row_count,
        "series": series,
        "interactive": interactive,
        "points": clean_points,
    }


EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def extract_first_email(*chunks: str) -> str:
    joined = " ".join(
        str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip()
    )
    match = EMAIL_RE.search(joined)
    return match.group(1).strip() if match else ""


def issue_fix_hint(issue: str) -> str:
    text = str(issue or "").lower()
    if "gmail_dwd_api_disabled" in text or "gmail api is not enabled" in text:
        return (
            "Enable Gmail API in the Google Cloud project used by the service account, "
            "then retry."
        )
    if "gmail_dwd_delegation_denied" in text or "domain-wide delegation" in text:
        return (
            "Verify Workspace Domain-Wide Delegation for the service-account client ID and "
            "scope `https://www.googleapis.com/auth/gmail.send`."
        )
    if "gmail_dwd_mailbox_unavailable" in text or (
        "mailbox" in text and "suspended" in text
    ):
        return "Confirm the impersonated mailbox exists and is active in Google Workspace."
    if "required role" in text and "admin" in text:
        return (
            "Switch to Company Agent > Full Access for this run, "
            "or set `agent.user_role` to `admin`/`owner`."
        )
    if (
        "google_api_http_error" in text
        or "invalid authentication credentials" in text
        or "oauth" in text
        or "refresh_token" in text
    ):
        return "Reconnect Google OAuth in Settings and verify required scopes, then retry."
    return ""
