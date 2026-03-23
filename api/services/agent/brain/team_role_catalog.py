"""Shared role catalog for Brain team assembly and collaboration."""
from __future__ import annotations

import re

ROLE_CATALOG: tuple[dict[str, object], ...] = (
    {
        "role": "supervisor",
        "label": "Supervisor",
        "description": "Owns scope, resolves ambiguity, assigns work, and decides when output is ready to ship.",
        "when_to_use": "Use when the task has multiple specialist steps, quality tradeoffs, or conflicting evidence.",
    },
    {
        "role": "research specialist",
        "label": "Research Specialist",
        "description": "Finds external sources, factual evidence, and source-backed claims.",
        "when_to_use": "Use when the request needs web research, market scans, benchmarks, or cited findings.",
    },
    {
        "role": "browser specialist",
        "label": "Browser Specialist",
        "description": "Navigates websites, searches live pages, and interacts with browser-based workflows.",
        "when_to_use": "Use when the task needs live website interaction, search result triage, or web UI operations.",
    },
    {
        "role": "document reader",
        "label": "Document Reader",
        "description": "Extracts grounded evidence from PDFs, reports, and uploaded files.",
        "when_to_use": "Use when the task depends on uploaded PDFs, documents, or file-based evidence.",
    },
    {
        "role": "analyst",
        "label": "Analyst",
        "description": "Compares evidence, quantifies claims, identifies inconsistencies, and draws structured conclusions.",
        "when_to_use": "Use when the task needs comparison, interpretation, metrics, or decision support.",
    },
    {
        "role": "reviewer",
        "label": "Reviewer",
        "description": "Challenges weak assumptions, requests proof, and checks whether the work is ready to move forward.",
        "when_to_use": "Use when the task needs quality control, contradiction checks, or claim verification.",
    },
    {
        "role": "writer",
        "label": "Writer",
        "description": "Turns evidence into clear reports, summaries, or client-facing communication.",
        "when_to_use": "Use when the task needs polished written output.",
    },
    {
        "role": "email specialist",
        "label": "Email Specialist",
        "description": "Drafts and prepares delivery-ready email communication.",
        "when_to_use": "Use when the request explicitly involves email drafting or rewriting.",
    },
    {
        "role": "delivery specialist",
        "label": "Delivery Specialist",
        "description": "Handles final sending, publishing, or outward delivery actions.",
        "when_to_use": "Use when the request explicitly asks to send, publish, submit, or dispatch the result.",
    },
)

_ROLE_LOOKUP = {
    str(entry["role"]).strip().lower(): entry
    for entry in ROLE_CATALOG
}


def format_role_catalog_for_prompt() -> str:
    return "\n".join(
        f"- {entry['label']} ({entry['role']}): {entry['description']} "
        f"When to use: {entry['when_to_use']}"
        for entry in ROLE_CATALOG
    )


def display_name_for_role(role: str) -> str:
    normalized = " ".join(str(role or "").strip().lower().split())
    entry = _ROLE_LOOKUP.get(normalized)
    if entry:
        return str(entry["label"])
    return " ".join(part.capitalize() for part in normalized.split()) or "Agent"


def fallback_system_prompt_for_role(role: str, *, request_description: str, task_focus: str) -> str:
    normalized = " ".join(str(role or "").strip().lower().split())
    entry = _ROLE_LOOKUP.get(normalized)
    role_label = str(entry["label"]) if entry else display_name_for_role(role)
    role_description = str(entry["description"]) if entry else (
        "Contribute specialist work, ask teammates for missing evidence, and hand off clearly."
    )
    focus = str(task_focus or "").strip()
    request = str(request_description or "").strip()
    prompt = (
        f"You are the {role_label} on a multi-agent team. {role_description} "
        "Work like a strong teammate: contribute your own specialist output, ask for missing evidence, "
        "challenge weak assumptions directly, and keep handoffs concise."
    )
    if focus:
        prompt += f" Current step focus: {focus[:400]}."
    if request:
        prompt += f" Overall task: {request[:500]}."
    return prompt


def infer_fallback_role(step_description: str, *, index: int) -> str:
    text = str(step_description or "").strip().lower()
    if any(marker in text for marker in ("review", "verify", "fact-check", "fact check", "challenge", "qa")):
        return "reviewer"
    if any(marker in text for marker in ("email", "subject line", "recipient", "inbox")):
        if any(marker in text for marker in ("send", "deliver", "dispatch", "submit", "publish")):
            return "delivery specialist"
        return "email specialist"
    if any(marker in text for marker in ("pdf", "document", "file", "attachment", "report page")):
        return "document reader"
    if any(marker in text for marker in ("browser", "website", "web", "search result", "search", "navigate")):
        return "browser specialist"
    if any(marker in text for marker in ("analysis", "analyze", "compare", "trend", "metric", "forecast", "evaluate")):
        return "analyst"
    if any(marker in text for marker in ("write", "rewrite", "draft", "summary", "report", "memo")):
        return "writer"
    if any(marker in text for marker in ("research", "source", "evidence", "investigate", "benchmark")):
        return "research specialist"
    if index == 1:
        return "supervisor"
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = " ".join(text.split())
    return text[:80] or f"specialist {index}"
