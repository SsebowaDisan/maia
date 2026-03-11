from __future__ import annotations

import json
from typing import Any

from urllib.error import HTTPError


def call_openai_fast_qa_impl(
    *,
    question: str,
    snippets: list[dict[str, Any]],
    chat_history: list[list[str]],
    refs: list[dict[str, Any]],
    citation_mode: str | None,
    primary_source_note: str,
    requested_language: str | None,
    allow_general_knowledge: bool,
    logger,
    resolve_fast_qa_llm_config_fn,
    truncate_for_log_fn,
    is_placeholder_api_key_fn,
    resolve_required_citation_mode_fn,
    build_response_language_rule_fn,
    plan_adaptive_outline_fn,
    call_openai_chat_text_fn,
    API_FAST_QA_MAX_SNIPPETS: int,
    API_FAST_QA_MAX_IMAGES: int,
    API_FAST_QA_TEMPERATURE: float,
) -> str | None:
    api_key, base_url, model, config_source = resolve_fast_qa_llm_config_fn()
    logger.warning(
        "fast_qa_llm_config source=%s model=%s base=%s key_present=%s",
        config_source,
        model,
        base_url,
        bool(api_key),
    )
    if is_placeholder_api_key_fn(api_key):
        logger.warning(
            "fast_qa_disabled reason=missing_openai_key source=%s question=%s",
            config_source,
            truncate_for_log_fn(question, 220),
        )
        return None

    context_blocks = []
    for snippet in snippets[:API_FAST_QA_MAX_SNIPPETS]:
        source_name = str(snippet.get("source_name", "Indexed file"))
        page_label = str(snippet.get("page_label", "") or "").strip()
        text = str(snippet.get("text", "") or "").strip()
        doc_type = str(snippet.get("doc_type", "") or "").strip()
        ref_id = int(snippet.get("ref_id", 0) or 0)
        is_primary = bool(snippet.get("is_primary_source"))
        header_parts = [f"Ref: [{ref_id}] Source: {source_name}"]
        if page_label:
            header_parts.append(f"Page: {page_label}")
        if doc_type:
            header_parts.append(f"Type: {doc_type}")
        if is_primary:
            header_parts.append("Priority: primary")
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
    general_knowledge_mode = bool(allow_general_knowledge and not context_blocks)
    mode = resolve_required_citation_mode_fn(citation_mode)

    if general_knowledge_mode:
        citation_instruction = (
            "No indexed source refs are available for this turn. "
            "Do not fabricate citations or source links."
        )
    elif mode == "footnote":
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
    outline = plan_adaptive_outline_fn(
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
        "- Keep the answer directly relevant to the user's question.\n"
        "- Open with a direct, substantive answer — state the key finding or conclusion clearly and specifically.\n"
        "- For every section, develop the content fully: include specific data points, statistics, concrete examples, "
        "mechanisms, comparisons, and implications. Do not leave sections at surface level.\n"
        "- For research or analytical questions, provide rich multi-section depth with 3-5 substantial paragraphs per "
        "major section — explore causes, evidence, context, trade-offs, and significance.\n"
        "- Each section must develop its content with at least 2-3 full paragraphs of substantive prose — "
        "a single sentence or a bare bullet list is not sufficient for any analytical or research section.\n"
        "- Surface every relevant fact, figure, name, date, product, or measurement from the evidence — "
        "do not leave important details out of the response or paraphrase precise values into vague terms.\n"
        "- When the evidence contains specific company names, products, percentages, financial figures, or direct "
        "quotes, reproduce them precisely in the answer — do not generalise or omit them.\n"
        "- When evidence provides context around a claim (causes, history, consequences, comparisons), include "
        "that context in the section rather than stating only the headline finding.\n"
        "- Write the complete response — do not stop early, trail off, or skip sections from the blueprint; "
        "every section listed in the blueprint must appear with full content in the output.\n"
        "- For direct factual questions, give a precise answer with enough supporting detail to be genuinely useful.\n"
        "- Choose structure per query (narrative paragraphs, headed sections, bullets, or tables); do not reuse a single fixed layout across responses.\n"
        "- Use natural prose by default; use headings, bullets, or tables only when they add genuine clarity.\n"
        "- When a table or bullet list is used, precede it with at least one explanatory paragraph that contextualises the data.\n"
        "- When data or numbers are available, surface them explicitly — do not bury or omit statistics.\n"
        "- When multiple sources agree or disagree, call it out explicitly with specifics.\n"
        "- Do not lead with isolated quoted fragments or decorative callouts unless the user explicitly asks.\n"
        "- Prefer complete sentences and coherent paragraphs over stylized snippets.\n"
        "- Keep section titles specific to the request domain; avoid generic reusable labels.\n"
        "- Avoid promotional tone, filler, and repetitive phrasing.\n"
        "- Keep tone precise and authoritative; write with the depth expected of a senior analyst briefing an executive.\n"
        "- Do not include internal runtime sections such as Delivery Status, Contract Gate, Verification checks, or tool-failure logs.\n"
        "- Avoid unsupported inference; do not use 'typically', 'may', or similar hedging unless evidence explicitly indicates uncertainty.\n"
        "- For entity/detail lookup questions, provide exact fields from evidence instead of generic summaries.\n"
        "- When adding website links, avoid placeholder anchor text like 'here'; use meaningful link text.\n"
        "- If intent is unclear, ask one focused clarifying question and avoid speculative summaries.\n"
        "- Distinguish confirmed facts from inference when confidence is limited.\n"
        + (
            "- If indexed evidence is unavailable, answer from general knowledge and explicitly mark uncertainty when needed.\n"
            if general_knowledge_mode
            else "- If information is missing, say: Not visible in indexed content.\n"
        )
        + f"- {build_response_language_rule_fn(requested_language=requested_language, latest_message=question)}\n"
        "- Use clean markdown and avoid malformed formatting."
    )

    if general_knowledge_mode:
        prompt = (
            "No indexed evidence matched this request. "
            "Answer the user question directly from reliable general knowledge. "
            "Be thorough, specific, and substantive — include statistics, mechanisms, examples, and expert context where relevant. "
            "Be explicit about uncertainty where relevant. "
            "Do not invent citations, documents, or source URLs. "
            f"{citation_instruction}\n\n"
            f"Response blueprint (generated by Maia planner):\n{json.dumps(outline, ensure_ascii=True)}\n\n"
            f"{output_instruction}\n\n"
            f"Recent chat history:\n{history_text}\n\n"
            f"Question: {question}"
        )
    else:
        prompt = (
            "Use the provided indexed context to answer the user question. "
            "When multiple sources are relevant, synthesize across them and call out agreements or differences. "
            "When a question asks what a PDF/image is about, adapt the structure to the document type and available evidence instead of a fixed template. "
            "If visual evidence is provided, use it to improve detail while clearly signaling assumptions. "
            "If a primary source target is present, prioritize that source in the answer and keep other sources secondary. "
            f"{citation_instruction}\n\n"
            f"Primary source guidance:\n{primary_source_note or '(none)'}\n\n"
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
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        (
                            "You are Maia, a research-grade AI assistant. Use indexed evidence when available; when it is unavailable, answer from reliable general knowledge. "
                            "Never invent citations or pretend to have source evidence when none is provided. "
                            "Adapt structure to the question — simple lookups get a direct answer, analytical or research questions get deep, well-developed multi-section responses with specific data, examples, and expert-level context. "
                            "Write with the depth and precision of a senior analyst briefing a decision-maker: go beyond surface summaries, surface key numbers, explain mechanisms, and address implications. "
                            "For general knowledge questions, provide comprehensive, textbook-level depth — include mechanisms, historical context, statistics, examples, and expert-level nuance. "
                            "Never truncate a response mid-thought; complete every section fully before ending. "
                        )
                        if general_knowledge_mode
                        else (
                            "You are Maia, a research-grade AI assistant. Provide faithful answers grounded in indexed evidence. "
                            "Treat the indexed evidence as a primary source — read every excerpt carefully and surface all specific details, figures, names, and dates, not just headlines. "
                            "Adapt structure and depth to the question — analytical and research questions deserve rich, multi-section responses with specific data, comparisons, mechanisms, and implications drawn from the evidence. "
                            "Go beyond surface summaries: surface exact numbers, highlight agreements and contradictions across sources, and develop each section with substantive detail that would satisfy a domain expert. "
                            "Write with the depth and precision of a senior analyst briefing a decision-maker. "
                            "Never truncate a response mid-thought; complete every section fully before ending. "
                        )
                        + f"{build_response_language_rule_fn(requested_language=requested_language, latest_message=question)} "
                        + (
                            "Do not invent facts; acknowledge uncertainty when needed."
                            if general_knowledge_mode
                            else "Do not infer details that are not explicitly supported by evidence."
                        )
                    ),
                },
                {"role": "user", "content": user_content},
            ],
        }
        answer = str(
            call_openai_chat_text_fn(
                api_key=api_key,
                base_url=base_url,
                request_payload=request_payload,
                timeout_seconds=45,
            )
            or ""
        ).strip()
        if not answer:
            logger.warning(
                "fast_qa_empty_answer model=%s question=%s",
                model,
                truncate_for_log_fn(question, 220),
            )
        return answer or None
    except HTTPError as exc:
        logger.warning(
            "fast_qa_http_error model=%s question=%s error=%s",
            model,
            truncate_for_log_fn(question, 220),
            truncate_for_log_fn(exc, 280),
        )
        return None
    except Exception:
        logger.exception(
            "fast_qa_call_failed model=%s question=%s",
            model,
            truncate_for_log_fn(question, 220),
        )
        return None
