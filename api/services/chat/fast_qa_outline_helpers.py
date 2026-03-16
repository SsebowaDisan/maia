from __future__ import annotations

import json
import re
from typing import Any


def plan_adaptive_outline(
    *,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float,
    question: str,
    history_text: str,
    refs_text: str,
    context_text: str,
    truncate_for_log_fn,
    call_openai_chat_text_fn,
    parse_json_object_fn,
    normalize_outline_fn,
    logger,
) -> dict[str, Any]:
    planner_temperature = max(0.0, min(1.0, float(temperature) * 0.5))
    refs_count = len(re.findall(r"^\[\d+\]\s", refs_text or "", flags=re.MULTILINE))
    logger.warning(
        "fast_qa_planner_request model=%s temp=%.3f refs=%d history_chars=%d context_chars=%d question=%s",
        model,
        planner_temperature,
        refs_count,
        len(history_text or ""),
        len(context_text or ""),
        truncate_for_log_fn(question, 280),
    )
    planner_prompt = (
        "Create an answer blueprint for a research-grade assistant reply.\n"
        "Return one JSON object only with keys:\n"
        '{ "style": "string", "detail_level": "high", "sections": [{"title":"string","goal":"string","format":"paragraphs|bullets|table|mixed"}], "tone": "string" }\n'
        "Rules:\n"
        "- Structure must be specific to this exact user request and evidence, not a generic reusable template.\n"
        "- For analytical, research, or comparison questions: use 5-8 substantive sections that explore different "
        "dimensions (e.g. context/background, key findings, mechanisms, data/evidence, implications, competing views, limitations).\n"
        "- For direct factual or conceptual questions (e.g. 'what is X?', 'how does Y work?', 'define Z'): use 2-3 focused sections "
        "with detail_level 'comprehensive'. Do NOT reduce depth — these questions deserve rich, substantive content covering "
        "definition/overview, mechanisms/how-it-works, and real-world context/applications. The structure is simpler but the depth must be high.\n"
        "- For quantitative / calculation questions (e.g. physics problems, financial formulas, unit conversions, statistics): "
        "use exactly 3 sections — (1) 'Answer' giving the direct numerical result with units, "
        "(2) 'Step-by-Step Solution' showing the formula and every substitution step, "
        "(3) 'Interpretation & Context' explaining what the result means and any relevant caveats. "
        "Section goals must specify the formula name, variables, and expected result — not generic phrases.\n"
        "- Each section goal must specify at least 2 concrete, specific findings or data points that will be surfaced — "
        "goals like 'provide details', 'explain the topic', 'review the source', or 'list the URL' are not acceptable.\n"
        "- CRITICAL: Section goals must describe CONTENT to write (analysis, findings, data), never meta-actions "
        "like 'note the source reviewed' or 'acknowledge the URL' — those are stubs, not content.\n"
        "- Design sections that progressively deepen the analysis: start with context, move to primary "
        "evidence/data, then mechanisms, then implications or significance.\n"
        "- Sections should cover distinct angles: do not repeat the same content across sections.\n"
        "- Section titles must be specific, professional, and tied to concrete entities in the request/evidence.\n"
        "- Do not default to reusable company-profile or marketing-report skeletons unless explicitly requested.\n"
        "- Do not include operational headings such as Delivery Status, Contract Gate, Verification, or Execution Issues.\n"
        "- If user intent is unclear/noisy, produce one section focused on a clarifying question instead of assumptions.\n"
        "- Do not invent facts.\n\n"
        f"Question:\n{question}\n\n"
        f"Recent chat history:\n{history_text}\n\n"
        f"Source index:\n{refs_text or '(none)'}\n\n"
        f"Evidence excerpt (truncated):\n{context_text[:14000]}"
    )
    planner_payload = {
        "model": model,
        "temperature": planner_temperature,
        "max_tokens": 1200,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You design deep, well-structured response blueprints for a research-grade AI assistant. "
                    "For ALL questions — simple or complex — section goals must specify substantive content to write with full depth. "
                    "Simple factual questions get 2-3 focused sections with comprehensive depth (definition, mechanisms, real-world context). "
                    "Analytical questions get 5-8 sections exploring distinct dimensions. "
                    "Calculation/quantitative questions get exactly 3 sections: direct answer, step-by-step solution (with LaTeX formula and substitutions), and interpretation. "
                    "Section goals must describe real content to write (findings, data, analysis, mechanisms, examples), never meta-actions like 'review the source' or 'note the URL'. "
                    "Return JSON only."
                ),
            },
            {"role": "user", "content": planner_prompt},
        ],
    }
    try:
        planned_raw = call_openai_chat_text_fn(
            api_key=api_key,
            base_url=base_url,
            request_payload=planner_payload,
            timeout_seconds=30,
        )
        parsed_outline = parse_json_object_fn(str(planned_raw or ""))
        normalized_outline = normalize_outline_fn(parsed_outline)
        logger.warning(
            "fast_qa_planner_output parse_ok=%s sections=%d style=%s raw=%s parsed=%s normalized=%s",
            bool(parsed_outline),
            len(normalized_outline.get("sections", []) or []),
            str(normalized_outline.get("style", "")),
            truncate_for_log_fn(planned_raw, 900),
            truncate_for_log_fn(
                json.dumps(parsed_outline, ensure_ascii=True, separators=(",", ":"))
                if parsed_outline
                else "(parse-failed)",
                900,
            ),
            truncate_for_log_fn(
                json.dumps(normalized_outline, ensure_ascii=True, separators=(",", ":")),
                900,
            ),
        )
        return normalized_outline
    except Exception:
        logger.exception("fast_qa_planner_output error; using fallback outline")
        fallback_outline = normalize_outline_fn(None)
        logger.warning(
            "fast_qa_planner_fallback normalized=%s",
            truncate_for_log_fn(
                json.dumps(fallback_outline, ensure_ascii=True, separators=(",", ":")),
                900,
            ),
        )
        return fallback_outline
