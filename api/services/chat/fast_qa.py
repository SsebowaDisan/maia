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

from api.context import ApiContext
from api.schemas import ChatRequest

from .citations import (
    assign_fast_source_refs,
    build_fast_info_html,
    normalize_fast_answer,
    render_fast_citation_links,
)
from .constants import (
    API_FAST_QA_MAX_IMAGES,
    API_FAST_QA_MAX_SNIPPETS,
    API_FAST_QA_MAX_SOURCES,
    API_FAST_QA_SOURCE_SCAN,
    API_FAST_QA_TEMPERATURE,
    DEFAULT_SETTING,
)
from .conversation_store import (
    build_selected_payload,
    get_or_create_conversation,
    persist_conversation,
)
from .fast_qa_retrieval import load_recent_chunks_for_fast_qa
from .pipeline import is_placeholder_api_key


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
    overview_intent = bool(
        re.search(
            r"\b(what\s+is\s+this\s+(pdf|document)\s+about|what'?s\s+this\s+(pdf|document)\s+about|summary|summarize|overview)\b",
            question.lower(),
        )
    )
    mode = (citation_mode or "").strip().lower()
    if mode == "off":
        citation_instruction = "Citations are disabled for this response."
    elif mode == "footnote":
        citation_instruction = (
            "Keep the main paragraphs citation-free, then add a final 'Sources' section "
            "with refs in square brackets (for example [1], [2]) tied to the key claims."
        )
    else:
        citation_instruction = (
            "Cite factual claims with source refs in square brackets like [1], [2]. "
            "Every major claim should have at least one citation."
        )
    if overview_intent:
        output_instruction = (
            "Output format rules:\n"
            "- Start with a direct 1-2 sentence summary.\n"
            "- Choose the most useful structure for this question (short paragraphs, bullets, or a compact table).\n"
            "- Vary phrasing and headings naturally; do not force a repeated section template.\n"
            "- For transactional documents (receipt/invoice/statement), extract explicit fields first, then add a brief interpretation.\n"
            "- Distinguish confirmed facts from inference when confidence is limited.\n"
            "- If data is missing, say: Not visible in indexed content.\n"
            "- Use clean markdown and avoid malformed formatting."
        )
    else:
        output_instruction = (
            "Output format rules:\n"
            "- Answer directly in a concise professional style.\n"
            "- Use headings/bullets only when they improve clarity.\n"
            "- Avoid repeated template phrasing across turns.\n"
            "- Use clean markdown and avoid malformed formatting."
        )
    prompt = (
        "Use the provided indexed context to answer the user question in detail. "
        "When multiple sources are relevant, synthesize across them and call out agreements or differences. "
        "When a question asks what a PDF/image is about, adapt the structure to the document type and available evidence instead of a fixed template. "
        "If visual evidence is provided, use it to improve detail while clearly signaling assumptions. "
        f"{citation_instruction}\n\n"
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

    temperature = max(0.0, min(1.0, float(API_FAST_QA_TEMPERATURE)))

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
        request = Request(
            f"{base_url.rstrip('/')}/chat/completions",
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(request_payload).encode("utf-8"),
        )
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        raw_answer = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        if isinstance(raw_answer, list):
            answer_parts = []
            for part in raw_answer:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text" and part.get("text"):
                    answer_parts.append(str(part.get("text")))
            answer = "\n".join(answer_parts).strip()
        else:
            answer = str(raw_answer or "").strip()
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
    answer = render_fast_citation_links(
        answer=answer,
        refs=refs,
        citation_mode=request.citation,
    )
    info_text = build_fast_info_html(snippets_with_refs, max_blocks=6)

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
            "next_recommended_steps": [],
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
        "next_recommended_steps": [],
        "activity_run_id": None,
    }
