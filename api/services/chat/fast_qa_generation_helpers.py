from __future__ import annotations

import hashlib
import json
import os
from collections import OrderedDict
from typing import Any

from urllib.error import HTTPError


_FAST_QA_RESPONSE_CACHE: "OrderedDict[str, str]" = OrderedDict()


def _cache_limit() -> int:
    raw = str(os.getenv("MAIA_FAST_QA_RESPONSE_CACHE_SIZE", "") or "").strip()
    try:
        value = int(raw) if raw else 64
    except Exception:
        value = 64
    return max(0, min(value, 512))


def _snippet_cache_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ref_id": int(row.get("ref_id", 0) or 0),
        "source_id": str(row.get("source_id", "") or "").strip(),
        "source_name": str(row.get("source_name", "") or "").strip(),
        "page_label": str(row.get("page_label", "") or "").strip(),
        "text": " ".join(str(row.get("text", "") or "").split())[:900],
    }


def _build_fast_qa_cache_key(
    *,
    question: str,
    snippets: list[dict[str, Any]],
    refs: list[dict[str, Any]],
    citation_mode: str | None,
    primary_source_note: str,
    requested_language: str | None,
    allow_general_knowledge: bool,
    is_follow_up: bool,
    base_url: str,
    model: str,
) -> str:
    payload = {
        "question": " ".join(str(question or "").split()),
        "snippets": [_snippet_cache_projection(row) for row in snippets[:12]],
        "refs": [
            {
                "id": int(ref.get("id", 0) or 0),
                "label": str(ref.get("label", "") or "").strip(),
            }
            for ref in refs[:20]
            if isinstance(ref, dict)
        ],
        "citation_mode": str(citation_mode or "").strip(),
        "primary_source_note": " ".join(str(primary_source_note or "").split())[:240],
        "requested_language": str(requested_language or "").strip(),
        "allow_general_knowledge": bool(allow_general_knowledge),
        "is_follow_up": bool(is_follow_up),
        "base_url": str(base_url or "").strip().lower(),
        "model": str(model or "").strip(),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> str | None:
    cached = _FAST_QA_RESPONSE_CACHE.get(key)
    if cached is None:
        return None
    _FAST_QA_RESPONSE_CACHE.move_to_end(key)
    return cached


def _cache_put(key: str, value: str) -> None:
    limit = _cache_limit()
    if limit <= 0:
        return
    _FAST_QA_RESPONSE_CACHE[key] = value
    _FAST_QA_RESPONSE_CACHE.move_to_end(key)
    while len(_FAST_QA_RESPONSE_CACHE) > limit:
        _FAST_QA_RESPONSE_CACHE.popitem(last=False)


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
    is_follow_up: bool = False,
    all_project_sources: list[str] | None = None,
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
    infer_provider_label_fn=None,
) -> str | None:
    api_key, base_url, model, config_source = resolve_fast_qa_llm_config_fn()
    provider_label = (
        infer_provider_label_fn(base_url=base_url, model=model)
        if callable(infer_provider_label_fn)
        else "openai-compatible"
    )
    logger.warning(
        "fast_qa_llm_config source=%s provider=%s model=%s base=%s key_present=%s",
        config_source,
        provider_label,
        model,
        base_url,
        bool(api_key),
    )
    if is_placeholder_api_key_fn(api_key):
        logger.warning(
            "fast_qa_disabled reason=missing_openai_compatible_key source=%s provider=%s question=%s",
            config_source,
            provider_label,
            truncate_for_log_fn(question, 220),
        )
        return None

    cache_key = _build_fast_qa_cache_key(
        question=question,
        snippets=snippets,
        refs=refs,
        citation_mode=citation_mode,
        primary_source_note=primary_source_note,
        requested_language=requested_language,
        allow_general_knowledge=allow_general_knowledge,
        is_follow_up=is_follow_up,
        base_url=base_url,
        model=model,
    )
    cached_answer = _cache_get(cache_key)
    if cached_answer:
        logger.warning(
            "fast_qa_cache_hit model=%s provider=%s question=%s",
            model,
            provider_label,
            truncate_for_log_fn(question, 220),
        )
        return cached_answer

    context_blocks = []
    context_snippet_limit = min(
        API_FAST_QA_MAX_SNIPPETS,
        6 if provider_label not in {"openai", "azure-openai"} else API_FAST_QA_MAX_SNIPPETS,
    )
    for snippet in snippets[:context_snippet_limit]:
        source_name = str(snippet.get("source_name", "Indexed file"))
        page_label = str(snippet.get("page_label", "") or "").strip()
        text = str(snippet.get("text", "") or "").strip()[:700]
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

    general_knowledge_mode = bool(allow_general_knowledge and not context_blocks)
    history_blocks = []
    # Only include conversation history when the question is a confirmed follow-up.
    # For independent questions, suppress history so prior conversations don't leak
    # into unrelated answers. The LLM is still aware context exists but won't use it.
    if is_follow_up:
        for turn in chat_history[-3:]:
            if not isinstance(turn, list) or len(turn) < 2:
                continue
            user_turn = str(turn[0] or "").strip()
            assistant_turn = str(turn[1] or "").strip()
            if not user_turn:
                continue
            if general_knowledge_mode:
                history_blocks.append(f"User: {user_turn}\nAssistant: {assistant_turn}")
            else:
                # For evidence-grounded follow-ups, prior assistant answers are not
                # reliable evidence and can self-reinforce hallucinated details.
                # Keep only the user's previous questions to preserve referents
                # like "this system" without leaking model-written prose back in.
                history_blocks.append(f"User: {user_turn}")

    history_text = "\n\n".join(history_blocks) if history_blocks else "(none)"
    context_text = "\n\n".join(context_blocks)
    refs_text = "\n".join([f"[{ref['id']}] {ref['label']}" for ref in refs[: min(len(refs), 20)]])
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
            "Number refs sequentially starting at [1] and reuse the same ref number when citing the same evidence. "
            "When different claims are supported by different refs, use those different ref numbers instead of repeating [1] everywhere."
        )

    temperature = max(0.0, min(1.0, float(API_FAST_QA_TEMPERATURE)))
    use_planner = not (
        len(refs) >= 6
        or len(context_text) >= 2400
        or provider_label not in {"openai", "azure-openai"}
    )
    if use_planner:
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
    else:
        outline = {
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
        logger.warning(
            "fast_qa_planner_skipped provider=%s refs=%d context_chars=%d question=%s",
            provider_label,
            len(refs),
            len(context_text),
            truncate_for_log_fn(question, 220),
        )

    output_instruction = (
        "Output format rules:\n"
        "- Follow the provided response blueprint while adapting when evidence is missing.\n"
        "- Keep the answer directly relevant to the user's question.\n"
        "- LEAD WITH THE ANSWER: the very first sentence must state the direct answer, conclusion, or key finding — "
        "NEVER open with 'Based on...', 'It is important to note...', 'I will...', 'Certainly!', 'Great question!', "
        "'As an AI...', 'Thank you for asking...', or any meta-commentary about what you are about to say.\n"
        "- CRITICAL: Every section must contain real, developed prose content — never a single bullet that merely "
        "says 'Reviewed source: [URL]' or 'See [URL]' or lists a link with no analysis. A section heading "
        "followed by only a URL or a one-line reference is a stub and is unacceptable.\n"
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
        "- If multiple indexed PDFs or files are in the selected scope, reconcile the answer across that full selected set before concluding; do not anchor the answer to a single file unless you explicitly state the others contained no relevant evidence.\n"
        "- When indexed excerpts contain formulas, equations, symbolic definitions, or numeric tables, use those exact formulas and values first. Cite every substituted value and state when different files disagree.\n"
        "- FORMULA APPLICATION RULE: if the user asks to calculate/compute something AND the indexed evidence contains a relevant formula, you MUST: "
        "(1) quote the exact formula from the source with its citation [N], "
        "(2) identify each variable in the formula, "
        "(3) substitute the user's provided values (or values from the evidence), "
        "(4) show every arithmetic step, "
        "(5) state the final result with units. "
        "Never skip the formula extraction step — the user expects you to USE the PDF's formulas, not invent your own.\n"
        "- Do not lead with isolated quoted fragments or decorative callouts unless the user explicitly asks.\n"
        "- Prefer complete sentences and coherent paragraphs over stylized snippets.\n"
        "- Keep section titles specific to the request domain; avoid generic reusable labels.\n"
        "- Avoid promotional tone, filler, and repetitive phrasing.\n"
        "- Keep tone precise and authoritative; write with the depth expected of a senior analyst briefing an executive.\n"
        "- For quantitative, physics, chemistry, finance, or any calculation question: "
        "(1) state the final numerical answer with units in the very first sentence, "
        "(2) write the governing formula as a LaTeX display equation using $$...$$, "
        "(3) show every substitution step with numbers, "
        "(4) box or bold the final result, "
        "(5) SELF-VERIFY: compute the result a second way if possible (e.g., plug the answer back into the original equation, "
        "or compute using an alternative method) and confirm both methods agree. If they disagree, flag it explicitly. "
        "Use $...$ for inline math values and $$...$$ for stand-alone equations. "
        "Example for a thin-lens calculation: state di = 22.5 cm, then show "
        "$$\\frac{1}{f} = \\frac{1}{d_o} + \\frac{1}{d_i}$$ and each algebraic step.\n"
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
        "- If more than one relevant ref exists, distribute citations across the answer instead of leaning on a single ref number.\n"
        "- Every substantive paragraph should end with at least one inline citation when evidence is available.\n"
        "- For multi-section answers, each major section must cite at least one supporting ref when evidence exists for that section.\n"
        "- When two or more distinct refs are available, use multiple ref numbers in the body of the answer instead of repeating a single citation number across unrelated claims.\n"
        "- Do not stack the same citation number on consecutive paragraphs unless those paragraphs are genuinely supported by the exact same source passage.\n"
        "- Avoid citation stacks like [1][2][3] at the end of a single sentence unless the sentence truly depends on all of those refs; distribute those refs across the nearby sentences instead.\n"
        "- Prefer 1-2 citations per sentence. If a paragraph uses 3 or more refs, spread them across the paragraph where each claim is made.\n"
        "- Do not put three or more inline citations on the opening sentence of the answer. If the opening conclusion draws on several sources, cite the strongest 1-2 refs there and support the rest in the next sentences.\n"
        "- When comparing claims, attach the citation directly to the sentence that states the comparison, not only at the end of the section.\n"
        "- For formula-based answers, cite the formula source and cite each substituted value where it appears.\n"
        "- Do not write raw page-number prose such as 'Page 66 states...' or 'on page 8'; let the inline citations carry page provenance instead.\n"
        "- Every substantive sentence must be directly supported by the citation attached to that sentence or by a citation immediately at the end of that sentence; do not let one citation carry multiple later sentences that introduce new facts.\n"
        "- Do not invent exact numbers, temperatures, dimensions, material grades, performance percentages, standards, or engineering recommendations unless they are explicitly present in the retrieved evidence.\n"
        "- If an exact value or specification is not visible in the evidence, say that it is not explicitly stated in the indexed content instead of filling it in from general knowledge.\n"
        "- Use clean markdown and avoid malformed formatting."
    )

    # Build project-scope index: all unique source names from the broader scan,
    # beyond just those that fit in the retrieved context window.
    project_index_text = ""
    if all_project_sources:
        unique_sources = list(dict.fromkeys(str(s).strip() for s in all_project_sources if str(s).strip()))
        if unique_sources:
            project_index_text = (
                f"Project source index ({len(unique_sources)} total indexed sources):\n"
                + "\n".join(f"- {s}" for s in unique_sources[:80])
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
            + (f"{project_index_text}\n\n" if project_index_text else "")
            + f"Source index:\n{refs_text or '(none)'}\n\n"
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
            "max_tokens": 3072,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        (
                            "You are Maia, a research-grade AI assistant. Use indexed evidence when available; when it is unavailable, answer from reliable general knowledge. "
                            "Never invent citations or pretend to have source evidence when none is provided. "
                            "LEAD WITH THE ANSWER: the very first sentence must state the direct answer, core finding, or conclusion — never open with 'Based on...', 'It is important to note...', 'I will...', 'Certainly!', 'Great question!', 'As an AI...', or any meta-commentary about what you are about to say. "
                            "Adapt structure to the question — simple factual questions get a focused 2-3 section response with deep, substantive content; analytical or research questions get 5-8 rich sections with expert-level depth. "
                            "For ANY question — simple or complex — provide comprehensive, textbook-level depth: include mechanisms, historical context, statistics, concrete examples, and expert-level nuance. Structure may be simpler for simple questions, but depth must always be high. "
                            "MATH & CALCULATIONS: for any quantitative question (physics, chemistry, finance, statistics, etc.), always show the step-by-step calculation. Use LaTeX: $...$ for inline values and $$...$$ for display equations. Lead with the numerical answer, then prove it by showing the formula, substituting values, and simplifying. "
                            "Write with the depth and precision of a senior analyst briefing a decision-maker: go beyond surface summaries, surface key numbers, explain mechanisms, and address implications. "
                            "Never truncate a response mid-thought; complete every section fully before ending. "
                            "Do not write raw page-number prose such as 'Page 66 states...' or 'on page 8'; let the inline citations carry page provenance instead. "
                            "Every substantive sentence must be directly supported by the citation attached to that sentence or by a citation immediately at the end of that sentence; do not let one citation carry multiple later sentences that introduce new facts. "
                            "Do not invent exact numbers, dimensions, material grades, standards, or engineering recommendations unless they are explicitly visible in the evidence. "
                        )
                        if general_knowledge_mode
                        else (
                            "You are Maia, a research-grade AI assistant. Provide faithful answers grounded in indexed evidence. "
                            "Treat the indexed evidence as a primary source — read every excerpt carefully and surface all specific details, figures, names, and dates, not just headlines. "
                            "LEAD WITH THE ANSWER: the very first sentence must state the direct answer, core finding, or conclusion — never open with 'Based on...', 'It is important to note...', 'I will...', 'Certainly!', 'Great question!', 'As an AI...', or any meta-commentary about what you are about to say. "
                            "Adapt structure and depth to the question — analytical and research questions deserve rich, multi-section responses with specific data, comparisons, mechanisms, and implications drawn from the evidence. "
                            "Go beyond surface summaries: surface exact numbers, highlight agreements and contradictions across sources, and develop each section with substantive detail that would satisfy a domain expert. "
                            "When multiple selected files are in scope, compare across the full selected set before concluding. "
                            "If formulas or equations appear in the indexed evidence, use those exact formulas and cited values in the reasoning. "
                            "MATH & CALCULATIONS: for any quantitative question (physics, chemistry, finance, statistics, etc.), always show the step-by-step calculation. Use LaTeX: $...$ for inline values and $$...$$ for display equations. Lead with the numerical answer, then prove it by showing the formula, substituting values, and simplifying. "
                            "Write with the depth and precision of a senior analyst briefing a decision-maker. "
                            "Never truncate a response mid-thought; complete every section fully before ending. "
                            "Do not write raw page-number prose such as 'Page 66 states...' or 'on page 8'; let the inline citations carry page provenance instead. "
                            "CITATION RULE: cite every factual claim inline using the source ref number in square brackets, e.g. [1] or [2]. Every major claim must have at least one citation marker. Reuse the same ref number only when citing the same source; if different claims are grounded in different refs, distribute citations across those refs instead of repeating [1] for unrelated claims. Every substantive paragraph should carry at least one inline citation when evidence exists. For equations and calculations, cite the governing equation and each substituted value. Do not leave any substantive claim uncited. "
                            "Every substantive sentence must be directly supported by the citation attached to that sentence or by a citation immediately at the end of that sentence; do not let one citation carry multiple later sentences that introduce new facts. "
                            "Do not invent exact numbers, dimensions, material grades, standards, or engineering recommendations unless they are explicitly visible in the evidence. "
                            "Treat prior assistant messages as non-authoritative context only; never reuse prior assistant prose as evidence or as a source of technical facts. "
                        )
                        + f"{build_response_language_rule_fn(requested_language=requested_language, latest_message=question)} "
                        + (
                            "Do not invent facts; acknowledge uncertainty when needed."
                            if general_knowledge_mode
                            else "Do not infer details that are not explicitly supported by evidence."
                        )
                        + (
                            " This is a direct follow-up question — use prior conversation context when relevant to resolve references or build on prior answers."
                            if is_follow_up
                            else " This is an independent question with no dependency on prior conversations — answer entirely from the evidence and question provided; do not reference, repeat, or carry over content from past discussions."
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
        if answer:
            _cache_put(cache_key, answer)
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
