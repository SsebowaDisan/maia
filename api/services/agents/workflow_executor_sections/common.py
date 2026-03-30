from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from api.schemas.workflow_definition import WorkflowStep
from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value

logger = logging.getLogger(__name__)

_MAX_PARALLEL_STEPS = 5
_RETRY_BASE_DELAY = 1.0
_CITATION_SECTION_HEADING_RE = re.compile(
    r"^##\s+(?:Evidence\s+Citations|Sources|References)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_CITATION_LINE_RE = re.compile(r"^\s*-\s*\[(\d+)\]\s*(.+?)\s*$", re.MULTILINE)
_INLINE_CITATION_RE = re.compile(r"\[(\d+)\]")
_EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_EMAIL_SUBJECT_RE = re.compile(r"(?im)^\s*subject:\s*(.+?)\s*$")
_EMAIL_TO_RE = re.compile(r"(?im)^\s*to:\s*(.+?)\s*$")
_SEARCH_HOSTS = {
    "search.brave.com",
    "www.google.com",
    "google.com",
    "www.bing.com",
    "bing.com",
    "duckduckgo.com",
    "www.duckduckgo.com",
}


class WorkflowExecutionError(Exception):
    pass


def _step_tool_ids(step: WorkflowStep | None) -> list[str]:
    step_config = getattr(step, "step_config", None)
    if step is None or not isinstance(step_config, dict):
        return []
    raw = step_config.get("tool_ids")
    if not isinstance(raw, list):
        return []
    return [str(tool_id).strip() for tool_id in raw if str(tool_id).strip()]


def _extract_email_from_text(text: Any) -> str:
    match = _EMAIL_RE.search(str(text or ""))
    return str(match.group(1)).strip() if match else ""


def _normalize_http_url(value: Any) -> str:
    raw = str(value or "").strip().strip(" <>\"'`").rstrip(".,;:!?")
    if not raw or not re.match(r"^https?://", raw, flags=re.IGNORECASE):
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return parsed.geturl()


def _clean_stage_topic(value: Any) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    extracted = _extract_stage_topic(text)
    return extracted[:180] if extracted else text[:180]


_TOPIC_WRAPPER_MARKERS = (
    "research online",
    "search online",
    "research about",
    "research on",
    "make research",
    "conduct research",
    "find information",
    "gather evidence",
)


def _needs_topic_extraction(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split()).strip()
    if not normalized:
        return False
    if len(normalized.split()) <= 4 and "?" not in normalized:
        return False
    return any(marker in normalized for marker in _TOPIC_WRAPPER_MARKERS) or " about " in normalized


@lru_cache(maxsize=256)
def _extract_stage_topic(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    if env_bool("MAIA_AGENT_LLM_STAGE_TOPIC_EXTRACTION_ENABLED", default=True) and _needs_topic_extraction(cleaned):
        payload = call_json_response(
            system_prompt=(
                "You extract the core research topic from an agent stage instruction. "
                "Return strict JSON only."
            ),
            user_prompt=(
                "Return JSON only in this schema:\n"
                '{ "topic": "machine learning" }\n'
                "Rules:\n"
                "- Keep only the core subject/topic to research.\n"
                "- Remove operational wrapper words like research/search/find/gather/open/verify.\n"
                "- Do not include formatting instructions or delivery instructions.\n"
                "- Keep it concise, usually 2-8 words.\n\n"
                f"Input:\n{cleaned}"
            ),
            temperature=0.0,
            timeout_seconds=8,
            max_tokens=120,
        )
        normalized = sanitize_json_value(payload) if isinstance(payload, dict) else None
        if isinstance(normalized, dict):
            topic = " ".join(str(normalized.get("topic") or "").split()).strip()
            if topic:
                return topic
    return _fallback_stage_topic(cleaned)


def _fallback_stage_topic(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    for marker in (" about ", " on "):
        if marker in lowered:
            idx = lowered.find(marker)
            candidate = cleaned[idx + len(marker):].strip(" .,:;!?-")
            if candidate:
                return candidate
    return cleaned


def _normalize_delivery_artifact(text: Any) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not value:
        return ""
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def _preferred_artifact_keys(step: WorkflowStep | None) -> list[str]:
    if step is None or not isinstance(getattr(step, "input_mapping", None), dict):
        return []
    preferred: list[str] = []
    for param, source in step.input_mapping.items():
        raw_source = str(source or "").strip()
        if not raw_source or raw_source.startswith("literal:") or raw_source.startswith("context:"):
            continue
        preferred.append(str(param).strip())
    return [key for key in preferred if key]


def _extract_terminal_citation_section(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    heading = _CITATION_SECTION_HEADING_RE.search(raw)
    if not heading:
        return ""
    section = raw[heading.start():].strip()
    return section if section and _CITATION_LINE_RE.search(section) else ""


def _looks_like_email_draft(text: Any) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if raw.startswith("Subject:"):
        return True
    if "## evidence citations" in lowered and any(
        marker in lowered for marker in ("\nhi", "\nhello", "\ndear", "\nbest regards", "\nregards")
    ):
        return True
    return False


def _is_search_like_url(url: str) -> bool:
    normalized = _normalize_http_url(url)
    if not normalized:
        return True
    try:
        parsed = urlparse(normalized)
    except Exception:
        return True
    host = (parsed.netloc or "").lower()
    if host in _SEARCH_HOSTS:
        return True
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()
    return path == "/search" or "search?" in normalized.lower() or query.startswith("q=")


def _display_label_for_url(url: str) -> str:
    normalized = _normalize_http_url(url)
    if not normalized:
        return "Source"
    parsed = urlparse(normalized)
    host = (parsed.netloc or "source").lower()
    host_label = host[4:] if host.startswith("www.") else host
    segments = [segment for segment in (parsed.path or "").split("/") if segment]
    if not segments:
        return host_label
    tail = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", segments[-1]).replace("-", " ").replace("_", " ").strip()
    if not tail or len(tail) < 4 or len(tail) > 72 or tail.isdigit():
        return host_label
    return f"{tail.title()} | {host_label}"


def _looks_like_customer_facing_output(step: WorkflowStep | None, output: Any) -> bool:
    raw = str(output or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if raw.startswith("Subject:"):
        return True
    if _has_terminal_citation_section(raw) and any(
        marker in lowered
        for marker in ("\nhi ", "\nhello", "\ndear ", "best regards", "kind regards", "warm regards")
    ):
        return True
    if step is None:
        return False
    description = " ".join(str(getattr(step, "description", "") or "").lower().split())
    tool_ids = set(_step_tool_ids(step))
    if "email" in description and _has_terminal_citation_section(raw):
        return True
    if tool_ids.intersection({"gmail.draft", "email.draft", "mailer.report_send"}) and _has_terminal_citation_section(raw):
        return True
    return False


def _has_terminal_citation_section(text: str) -> bool:
    return bool(_CITATION_SECTION_HEADING_RE.search(str(text or "")))


def _count_inline_citation_markers(text: str) -> int:
    return len(list(_INLINE_CITATION_RE.finditer(str(text or ""))))


def _has_strong_citation_scaffold(text: str) -> bool:
    raw = str(text or "")
    return _has_terminal_citation_section(raw) and _count_inline_citation_markers(raw) >= 3


def _emit(on_event: Optional[Callable], event: dict[str, Any]) -> None:
    if on_event:
        try:
            on_event(event)
        except Exception:
            pass


def _format_inputs(inputs: dict[str, Any]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in inputs.items())


def _eval_condition(condition: str, outputs: dict[str, Any]) -> bool:
    condition = condition.strip()
    if re.search(r"\bOR\b", condition, re.IGNORECASE):
        parts = re.split(r"\bOR\b", condition, flags=re.IGNORECASE)
        return any(_eval_condition(p.strip(), outputs) for p in parts if p.strip())
    if re.search(r"\bAND\b", condition, re.IGNORECASE):
        parts = re.split(r"\bAND\b", condition, flags=re.IGNORECASE)
        return all(_eval_condition(p.strip(), outputs) for p in parts if p.strip())
    not_m = re.match(r"^NOT\s+(.+)$", condition, re.IGNORECASE)
    if not_m:
        return not _eval_condition(not_m.group(1).strip(), outputs)

    cmp_re = re.compile(r"^output\.([A-Za-z_]\w*)\s*(==|!=|>=|<=|>|<)\s*(.+)$")
    match = cmp_re.match(condition)
    if match:
        key, op, raw_val = match.group(1), match.group(2), match.group(3).strip()
        lhs = outputs.get(key)
        if (raw_val.startswith('"') and raw_val.endswith('"')) or (raw_val.startswith("'") and raw_val.endswith("'")):
            rhs: Any = raw_val[1:-1]
        elif raw_val in ("True", "true"):
            rhs = True
        elif raw_val in ("False", "false"):
            rhs = False
        elif raw_val in ("None", "null"):
            rhs = None
        else:
            try:
                rhs = int(raw_val)
            except ValueError:
                try:
                    rhs = float(raw_val)
                except ValueError:
                    rhs = raw_val
        if op == "==":
            return lhs == rhs
        if op == "!=":
            return lhs != rhs
        try:
            lhs_n, rhs_n = float(lhs), float(rhs)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        return {">": lhs_n > rhs_n, ">=": lhs_n >= rhs_n, "<": lhs_n < rhs_n, "<=": lhs_n <= rhs_n}.get(op, False)

    truthy_re = re.compile(r"^output\.([A-Za-z_]\w*)$")
    truthy_match = truthy_re.match(condition)
    if truthy_match:
        return bool(outputs.get(truthy_match.group(1)))

    logger.warning("Unsupported workflow condition syntax (skipping): %r", condition)
    return False
