from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from decouple import config
from fastapi import HTTPException

from ktem.pages.chat.common import STATE
from maia.mindmap.indexer import build_knowledge_map

from api.context import ApiContext
from api.schemas import ChatRequest

from .citations import (
    assign_fast_source_refs,
    build_citation_quality_metrics,
    build_claim_signal_summary,
    build_source_usage,
    build_fast_info_html,
    enforce_required_citations,
    normalize_fast_answer,
    render_fast_citation_links,
    resolve_required_citation_mode,
)
from .constants import (
    API_FAST_QA_MAX_IMAGES,
    API_FAST_QA_MAX_SNIPPETS,
    API_FAST_QA_MAX_SOURCES,
    API_FAST_QA_SOURCE_SCAN,
    API_FAST_QA_TEMPERATURE,
    MAIA_CITATION_STRENGTH_ORDERING_ENABLED,
    MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD,
    MAIA_SOURCE_USAGE_HEATMAP_ENABLED,
    DEFAULT_SETTING,
)
from .conversation_store import (
    build_selected_payload,
    get_or_create_conversation,
    maybe_autoname_conversation,
    persist_conversation,
)
from .fast_qa_retrieval import load_recent_chunks_for_fast_qa
from .info_panel_copy import build_info_panel_copy
from .pipeline import is_placeholder_api_key


def _extract_text_content(raw_content: Any) -> str:
    if isinstance(raw_content, str):
        return raw_content.strip()
    if not isinstance(raw_content, list):
        return ""
    parts: list[str] = []
    for item in raw_content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text_value = str(item.get("text") or "").strip()
        if text_value:
            parts.append(text_value)
    return "\n".join(parts).strip()


def _call_openai_chat_text(
    *,
    api_key: str,
    base_url: str,
    request_payload: dict[str, Any],
    timeout_seconds: int = 20,
) -> str | None:
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(request_payload).encode("utf-8"),
    )
    with urlopen(request, timeout=max(8, int(timeout_seconds))) as response:
        payload = json.loads(response.read().decode("utf-8"))
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if not isinstance(message, dict):
        return None
    return _extract_text_content(message.get("content")) or None


def _parse_json_object(raw_text: str) -> dict[str, Any] | None:
    text = str(raw_text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _normalize_outline(raw_outline: dict[str, Any] | None) -> dict[str, Any]:
    fallback = {
        "style": "adaptive-detailed",
        "detail_level": "high",
        "sections": [
            {
                "title": "Answer",
                "goal": "Respond directly with evidence-grounded detail.",
                "format": "mixed",
            }
        ],
        "tone": "professional",
    }
    if not isinstance(raw_outline, dict):
        return fallback

    style = " ".join(str(raw_outline.get("style") or "").split()).strip()[:80] or fallback["style"]
    detail_level = (
        " ".join(str(raw_outline.get("detail_level") or "").split()).strip()[:40] or fallback["detail_level"]
    )
    tone = " ".join(str(raw_outline.get("tone") or "").split()).strip()[:40] or fallback["tone"]
    sections_raw = raw_outline.get("sections")
    sections: list[dict[str, str]] = []
    if isinstance(sections_raw, list):
        for row in sections_raw[:6]:
            if not isinstance(row, dict):
                continue
            title = " ".join(str(row.get("title") or "").split()).strip()[:120]
            goal = " ".join(str(row.get("goal") or "").split()).strip()[:220]
            fmt = " ".join(str(row.get("format") or "").split()).strip()[:40]
            if not title and not goal:
                continue
            sections.append(
                {
                    "title": title or "Section",
                    "goal": goal or "Explain relevant evidence-backed details.",
                    "format": fmt or "paragraphs",
                }
            )
    if not sections:
        sections = fallback["sections"]

    return {
        "style": style,
        "detail_level": detail_level,
        "sections": sections,
        "tone": tone,
    }


def _apply_mindmap_focus(
    snippets: list[dict[str, Any]],
    focus: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    payload = dict(focus or {})
    if not payload or not snippets:
        return snippets

    focus_source_id = str(payload.get("source_id", "") or "").strip()
    focus_source_name = str(payload.get("source_name", "") or "").strip().lower()
    focus_page = str(payload.get("page_ref") or payload.get("page_label") or "").strip()
    focus_unit_id = str(payload.get("unit_id", "") or "").strip()
    focus_text = str(payload.get("text", "") or "").strip().lower()

    filtered = snippets
    if focus_source_id:
        filtered = [
            row
            for row in filtered
            if str(row.get("source_id", "") or "").strip() == focus_source_id
        ]
    elif focus_source_name:
        filtered = [
            row
            for row in filtered
            if focus_source_name in str(row.get("source_name", "") or "").strip().lower()
        ]
    if focus_page:
        page_filtered = [
            row for row in filtered if str(row.get("page_label", "") or "").strip() == focus_page
        ]
        if page_filtered:
            filtered = page_filtered
    if focus_unit_id:
        unit_filtered = [
            row for row in filtered if str(row.get("unit_id", "") or "").strip() == focus_unit_id
        ]
        if unit_filtered:
            filtered = unit_filtered

    if focus_text and filtered:
        focus_terms = {
            token
            for token in re.findall(r"[a-z0-9]{3,}", focus_text)
            if len(token) >= 3
        }

        def overlap_score(row: dict[str, Any]) -> int:
            text = str(row.get("text", "") or "").lower()
            return sum(1 for term in focus_terms if term in text)

        ranked = sorted(filtered, key=overlap_score, reverse=True)
        if overlap_score(ranked[0]) > 0:
            filtered = ranked[: max(4, min(10, len(ranked)))]

    return filtered or snippets


def _plan_adaptive_outline(
    *,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float,
    question: str,
    history_text: str,
    refs_text: str,
    context_text: str,
) -> dict[str, Any]:
    planner_prompt = (
        "Create an answer blueprint for a retrieval-grounded assistant reply.\n"
        "Return one JSON object only with keys:\n"
        '{ "style": "string", "detail_level": "high", "sections": [{"title":"string","goal":"string","format":"paragraphs|bullets|table|mixed"}], "tone": "string" }\n'
        "Rules:\n"
        "- Structure must be specific to this exact user request and evidence, not a generic reusable template.\n"
        "- Keep the final answer detailed.\n"
        "- Use 2-6 sections.\n"
        "- Section titles must be specific, professional, and tied to concrete entities in the request/evidence.\n"
        "- Do not default to reusable company-profile or marketing-report skeletons unless explicitly requested.\n"
        "- If user intent is unclear/noisy, produce one section focused on a clarifying question instead of assumptions.\n"
        "- Do not invent facts.\n\n"
        f"Question:\n{question}\n\n"
        f"Recent chat history:\n{history_text}\n\n"
        f"Source index:\n{refs_text or '(none)'}\n\n"
        f"Evidence excerpt (truncated):\n{context_text[:6000]}"
    )
    planner_payload = {
        "model": model,
        "temperature": max(0.0, min(1.0, float(temperature) * 0.5)),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You design response structures for professional assistants. "
                    "Return JSON only."
                ),
            },
            {"role": "user", "content": planner_prompt},
        ],
    }
    try:
        planned_raw = _call_openai_chat_text(
            api_key=api_key,
            base_url=base_url,
            request_payload=planner_payload,
            timeout_seconds=16,
        )
        return _normalize_outline(_parse_json_object(str(planned_raw or "")))
    except Exception:
        return _normalize_outline(None)


def call_openai_fast_qa(
    question: str,
    snippets: list[dict[str, Any]],
    chat_history: list[list[str]],
    refs: list[dict[str, Any]],
    citation_mode: str | None,
) -> str | None:
    api_key = str(config("OPENAI_API_KEY", default="") or "").strip()
    if is_placeholder_api_key(api_key):
        return None

    base_url = str(config("OPENAI_API_BASE", default="https://api.openai.com/v1")) or "https://api.openai.com/v1"
    model = str(config("OPENAI_CHAT_MODEL", default="gpt-4o-mini")) or "gpt-4o-mini"

    context_blocks = []
    for snippet in snippets[:API_FAST_QA_MAX_SNIPPETS]:
        source_name = str(snippet.get("source_name", "Indexed file"))
        page_label = str(snippet.get("page_label", "") or "").strip()
        text = str(snippet.get("text", "") or "").strip()
        doc_type = str(snippet.get("doc_type", "") or "").strip()
        ref_id = int(snippet.get("ref_id", 0) or 0)
        header_parts = [f"Ref: [{ref_id}] Source: {source_name}"]
        if page_label:
            header_parts.append(f"Page: {page_label}")
        if doc_type:
            header_parts.append(f"Type: {doc_type}")
        context_blocks.append(f"{' | '.join(header_parts)}\nExcerpt: {text}")

    visual_evidence: list[tuple[str, str, str, int]] = []
    seen_images: set[str] = set()
    for snippet in snippets:
        source_name = str(snippet.get("source_name", "Indexed file"))
        page_label = str(snippet.get("page_label", "") or "")
        ref_id = int(snippet.get("ref_id", 0) or 0)
        image_origin = snippet.get("image_origin")
        if not isinstance(image_origin, str) or not image_origin.startswith("data:image/"):
            continue
        if image_origin in seen_images:
            continue
        seen_images.add(image_origin)
        visual_evidence.append((source_name, page_label, image_origin, ref_id))
        if len(visual_evidence) >= max(0, API_FAST_QA_MAX_IMAGES):
            break
    history_blocks = []
    for turn in chat_history[-3:]:
        if not isinstance(turn, list) or len(turn) < 2:
            continue
        history_blocks.append(f"User: {turn[0]}\nAssistant: {turn[1]}")

    history_text = "\n\n".join(history_blocks) if history_blocks else "(none)"
    context_text = "\n\n".join(context_blocks)
    refs_text = "\n".join([f"[{ref['id']}] {ref['label']}" for ref in refs[: min(len(refs), 20)]])
    mode = resolve_required_citation_mode(citation_mode)
    if mode == "footnote":
        citation_instruction = (
            "Keep the main paragraphs citation-free, then add a final 'Sources' section "
            "with refs in square brackets (for example [1], [2]) tied to the key claims."
        )
    else:
        citation_instruction = (
            "Cite factual claims with source refs in square brackets like [1], [2]. "
            "Every major claim should have at least one citation. "
            "Use the most specific ref excerpt that directly supports each cited claim. "
            "Number refs sequentially starting at [1] and reuse the same ref number when citing the same evidence."
        )
    temperature = max(0.0, min(1.0, float(API_FAST_QA_TEMPERATURE)))
    outline = _plan_adaptive_outline(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        question=question,
        history_text=history_text,
        refs_text=refs_text,
        context_text=context_text,
    )
    output_instruction = (
        "Output format rules:\n"
        "- Follow the provided response blueprint while adapting when evidence is missing.\n"
        "- Keep the answer detailed, specific, and professional.\n"
        "- Use natural prose by default; use headings, bullets, or tables only when they improve clarity.\n"
        "- Keep section titles specific to the request domain; avoid generic reusable labels and reusable report skeletons.\n"
        "- If intent is unclear, ask one focused clarifying question and avoid speculative summaries.\n"
        "- Distinguish confirmed facts from inference when confidence is limited.\n"
        "- If information is missing, say: Not visible in indexed content.\n"
        "- Use clean markdown and avoid malformed formatting."
    )
    prompt = (
        "Use the provided indexed context to answer the user question in detail. "
        "When multiple sources are relevant, synthesize across them and call out agreements or differences. "
        "When a question asks what a PDF/image is about, adapt the structure to the document type and available evidence instead of a fixed template. "
        "If visual evidence is provided, use it to improve detail while clearly signaling assumptions. "
        f"{citation_instruction}\n\n"
        f"Response blueprint (generated by Maia planner):\n{json.dumps(outline, ensure_ascii=True)}\n\n"
        f"{output_instruction}\n\n"
        f"Source index:\n{refs_text or '(none)'}\n\n"
        f"Recent chat history:\n{history_text}\n\n"
        f"Indexed context:\n{context_text}\n\n"
        f"Question: {question}"
    )
    user_content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for source_name, page_label, image_origin, ref_id in visual_evidence:
        label = f"Visual evidence [{ref_id}] from {source_name}"
        if page_label:
            label += f" (page {page_label})"
        user_content.append({"type": "text", "text": label})
        user_content.append({"type": "image_url", "image_url": {"url": image_origin}})

    try:
        request_payload = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Maia. Provide faithful, high-detail answers from indexed evidence. "
                        "Adapt structure to the user's question and evidence; do not force fixed section templates. "
                        "Use concise sections and bullet points only when useful."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
        }
        answer = str(
            _call_openai_chat_text(
                api_key=api_key,
                base_url=base_url,
                request_payload=request_payload,
                timeout_seconds=20,
            )
            or ""
        ).strip()
        return answer or None
    except HTTPError:
        return None
    except Exception:
        return None


def run_fast_chat_turn(
    context: ApiContext,
    user_id: str,
    request: ChatRequest,
) -> dict[str, Any] | None:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is empty.")
    if request.command not in (None, "", DEFAULT_SETTING):
        return None

    conversation_id, conversation_name, data_source = get_or_create_conversation(
        user_id=user_id,
        conversation_id=request.conversation_id,
    )
    conversation_name = maybe_autoname_conversation(
        user_id=user_id,
        conversation_id=conversation_id,
        current_name=conversation_name,
        message=message,
        agent_mode=request.agent_mode,
    )
    chat_history = deepcopy(data_source.get("messages", []))
    chat_state = deepcopy(data_source.get("state", STATE))

    selected_payload = build_selected_payload(
        context=context,
        user_id=user_id,
        existing_selected=data_source.get("selected", {}),
        requested_selected=request.index_selection,
    )

    snippets = load_recent_chunks_for_fast_qa(
        context=context,
        user_id=user_id,
        selected_payload=selected_payload,
        query=message,
        max_sources=max(API_FAST_QA_SOURCE_SCAN, API_FAST_QA_MAX_SOURCES),
        max_chunks=max(10, API_FAST_QA_MAX_SNIPPETS),
    )
    if not snippets:
        return None
    snippets = _apply_mindmap_focus(
        snippets,
        request.mindmap_focus if isinstance(request.mindmap_focus, dict) else {},
    )

    snippets_with_refs, refs = assign_fast_source_refs(snippets)
    answer = call_openai_fast_qa(
        question=message,
        snippets=snippets_with_refs,
        chat_history=chat_history,
        refs=refs,
        citation_mode=request.citation,
    )
    if not answer:
        return None
    answer = normalize_fast_answer(answer)
    resolved_citation_mode = resolve_required_citation_mode(request.citation)
    answer = render_fast_citation_links(
        answer=answer,
        refs=refs,
        citation_mode=resolved_citation_mode,
    )
    info_text = build_fast_info_html(snippets_with_refs, max_blocks=6)
    answer = enforce_required_citations(
        answer=answer,
        info_html=info_text,
        citation_mode=resolved_citation_mode,
    )
    source_usage = build_source_usage(
        snippets_with_refs=snippets_with_refs,
        refs=refs,
        answer_text=answer,
        enabled=MAIA_SOURCE_USAGE_HEATMAP_ENABLED,
    )
    claim_signal_summary = build_claim_signal_summary(
        answer_text=answer,
        refs=refs,
    )
    citation_quality_metrics = build_citation_quality_metrics(
        snippets_with_refs=snippets_with_refs,
        refs=refs,
        answer_text=answer,
    )
    max_citation_share = max(
        (float(item.get("citation_share", 0.0) or 0.0) for item in source_usage),
        default=0.0,
    )
    source_dominance_detected = bool(
        source_usage and max_citation_share > float(MAIA_CITATION_DOMINANCE_WARNING_THRESHOLD)
    )
    source_dominance_warning = (
        "This answer depends heavily on one source; consider reviewing other documents for broader context."
        if source_dominance_detected
        else ""
    )
    info_panel = build_info_panel_copy(
        request_message=message,
        answer_text=answer,
        info_html=info_text,
        mode="ask",
        next_steps=[],
        web_summary={},
    )
    mindmap_payload: dict[str, Any] = {}
    if bool(request.use_mindmap):
        map_settings = dict(request.mindmap_settings or {})
        try:
            map_depth = int(map_settings.get("max_depth", 4))
        except Exception:
            map_depth = 4
        map_type = str(map_settings.get("map_type", "structure") or "structure").strip().lower()
        if map_type not in {"structure", "evidence"}:
            map_type = "structure"
        mindmap_payload = build_knowledge_map(
            question=message,
            context="\n\n".join(str(row.get("text", "") or "") for row in snippets[:8]),
            documents=snippets,
            answer_text=answer,
            max_depth=max(2, min(8, map_depth)),
            include_reasoning_map=bool(map_settings.get("include_reasoning_map", True)),
            source_type_hint=str(map_settings.get("source_type_hint", "") or ""),
            focus=request.mindmap_focus if isinstance(request.mindmap_focus, dict) else {},
            map_type=map_type,
        )
        info_panel["mindmap"] = mindmap_payload
    if source_usage:
        info_panel["source_usage"] = source_usage
    if claim_signal_summary:
        info_panel["claim_signal_summary"] = claim_signal_summary
    if citation_quality_metrics:
        info_panel["citation_quality_metrics"] = citation_quality_metrics
    if source_dominance_warning:
        info_panel["source_dominance_warning"] = source_dominance_warning
    info_panel["citation_strength_ordering"] = bool(MAIA_CITATION_STRENGTH_ORDERING_ENABLED)
    info_panel["citation_strength_legend"] = (
        "Citation numbers are normalized per answer: each source appears once and numbering starts at 1."
    )

    messages = chat_history + [[message, answer]]
    retrieval_history = deepcopy(data_source.get("retrieval_messages", []))
    retrieval_history.append(info_text)
    plot_history = deepcopy(data_source.get("plot_history", []))
    plot_history.append(None)
    message_meta = deepcopy(data_source.get("message_meta", []))
    message_meta.append(
        {
            "mode": "ask",
            "activity_run_id": None,
            "actions_taken": [],
            "sources_used": [],
            "source_usage": source_usage,
            "claim_signal_summary": claim_signal_summary,
            "citation_quality_metrics": citation_quality_metrics,
            "next_recommended_steps": [],
            "info_panel": info_panel,
            "mindmap": mindmap_payload,
        }
    )

    conversation_payload = {
        "selected": selected_payload,
        "messages": messages,
        "retrieval_messages": retrieval_history,
        "plot_history": plot_history,
        "message_meta": message_meta,
        "state": chat_state,
        "likes": deepcopy(data_source.get("likes", [])),
    }
    persist_conversation(conversation_id, conversation_payload)

    return {
        "conversation_id": conversation_id,
        "conversation_name": conversation_name,
        "message": message,
        "answer": answer,
        "info": info_text,
        "plot": None,
        "state": chat_state,
        "mode": "ask",
        "actions_taken": [],
        "sources_used": [],
        "source_usage": source_usage,
        "claim_signal_summary": claim_signal_summary,
        "citation_quality_metrics": citation_quality_metrics,
        "next_recommended_steps": [],
        "activity_run_id": None,
        "info_panel": info_panel,
        "mindmap": mindmap_payload,
    }
