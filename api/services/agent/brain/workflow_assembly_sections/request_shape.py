from __future__ import annotations

from functools import lru_cache
import re
from typing import Any

from api.services.agent.llm_runtime import call_json_response, env_bool, sanitize_json_value

from .common import _extract_email, _normalize_role_key


def _derive_request_focus(request_description: str) -> str:
    text = " ".join(str(request_description or "").split()).strip()
    if not text:
        return "the requested topic"
    llm_focus = _derive_request_focus_with_llm(text)
    if llm_focus:
        return llm_focus
    cleaned = re.sub(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:and|then)?\s*(?:write|draft|compose|send|deliver|email|mail)\b[\s\S]*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*(?:please\s+)?(?:make|do|perform|conduct|carry out|start|run)\s+(?:the\s+)?research(?:\s+online)?\s+(?:about|on)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*(?:research|analyse|analyze|investigate|study)\s+(?:about|on)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" .,:;!?-")
    return cleaned or text.strip(" .,:;!?-") or "the requested topic"


def _needs_focus_extraction(text: str) -> bool:
    normalized = " ".join(str(text or "").lower().split()).strip()
    if not normalized:
        return False
    if len(normalized.split()) <= 4 and "?" not in normalized:
        return False
    return any(
        marker in normalized
        for marker in (
            "research online",
            "research about",
            "research on",
            "make research",
            "conduct research",
            "write an email",
            "inline citations",
            "authoritative sources",
        )
    )


@lru_cache(maxsize=256)
def _derive_request_focus_with_llm(text: str) -> str:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned or not env_bool("MAIA_AGENT_LLM_REQUEST_FOCUS_ENABLED", default=True):
        return ""
    if not _needs_focus_extraction(cleaned):
        return ""
    payload = call_json_response(
        system_prompt=(
            "You extract the core subject of a user request for workflow planning. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "focus": "machine learning" }\n'
            "Rules:\n"
            "- Keep only the core subject/topic.\n"
            "- Remove wrapper verbs like make, research, search, email, write, send, gather.\n"
            "- Remove output formatting instructions and citation instructions.\n"
            "- Keep it concise, usually 2-8 words.\n\n"
            f"Input:\n{cleaned}"
        ),
        temperature=0.0,
        timeout_seconds=8,
        max_tokens=120,
    )
    normalized = sanitize_json_value(payload) if isinstance(payload, dict) else None
    if not isinstance(normalized, dict):
        return ""
    focus = " ".join(str(normalized.get("focus") or "").split()).strip()
    return focus[:180] if focus else ""


def _derive_primary_search_query(*, request_description: str, step: dict[str, Any]) -> str:
    text = " ".join(str(request_description or "").split()).strip()
    if not text:
        return str(step.get("description") or "").strip() or "the requested topic"
    target_url_match = re.search(r"https?://[^\s]+", text, flags=re.IGNORECASE)
    if target_url_match:
        return target_url_match.group(0).strip().rstrip(".,;:!?")
    focus = _derive_request_focus(text)
    focus = re.sub(r"\b(?:using|with)\s+multiple\s+authoritative\s+sources\b", "", focus, flags=re.IGNORECASE)
    focus = re.sub(r"\b(?:with|including)\s+inline\s+citations\b", "", focus, flags=re.IGNORECASE)
    focus = " ".join(focus.split()).strip(" .,:;!-")
    return focus or _derive_request_focus(text)


def _step_role_family(step: dict[str, Any]) -> str:
    role = _normalize_role_key(str(step.get("agent_role") or ""))
    description = " ".join(str(step.get("description") or "").split()).strip().lower()
    text = f"{role} {description}".strip()

    def _matches(*terms: str) -> bool:
        return any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) for term in terms)

    def _role_matches(*terms: str) -> bool:
        return any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", role) for term in terms)

    if _role_matches("deliver", "deliverer", "delivery", "mailer", "sender", "dispatch"):
        return "delivery"
    if _role_matches("email specialist", "writer", "author", "editor", "content", "drafter"):
        return "writer"
    if _role_matches("reviewer", "fact checker", "fact-check", "qa"):
        return "reviewer"
    if _role_matches("analyst", "analysis"):
        return "analysis"
    if _role_matches("browser", "research", "researcher", "research specialist", "document", "investigate"):
        return "research"
    if _matches("deliver", "delivery", "mailer", "sender", "dispatch"):
        return "delivery"
    if _matches("email specialist", "writer", "author", "editor", "content", "draft", "rewrite", "compose"):
        return "writer"
    if _matches("reviewer", "fact checker", "fact-check", "verify", "qa"):
        return "reviewer"
    if _matches("analyst", "analysis", "compare", "metric", "trend", "evaluate"):
        return "analysis"
    if _matches("browser", "research", "researcher", "document", "evidence", "search", "source", "investigate"):
        return "research"
    return "general"


def _request_needs_research_email_flow(request_description: str) -> bool:
    request = " ".join(str(request_description or "").split()).strip().lower()
    if not request:
        return False
    wants_delivery = bool(_extract_email(request_description)) or any(marker in request for marker in ("send", "email", "mail", "deliver"))
    wants_research = any(marker in request for marker in ("research", "investigate", "look up", "search", "sources", "evidence", "findings"))
    return wants_delivery and wants_research


def _request_needs_research_summary_flow(request_description: str) -> bool:
    request = " ".join(str(request_description or "").split()).strip().lower()
    if not request:
        return False
    wants_research = any(
        marker in request
        for marker in ("research", "investigate", "look up", "search", "sources", "evidence", "findings")
    )
    wants_delivery = bool(_extract_email(request_description)) or any(
        marker in request for marker in ("send", "email", "mail", "deliver")
    )
    return wants_research and not wants_delivery


def _research_step_description(focus: str) -> str:
    return (
        f"Research {focus} using multiple authoritative sources and extract source-backed findings with inline citations. "
        "Return a concise executive research brief with short headings, a premium polished tone, and a final "
        "Evidence Citations section. Synthesize the strongest converging evidence across representative sources "
        "instead of relying on a single article whenever broader support is available. Prefer an executive brief that "
        "lands around 1000-1500 characters when that range can preserve the strongest evidence clearly; exceed it only "
        "when compressing further would materially weaken clarity or citation integrity. Keep the output directly reusable "
        "in email drafting, typically fitting on a single screen when the topic is broad. Every inline citation marker "
        "[n] must resolve to a numbered row in the final Evidence Citations section. Do not draft or send the email."
    )


def _review_step_description(focus: str) -> str:
    return (
        f"Review the research findings about {focus}, verify the strongest supported claims, and challenge any weak "
        "or contradictory evidence before writing. Preserve inline citations and the final Evidence Citations section. "
        "Do not draft or send the email."
    )


def _research_summary_step_description(focus: str) -> str:
    return (
        f"Synthesize the research findings about {focus} into a concise executive brief with inline citations and a final "
        "Evidence Citations section. Explain the topic clearly, highlight the strongest supported findings, and remove weak "
        "or irrelevant sources. This stage writes the final user-facing answer only; do not send an email."
    )


def _writer_step_description(focus: str, recipient: str) -> str:
    return (
        f"Compose a polished, citation-rich email draft about {focus}" + (f" for {recipient}" if recipient else "")
        + ". Write the full send-ready draft with a clear Subject line, a professional greeting, a refined premium body, "
          "a compact executive summary, scannable key findings with inline citations, a final Evidence Citations section, "
          "and a professional sign-off. Use the cited research artifact from the previous step as the source of truth. "
          "Do not introduce new sources or renumber citations unless you are explicitly removing unsupported claims and "
          "keeping the remaining numbering internally consistent. Keep inline citations intact and preserve source "
          "numbering consistently. This stage drafts only; do not dispatch the email."
    )


def _delivery_step_description(recipient: str) -> str:
    return f"Send the cited email draft produced by the previous step to {recipient} without changing its substance." if recipient else "Send the cited email draft produced by the previous step without changing its substance."


def _rebalance_research_email_steps(*, steps: list[dict[str, Any]], request_description: str) -> list[dict[str, Any]]:
    if len(steps) < 2 or not _request_needs_research_email_flow(request_description):
        return steps
    focus = _derive_request_focus(request_description)
    recipient = _extract_email(request_description)
    updated_steps = [dict(step) for step in steps]
    families = [_step_role_family(step) for step in updated_steps]
    delivery_indexes = [index for index, family in enumerate(families) if family == "delivery"]
    if not delivery_indexes:
        return updated_steps
    delivery_index = delivery_indexes[-1]
    updated_steps[delivery_index]["description"] = _delivery_step_description(recipient)
    non_delivery_indexes = [index for index in range(delivery_index) if families[index] != "delivery"]
    if not non_delivery_indexes:
        return updated_steps
    research_index = non_delivery_indexes[0]
    updated_steps[research_index]["description"] = _research_step_description(focus)
    if len(non_delivery_indexes) == 1:
        return updated_steps
    writer_index = non_delivery_indexes[-1]
    if writer_index != research_index:
        updated_steps[writer_index]["description"] = _writer_step_description(focus, recipient)
    for index in non_delivery_indexes[1:-1]:
        updated_steps[index]["description"] = _review_step_description(focus)
    return updated_steps


def _ensure_research_summary_followup(*, steps: list[dict[str, Any]], edges: list[dict[str, str]], request_description: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if len(steps) != 1 or not _request_needs_research_summary_flow(request_description):
        return steps, edges
    first_step = dict(steps[0])
    first_family = _step_role_family(first_step)
    if first_family not in {"research", "analysis", "reviewer", "general"}:
        return steps, edges
    focus = _derive_request_focus(request_description)
    summary_step_id = "step_2"
    updated_steps = [first_step]
    updated_steps.append(
        {
            "step_id": summary_step_id,
            "agent_role": "writer",
            "description": _research_summary_step_description(focus),
            "tools_needed": ["report", "summary"],
        }
    )
    updated_edges = list(edges)
    if not any(
        str(edge.get("from_step") or "").strip() == str(first_step.get("step_id") or "").strip()
        and str(edge.get("to_step") or "").strip() == summary_step_id
        for edge in updated_edges
        if isinstance(edge, dict)
    ):
        updated_edges.append(
            {
                "from_step": str(first_step.get("step_id") or "").strip(),
                "to_step": summary_step_id,
            }
        )
    return updated_steps, updated_edges


def _rescope_step_descriptions(*, steps: list[dict[str, Any]], request_description: str) -> list[dict[str, Any]]:
    if len(steps) < 2:
        return steps
    focus = _derive_request_focus(request_description)
    recipient = _extract_email(request_description)
    has_delivery_step = any(_step_role_family(step) == "delivery" for step in steps)
    summary_only_flow = _request_needs_research_summary_flow(request_description)
    rescoped: list[dict[str, Any]] = []
    for index, step in enumerate(steps, start=1):
        updated = dict(step)
        family = _step_role_family(step)
        if family == "research":
            updated["description"] = _research_step_description(focus)
        elif family in {"analysis", "reviewer"}:
            updated["description"] = _review_step_description(focus)
        elif family == "writer":
            updated["description"] = (
                _research_summary_step_description(focus)
                if summary_only_flow and not recipient
                else _writer_step_description(focus, recipient)
            )
        elif family == "delivery":
            updated["description"] = _delivery_step_description(recipient)
        elif index == 1 and has_delivery_step:
            updated["description"] = _research_step_description(focus)
        rescoped.append(updated)
    return _rebalance_research_email_steps(steps=rescoped, request_description=request_description)


def _infer_input_mapping(step: dict, all_steps: list[dict], edges: list[dict], *, request_description: str = "") -> dict[str, str]:
    predecessors = [e["from_step"] for e in edges if e["to_step"] == step["step_id"]]
    mapping: dict[str, str] = {}
    if not predecessors:
        step_family = _step_role_family(step)
        if step_family in {"research", "analysis", "reviewer"}:
            primary_query = _derive_primary_search_query(request_description=request_description, step=step)
            mapping["query"] = f"literal:{primary_query}"
            mapping["topic"] = f"literal:{primary_query}"
        else:
            mapping["query"] = f"literal:{step.get('description', '')}"
    else:
        for pred_id in predecessors:
            pred = next((s for s in all_steps if s["step_id"] == pred_id), None)
            if pred:
                mapping[pred.get("agent_role", pred_id)] = f"output_{pred_id}"
    recipient = _extract_email(step.get("description", ""))
    if recipient:
        mapping.setdefault("to", f"literal:{recipient}")
        mapping.setdefault("recipient", f"literal:{recipient}")
    return mapping


def _normalize_step_tool_ids(*, step: dict[str, Any], request_description: str) -> list[str]:
    tool_hints = step.get("tools_needed")
    hints = tool_hints if isinstance(tool_hints, list) else []
    normalized: list[str] = []
    role_text = " ".join(str(step.get("agent_role") or "").split()).strip().lower()
    description_text = " ".join(str(step.get("description") or "").split()).strip().lower()
    text = " ".join([role_text, description_text]).strip()
    full_request = str(request_description or "").lower()
    hint_tokens = {str(raw or "").strip().lower() for raw in hints if str(raw or "").strip()}
    has_explicit_url = bool(re.search(r"https?://", text) or re.search(r"https?://", full_request))
    no_web_requested = any(marker in full_request for marker in ("do not browse", "don't browse", "no browsing", "do not search", "don't search", "no online search", "without web search", "no web search", "without browsing", "offline only", "no internet"))
    delivery_pattern = re.compile(r"\b(?:send|deliver|recipient|dispatch|outbox|email)\b")
    explicit_send_pattern = re.compile(r"\b(?:send|deliver|dispatch|outbox)\b(?![- ]ready)")
    negated_send_pattern = re.compile(r"\b(?:do not|don't|do n't|not)\s+(?:send|deliver|dispatch|outbox)\b")
    writing_patterns = (r"\brewrite\b", r"\bwrite\b", r"\bsummar(?:y|ize|ized|izing|isation|ization)\b", r"\bredraft\b", r"\bdraft\b", r"\bcompose\b", r"\breport(?:\s+(?:draft|email|summary|brief|memo|document))\b")
    research_patterns = (r"\bresearch\b", r"\bsearch\b", r"\bsource\b", r"\bsources\b", r"\bevidence\b", r"\binvestigat(?:e|ion)\b", r"\blook up\b", r"\bweb\b", r"\bonline\b", r"\bfact[- ]check\b")
    explicit_web_pattern = re.compile(r"\b(?:browse|browser|web|search|extract|inspect|open url|open page|visit)\b")
    visual_browser_pattern = re.compile(r"\b(?:browse|browser|inspect|open url|open page|visit|navigate|scroll|click|website)\b")
    is_writing_step = any(re.search(pattern, text) for pattern in writing_patterns)
    is_research_step = any(re.search(pattern, text) for pattern in research_patterns)
    research_needs_synthesis = bool(is_research_step and any(marker in text for marker in ("brief", "summary", "executive", "citations section", "evidence citations")))
    request_wants_research = any(re.search(pattern, full_request) for pattern in research_patterns)
    has_delivery_signal = bool(delivery_pattern.search(text))
    explicit_send_requested = bool(explicit_send_pattern.search(text)) and not bool(negated_send_pattern.search(text))
    role_implies_delivery = any(marker in role_text for marker in ("deliver", "delivery", "mailer", "sender", "dispatch"))
    role_implies_writing = any(marker in role_text for marker in ("writer", "author", "editor", "content", "email specialist", "drafter"))
    role_implies_research = any(marker in role_text for marker in ("research", "analyst", "reviewer", "browser", "document", "fact checker"))
    hint_has_delivery = bool(hint_tokens & {"send", "delivery", "deliver", "dispatch", "mailer"})
    hint_has_writing = bool(hint_tokens & {"report", "writer", "writing", "summary", "summarization", "rewrite", "draft", "email", "mail", "gmail"})
    hint_has_research = bool(hint_tokens & {"browser", "web", "search", "research", "sources", "evidence", "scrape", "scraping"})
    research_priority = role_implies_research or hint_has_research or is_research_step
    writing_priority = role_implies_writing or hint_has_writing or (is_writing_step and not role_implies_research and not hint_has_research)
    delivery_priority = role_implies_delivery or hint_has_delivery or (has_delivery_signal and not research_priority and not writing_priority)
    is_delivery_step = has_delivery_signal and (delivery_priority or not research_priority)
    delivery_only_writing = is_delivery_step and delivery_priority and not bool(explicit_web_pattern.search(text))
    explicit_send_delivery = bool(explicit_send_requested or role_implies_delivery or hint_has_delivery)
    visual_browser_requested = bool(visual_browser_pattern.search(text) or visual_browser_pattern.search(full_request))

    def _add(tool_id: str) -> None:
        value = str(tool_id or "").strip()
        if value and value not in normalized:
            normalized.append(value)

    for raw in hints:
        token = str(raw or "").strip().lower()
        if not token:
            continue
        if "." in token:
            _add(token)
            continue
        if token in {"gmail", "email", "mail"}:
            if explicit_send_delivery or delivery_priority:
                _add("gmail.draft")
            continue
        if token in {"send", "delivery", "deliver", "dispatch", "mailer"}:
            _add("gmail.draft"); _add("gmail.send"); _add("mailer.report_send"); continue
        if token in {"report", "writer", "writing", "summary", "summarization", "rewrite", "draft"}:
            if not delivery_only_writing:
                _add("report.generate")
            continue
        if token in {"browser", "web", "search", "research", "sources", "evidence", "scrape", "scraping"}:
            if not delivery_only_writing and not no_web_requested:
                _add("marketing.web_research"); _add("web.extract.structured")
                if has_explicit_url or visual_browser_requested:
                    _add("browser.playwright.inspect")
            continue
    if writing_priority and not delivery_only_writing:
        _add("report.generate")
    if research_needs_synthesis and not delivery_only_writing:
        _add("report.generate")
    if (is_research_step or research_priority) and not no_web_requested and not delivery_only_writing:
        _add("marketing.web_research"); _add("web.extract.structured")
        if has_explicit_url or visual_browser_requested:
            _add("browser.playwright.inspect")
    if explicit_send_delivery:
        _add("gmail.draft"); _add("gmail.send"); _add("mailer.report_send")
    if not normalized:
        if is_delivery_step:
            _add("gmail.draft"); _add("gmail.send"); _add("mailer.report_send")
        if is_research_step and not no_web_requested and not delivery_only_writing:
            _add("marketing.web_research"); _add("web.extract.structured")
            if has_explicit_url or visual_browser_requested:
                _add("browser.playwright.inspect")
        if is_writing_step and not delivery_only_writing:
            _add("report.generate")
    has_research_tool = any(tool_id in normalized for tool_id in ("marketing.web_research", "web.extract.structured", "browser.playwright.inspect"))
    if request_wants_research and not delivery_only_writing and not no_web_requested and not has_research_tool and not role_implies_writing and not role_implies_delivery:
        _add("marketing.web_research"); _add("web.extract.structured")
        if has_explicit_url or visual_browser_requested:
            _add("browser.playwright.inspect")
    if (is_research_step or research_priority) and not delivery_priority:
        blocked_delivery_tools = {"gmail.send", "mailer.report_send"} if role_implies_writing or writing_priority else {"gmail.draft", "gmail.send", "mailer.report_send"}
        normalized = [tool_id for tool_id in normalized if tool_id not in blocked_delivery_tools]
    if role_implies_writing and not role_implies_delivery:
        normalized = [tool_id for tool_id in normalized if tool_id not in {"gmail.send", "email.send", "mailer.report_send"}]
        _add("report.generate")
    if explicit_send_delivery and not research_priority:
        normalized = [tool_id for tool_id in normalized if tool_id not in {"marketing.web_research", "web.extract.structured", "browser.playwright.inspect"}]
    if role_implies_writing and not role_implies_research and not visual_browser_requested and not has_explicit_url:
        normalized = [tool_id for tool_id in normalized if tool_id not in {"marketing.web_research", "web.extract.structured", "browser.playwright.inspect"}]
    if delivery_only_writing and explicit_send_delivery and not role_implies_writing and "report.generate" in normalized:
        normalized = [tool_id for tool_id in normalized if tool_id != "report.generate"]
    if not writing_priority and not research_needs_synthesis and "report.generate" in normalized:
        normalized = [tool_id for tool_id in normalized if tool_id != "report.generate"]
    if no_web_requested:
        blocked = {"marketing.web_research", "browser.playwright.inspect", "web.extract.structured", "web.dataset.adapter", "browser.contact_form.send"}
        normalized = [tool_id for tool_id in normalized if tool_id not in blocked]
    return normalized


def _sanitize_plan(plan: dict[str, Any], *, description: str, ops: Any | None = None) -> dict[str, Any]:
    raw_steps = plan.get("steps")
    raw_edges = plan.get("edges")
    raw_connectors = plan.get("connectors_needed")
    steps: list[dict[str, Any]] = []
    seen_step_ids: set[str] = set()
    for index, candidate in enumerate(raw_steps if isinstance(raw_steps, list) else [], start=1):
        if not isinstance(candidate, dict):
            continue
        step_id = str(candidate.get("step_id") or "").strip() or f"step_{index}"
        if not re.fullmatch(r"step_\d+", step_id):
            step_id = f"step_{index}"
        while step_id in seen_step_ids:
            step_id = f"step_{len(seen_step_ids) + 1}"
        seen_step_ids.add(step_id)
        description_value = str(candidate.get("description") or "").strip() or f"Handle workflow step {index}."
        role = ops._sanitize_agent_role(raw_role=str(candidate.get("agent_role") or "").strip(), step_description=description_value, index=index)
        tools = candidate.get("tools_needed")
        tool_ids = [str(tool_id).strip() for tool_id in (tools if isinstance(tools, list) else []) if str(tool_id).strip()]
        steps.append({"step_id": step_id, "agent_role": role, "description": description_value, "tools_needed": tool_ids[:12]})
    if not steps:
        return {"steps": [], "edges": [], "connectors_needed": []}
    valid_step_ids = {str(step["step_id"]) for step in steps}
    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()
    for candidate in raw_edges if isinstance(raw_edges, list) else []:
        if isinstance(candidate, dict):
            from_step = str(candidate.get("from_step") or "").strip()
            to_step = str(candidate.get("to_step") or "").strip()
            if from_step in valid_step_ids and to_step in valid_step_ids and from_step != to_step and (from_step, to_step) not in seen_edges:
                seen_edges.add((from_step, to_step))
                edges.append({"from_step": from_step, "to_step": to_step})
    if not edges and len(steps) > 1:
        edges = [{"from_step": steps[idx]["step_id"], "to_step": steps[idx + 1]["step_id"]} for idx in range(len(steps) - 1)]
    connectors = []
    for candidate in raw_connectors if isinstance(raw_connectors, list) else []:
        if isinstance(candidate, dict):
            connector_id = str(candidate.get("connector_id") or "").strip()
            reason = str(candidate.get("reason") or "").strip()
            if connector_id:
                connectors.append({"connector_id": connector_id, "reason": reason})
    steps, edges = _ensure_research_summary_followup(
        steps=steps,
        edges=edges,
        request_description=description,
    )
    steps = _rescope_step_descriptions(steps=steps, request_description=description)
    return {"steps": steps, "edges": edges, "connectors_needed": connectors}
