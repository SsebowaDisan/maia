from __future__ import annotations

from typing import Any

from api.services.agent.llm_verification import build_llm_verification_check
from api.services.agent.models import AgentAction, AgentSource

from .claims import extract_claim_candidates, score_claim_support
from .constants import DELIVERY_ACTION_IDS
from .contradictions import detect_potential_contradictions
from .evidence import collect_evidence_units
from .models import TaskIntelligence


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
        item.tool_id in DELIVERY_ACTION_IDS and item.status == "success" for item in actions
    )
    send_attempted = any(item.tool_id in DELIVERY_ACTION_IDS for item in actions)
    evidence_units = collect_evidence_units(sources=sources, executed_steps=executed_steps)
    claim_candidates = extract_claim_candidates(executed_steps=executed_steps, actions=actions)
    claim_assessments = [
        score_claim_support(claim=claim, evidence_units=evidence_units)
        for claim in claim_candidates
    ]
    supported_claims = [item for item in claim_assessments if item.get("supported")]
    contradictions = detect_potential_contradictions(evidence_units)

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
                (item.summary for item in reversed(actions) if item.tool_id in DELIVERY_ACTION_IDS),
                "",
            )
            auth_hint = ""
            lowered_error = str(latest_send_error).lower()
            if "gmail_dwd_api_disabled" in lowered_error or "gmail api is not enabled" in lowered_error:
                auth_hint = "Enable Gmail API in Google Cloud for the service-account project and retry."
            elif "gmail_dwd_delegation_denied" in lowered_error or "domain-wide delegation" in lowered_error:
                auth_hint = (
                    "Verify Admin Console domain-wide delegation for the service-account client ID "
                    "and scope https://www.googleapis.com/auth/gmail.send."
                )
            elif "gmail_dwd_mailbox_unavailable" in lowered_error:
                auth_hint = "Confirm the impersonated mailbox exists and is active in Google Workspace."
            elif "invalid authentication" in lowered_error or "oauth" in lowered_error or "refresh_token" in lowered_error:
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
    llm_check = build_llm_verification_check(
        task=task.to_dict(),
        executed_steps=executed_steps,
        actions=actions,
        sources=sources,
    )
    if isinstance(llm_check, dict):
        checks.append(llm_check)

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
