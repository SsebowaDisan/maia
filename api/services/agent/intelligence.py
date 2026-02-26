from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urlparse

from api.services.agent.models import AgentAction, AgentSource

EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
NUMBER_RE = re.compile(r"\b\d+(?:[\.,]\d+)?\b")
STOPWORDS = {
    "about",
    "after",
    "also",
    "been",
    "being",
    "between",
    "company",
    "from",
    "have",
    "into",
    "more",
    "most",
    "other",
    "that",
    "their",
    "there",
    "these",
    "this",
    "those",
    "using",
    "with",
    "your",
    "http",
    "https",
    "www",
}
NEGATION_TERMS = {"no", "not", "never", "without", "none", "cannot", "can't"}


@dataclass(frozen=True)
class TaskIntelligence:
    objective: str
    target_url: str
    target_host: str
    delivery_email: str
    requires_delivery: bool
    requires_web_inspection: bool
    requested_report: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "target_url": self.target_url,
            "target_host": self.target_host,
            "delivery_email": self.delivery_email,
            "requires_delivery": self.requires_delivery,
            "requires_web_inspection": self.requires_web_inspection,
            "requested_report": self.requested_report,
        }


def _compact(text: str, max_len: int = 220) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= max_len:
        return clean
    return f"{clean[: max_len - 1].rstrip()}..."


def _extract_first_email(*chunks: str) -> str:
    joined = " ".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    match = EMAIL_RE.search(joined)
    return match.group(1).strip() if match else ""


def _extract_first_url(*chunks: str) -> str:
    joined = " ".join(str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip())
    match = URL_RE.search(joined)
    return match.group(0).strip().rstrip(".,;)") if match else ""


def derive_task_intelligence(*, message: str, agent_goal: str | None = None) -> TaskIntelligence:
    raw = f"{message} {agent_goal or ''}".strip()
    lowered = raw.lower()
    target_url = _extract_first_url(raw)
    host = (urlparse(target_url).hostname or "").strip().lower() if target_url else ""
    delivery_email = _extract_first_email(raw)
    requires_delivery = any(token in lowered for token in ("send", "deliver", "email")) and bool(
        delivery_email
    )
    requires_web_inspection = bool(target_url) or any(
        token in lowered for token in ("website", "web", "online", "source", "research", "analy")
    )
    requested_report = any(token in lowered for token in ("report", "summary", "analysis", "brief"))
    return TaskIntelligence(
        objective=_compact(message, 280),
        target_url=target_url,
        target_host=host,
        delivery_email=delivery_email,
        requires_delivery=requires_delivery,
        requires_web_inspection=requires_web_inspection,
        requested_report=requested_report,
    )


def _tokenize(text: str) -> set[str]:
    words = [match.group(0).lower() for match in WORD_RE.finditer(str(text or ""))]
    return {word for word in words if word not in STOPWORDS and len(word) >= 4}


def _contains_negation(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(term in lowered.split() for term in NEGATION_TERMS)


def _collect_evidence_units(
    *,
    sources: list[AgentSource],
    executed_steps: list[dict[str, Any]],
) -> list[dict[str, str]]:
    units: list[dict[str, str]] = []
    for source in sources:
        metadata = source.metadata if isinstance(source.metadata, dict) else {}
        excerpt = ""
        for key in ("excerpt", "snippet", "text_excerpt", "description"):
            value = metadata.get(key) if isinstance(metadata, dict) else None
            if isinstance(value, str) and value.strip():
                excerpt = value.strip()
                break
        candidate = " ".join(
            part for part in [source.label.strip(), excerpt] if part
        ).strip()
        if not candidate:
            continue
        units.append(
            {
                "source": source.label.strip() or "Source",
                "url": str(source.url or "").strip(),
                "text": _compact(candidate, 560),
            }
        )
    for row in executed_steps:
        tool_id = str(row.get("tool_id") or "").strip()
        summary = str(row.get("summary") or "").strip()
        if not tool_id or not summary:
            continue
        units.append(
            {
                "source": tool_id,
                "url": "",
                "text": _compact(summary, 320),
            }
        )
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for unit in units:
        key = f"{unit['source']}|{unit['text']}".lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(unit)
    return deduped[:24]


def _extract_claim_candidates(
    *,
    executed_steps: list[dict[str, Any]],
    actions: list[AgentAction],
    limit: int = 8,
) -> list[str]:
    text_blocks: list[str] = []
    for row in executed_steps:
        if str(row.get("status") or "") != "success":
            continue
        summary = str(row.get("summary") or "").strip()
        title = str(row.get("title") or "").strip()
        if summary:
            text_blocks.append(f"{title}. {summary}" if title else summary)
    for action in actions:
        if action.status != "success":
            continue
        if action.summary.strip():
            text_blocks.append(action.summary.strip())
    combined = "\n".join(text_blocks)
    fragments = re.split(r"[.\n;!?]+", combined)
    claims: list[str] = []
    seen: set[str] = set()
    for raw in fragments:
        claim = " ".join(raw.split()).strip()
        if len(claim) < 24:
            continue
        tokens = _tokenize(claim)
        if len(tokens) < 4:
            continue
        key = claim.lower()
        if key in seen:
            continue
        seen.add(key)
        claims.append(_compact(claim, 240))
        if len(claims) >= limit:
            break
    return claims


def _score_claim_support(
    *,
    claim: str,
    evidence_units: list[dict[str, str]],
) -> dict[str, Any]:
    claim_tokens = _tokenize(claim)
    if not claim_tokens:
        return {
            "claim": claim,
            "supported": False,
            "score": 0.0,
            "evidence_source": "",
            "evidence_excerpt": "",
        }
    best_score = 0.0
    best_source = ""
    best_excerpt = ""
    for evidence in evidence_units:
        evidence_text = str(evidence.get("text") or "")
        if not evidence_text:
            continue
        evidence_tokens = _tokenize(evidence_text)
        if not evidence_tokens:
            continue
        overlap = len(claim_tokens.intersection(evidence_tokens))
        score = overlap / float(max(1, len(claim_tokens)))
        if score > best_score:
            best_score = score
            best_source = str(evidence.get("source") or "")
            best_excerpt = _compact(evidence_text, 200)
    supported = best_score >= 0.22
    return {
        "claim": claim,
        "supported": supported,
        "score": round(best_score, 3),
        "evidence_source": best_source,
        "evidence_excerpt": best_excerpt,
    }


def _detect_potential_contradictions(evidence_units: list[dict[str, str]]) -> list[dict[str, Any]]:
    contradictions: list[dict[str, Any]] = []
    limited = evidence_units[:12]
    for left_idx in range(len(limited)):
        left = limited[left_idx]
        left_text = str(left.get("text") or "")
        left_tokens = _tokenize(left_text)
        if len(left_tokens) < 4:
            continue
        left_numbers = NUMBER_RE.findall(left_text)
        left_negation = _contains_negation(left_text)
        for right_idx in range(left_idx + 1, len(limited)):
            right = limited[right_idx]
            right_text = str(right.get("text") or "")
            right_tokens = _tokenize(right_text)
            if len(right_tokens) < 4:
                continue
            overlap = left_tokens.intersection(right_tokens)
            if len(overlap) < 4:
                continue
            right_numbers = NUMBER_RE.findall(right_text)
            right_negation = _contains_negation(right_text)
            contradiction_reason = ""
            if left_negation != right_negation and len(overlap) >= 5:
                contradiction_reason = "negation_mismatch"
            elif left_numbers and right_numbers and left_numbers[0] != right_numbers[0] and len(overlap) >= 5:
                contradiction_reason = "numeric_mismatch"
            if not contradiction_reason:
                continue
            contradictions.append(
                {
                    "type": contradiction_reason,
                    "left_source": str(left.get("source") or ""),
                    "right_source": str(right.get("source") or ""),
                    "overlap_terms": sorted(list(overlap))[:8],
                    "left_excerpt": _compact(left_text, 180),
                    "right_excerpt": _compact(right_text, 180),
                }
            )
            if len(contradictions) >= 6:
                return contradictions
    return contradictions


def build_verification_report(
    *,
    task: TaskIntelligence,
    planned_tool_ids: list[str],
    executed_steps: list[dict[str, Any]],
    actions: list[AgentAction],
    sources: list[AgentSource],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    executed_success = [row for row in executed_steps if str(row.get("status")) == "success"]
    action_failures = [item for item in actions if item.status == "failed"]
    source_urls = [str(source.url or "").strip() for source in sources if str(source.url or "").strip()]
    unique_source_urls = list(dict.fromkeys(source_urls))
    has_browser_success = any(
        str(row.get("tool_id")) == "browser.playwright.inspect" and str(row.get("status")) == "success"
        for row in executed_steps
    )
    has_report_success = any(
        str(row.get("tool_id")) == "report.generate" and str(row.get("status")) == "success"
        for row in executed_steps
    )
    has_send_success = any(
        item.tool_id in ("gmail.send", "email.send") and item.status == "success" for item in actions
    )
    send_attempted = any(item.tool_id in ("gmail.send", "email.send") for item in actions)
    evidence_units = _collect_evidence_units(sources=sources, executed_steps=executed_steps)
    claim_candidates = _extract_claim_candidates(executed_steps=executed_steps, actions=actions)
    claim_assessments = [
        _score_claim_support(claim=claim, evidence_units=evidence_units)
        for claim in claim_candidates
    ]
    supported_claims = [item for item in claim_assessments if item.get("supported")]
    contradictions = _detect_potential_contradictions(evidence_units)

    def add_check(name: str, passed: bool, detail: str) -> None:
        checks.append(
            {
                "name": name,
                "status": "pass" if passed else "warn",
                "detail": detail,
            }
        )

    add_check(
        "Plan executed",
        bool(executed_success),
        f"{len(executed_success)} successful step(s), {len(executed_steps)} total step(s).",
    )
    if task.requires_web_inspection:
        add_check(
            "Website evidence captured",
            has_browser_success,
            "Browser inspection completed." if has_browser_success else "No successful browser inspection found.",
        )
    add_check(
        "Source grounding",
        len(unique_source_urls) > 0,
        f"{len(unique_source_urls)} unique source URL(s) linked to this run.",
    )
    if task.requested_report:
        add_check(
            "Report generated",
            has_report_success,
            "Report draft was generated." if has_report_success else "No report generation success found.",
        )
    if claim_assessments:
        claim_support_ratio = len(supported_claims) / float(max(1, len(claim_assessments)))
        add_check(
            "Claim support coverage",
            claim_support_ratio >= 0.6,
            f"{len(supported_claims)}/{len(claim_assessments)} extracted claim(s) have direct evidence support.",
        )
    else:
        add_check(
            "Claim support coverage",
            False,
            "No claim candidates were extracted from tool outputs.",
        )
    add_check(
        "Contradiction scan",
        len(contradictions) == 0,
        "No strong contradiction signals detected across evidence units."
        if not contradictions
        else f"{len(contradictions)} potential contradiction signal(s) detected.",
    )
    if task.requires_delivery:
        add_check(
            "Requested delivery completed",
            has_send_success,
            "Message sent successfully."
            if has_send_success
            else "Send requested but not completed successfully.",
        )
        if send_attempted and not has_send_success:
            latest_send_error = next(
                (item.summary for item in reversed(actions) if item.tool_id in ("gmail.send", "email.send")),
                "",
            )
            auth_hint = ""
            lowered_error = str(latest_send_error).lower()
            if "invalid authentication" in lowered_error or "oauth" in lowered_error or "refresh_token" in lowered_error:
                auth_hint = "Reconnect Google OAuth in Settings and retry."
            elif "required role" in lowered_error and "admin" in lowered_error:
                auth_hint = "Use Full Access for this run or set agent role to admin/owner."
            if auth_hint:
                checks.append(
                    {
                        "name": "Delivery remediation",
                        "status": "warn",
                        "detail": auth_hint,
                    }
                )

    add_check(
        "Execution stability",
        len(action_failures) == 0,
        "No tool failures detected." if not action_failures else f"{len(action_failures)} tool failure(s) detected.",
    )

    pass_count = sum(1 for check in checks if check.get("status") == "pass")
    total = max(1, len(checks))
    score = round((pass_count / total) * 100.0, 2)
    grade = "strong" if score >= 85 else "fair" if score >= 60 else "weak"
    return {
        "score": score,
        "grade": grade,
        "checks": checks,
        "planned_tools": planned_tool_ids,
        "claim_assessments": claim_assessments[:10],
        "contradictions": contradictions[:6],
        "evidence_units": evidence_units[:12],
    }
