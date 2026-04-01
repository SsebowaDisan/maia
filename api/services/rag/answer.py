"""RAG Pipeline Phase 12: Answer — generate a grounded answer from evidence.

Builds a carefully structured prompt that instructs the LLM to:
  - Answer ONLY from provided evidence
  - Cite with [1], [2], etc. inline markers
  - Show calculation steps when MATH_READY
  - Acknowledge conflicts when CONFLICTING
  - State what's missing when INSUFFICIENT

Then parses the response to extract claims and bind each to its evidence.
"""

from __future__ import annotations

import json
import logging
import os
import re

import httpx

from api.services.rag.types import (
    AnswerClaim,
    CoverageResult,
    CoverageVerdict,
    GeneratedAnswer,
    RAGConfig,
    RankedEvidence,
)

logger = logging.getLogger(__name__)


async def _is_math_question(query: str, config: "RAGConfig") -> bool:
    """Ask the cheap LLM to classify whether this question needs math reasoning.
    No hardcoded keywords — the LLM decides.
    """
    try:
        result = await _call_llm(
            system="You are a question classifier. Respond with ONLY 'yes' or 'no'.",
            user=(
                "Does this question require mathematical calculation, formula application, "
                "unit conversion, numerical derivation, or step-by-step quantitative reasoning "
                "to answer correctly?\n\n"
                f"Question: {query}\n\n"
                "Answer yes or no:"
            ),
            model=config.classify_model or config.answer_model,
        )
        return result.strip().lower().startswith("yes")
    except Exception:
        return False


# ── Prompt construction ─────────────────────────────────────────────────────

def _needs_visual_context(query: str, evidence: list[RankedEvidence]) -> bool:
    """Detect if the query or evidence involves images/figures/diagrams
    that would benefit from sending actual PDF page images to the vision model.
    """
    # Check if any evidence chunk mentions figures
    has_figure_evidence = any(
        "[Figure" in ev.chunk.text or "[Image" in ev.chunk.text or ev.chunk.chunk_type == "figure"
        for ev in evidence
    )
    if has_figure_evidence:
        return True

    # Check if any source files have figures in their chunks
    has_figure_chunks = any(
        ev.chunk.chunk_type in ("figure", "table") for ev in evidence
    )
    if has_figure_chunks:
        return True

    return False


async def _call_llm_with_page_images(
    query: str,
    evidence: list[RankedEvidence],
    system_prompt: str,
    model: str,
    config: "RAGConfig",
) -> str | None:
    """Send relevant PDF pages as images to the vision model alongside text evidence.
    The LLM sees formulas, diagrams, and tables exactly as rendered in the PDF.
    """
    import base64

    api_key = os.environ.get("MAIA_RAG_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None

    base_url = os.environ.get("MAIA_RAG_LLM_BASE_URL", "https://api.openai.com/v1")
    vision_model = config.vision_model or model

    # Collect unique source files and pages from evidence
    pages_needed: dict[str, set[int]] = {}  # source_id → set of page numbers
    for ev in evidence:
        sid = ev.chunk.source_id
        if sid not in pages_needed:
            pages_needed[sid] = set()
        pages_needed[sid].add(ev.chunk.page_start)

    # Render pages as images using PyMuPDF
    page_images: list[dict] = []  # [{base64, page, source}]
    try:
        import fitz

        for source_id, page_nums in pages_needed.items():
            # Find the file path from evidence metadata
            for ev in evidence:
                if ev.chunk.source_id == source_id:
                    file_path = ev.chunk.metadata.get("file_path", "")
                    if not file_path:
                        # Try to find from upload_url
                        from api.services.rag.bridge import resolve_registered_source_path
                        resolved = resolve_registered_source_path(source_id=source_id)
                        if resolved:
                            file_path = str(resolved[0])
                    if file_path and os.path.exists(file_path):
                        doc = fitz.open(file_path)
                        for page_num in sorted(page_nums)[:5]:  # max 5 pages per source
                            if page_num < doc.page_count:
                                page = doc[page_num]
                                # Render at 2x for readability
                                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                                img_bytes = pix.tobytes("png")
                                b64 = base64.b64encode(img_bytes).decode("utf-8")
                                page_images.append({
                                    "base64": b64,
                                    "page": page_num,
                                    "source": ev.chunk.filename or source_id,
                                })
                        doc.close()
                    break
    except Exception as exc:
        logger.warning("Failed to render PDF pages: %s", exc)

    if not page_images:
        return None

    # Build multimodal message: text evidence + page images
    content_parts: list[dict] = []

    # Text part
    evidence_text = _build_evidence_context(evidence)
    content_parts.append({
        "type": "text",
        "text": (
            f"{system_prompt}\n\n"
            f"Below is text evidence extracted from the documents, followed by images of the relevant pages.\n"
            f"Use BOTH the text and images to answer. Cite with [1], [2], etc.\n\n"
            f"Text evidence:\n{evidence_text}\n\n"
            f"Question: {query}"
        ),
    })

    # Image parts
    for img in page_images[:8]:  # max 8 images to stay within limits
        content_parts.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{img['base64']}",
                "detail": "high",
            },
        })

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": vision_model,
                    "messages": [{"role": "user", "content": content_parts}],
                    "temperature": 0.1,
                },
            )
            if response.status_code != 200:
                logger.warning("Vision LLM returned %d", response.status_code)
                return None
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.warning("Vision LLM call failed: %s", exc)
        return None


_SYSTEM_STRICT = """\
You are a research assistant. You MUST answer ONLY from the evidence blocks below. \
Do NOT use your own knowledge. If information is not in the evidence, say "not found in the provided documents".

=== CITATION FORMAT (YOU MUST FOLLOW THIS EXACTLY) ===

Step 1: Every sentence you write MUST end with at least one citation number in square brackets.
Step 2: The citation number refers to the evidence block number. Evidence block [1] is cited as [1].
Step 3: If a sentence uses facts from multiple evidence blocks, list ALL numbers: [1][2][3].
Step 4: Never write a sentence without a citation. Check every sentence before finishing.

GOOD example (follow this):
"The company was founded in 2005 [1]. It has 500 employees across 3 offices [1][2]. Revenue grew 20% year-over-year [3]. The CEO stated that growth was driven by the Asian market [2][3]."

BAD example (never do this):
"The company was founded in 2005. It has many employees. Revenue grew significantly."
This is BAD because: no citations, vague language, missing numbers.

=== ANSWER FORMAT ===

1. Start with a # title in sentence case (capitalise first word only, e.g. "# Overview of the document").
2. Use ## headings to organise sections.
3. Write DETAILED paragraphs — not short summaries. Cover every relevant fact from the evidence.
4. Every paragraph must have multiple citations. Aim for 2-5 citations per paragraph.
5. Cite specific numbers, dates, names, percentages, and definitions — not just general claims.
6. Use EVERY evidence block at least once if it has relevant information.
7. If evidence is insufficient, clearly state what is missing.
8. If sources conflict, present both sides with their citations.
9. Never fabricate information not in the evidence."""

_SYSTEM_RELAXED = """\
You are a research assistant. Answer primarily from the evidence blocks below. \
You may add brief context from general knowledge, but mark it clearly as "(general knowledge)".

=== CITATION FORMAT (YOU MUST FOLLOW THIS EXACTLY) ===

Step 1: Every sentence that uses evidence MUST end with at least one citation number in square brackets.
Step 2: The citation number refers to the evidence block number. Evidence block [1] is cited as [1].
Step 3: If a sentence uses facts from multiple evidence blocks, list ALL numbers: [1][2][3].
Step 4: Never write a sentence using evidence without a citation. Check every sentence before finishing.

GOOD example (follow this):
"The total vacation days allowed is 20 [1]. This is calculated based on a full-time five-day workweek [1][2]. The global vacation duration depends on specific sector funds [2]. For the metal and electrical construction sectors, separate calculations apply [3]."

BAD example (never do this):
"The document discusses vacation days. There are 20 days allowed. Different sectors have different rules."
This is BAD because: no citations at all.

=== ANSWER FORMAT ===

1. Start with a # title in sentence case (capitalise first word only).
2. Use ## headings to organise sections.
3. Write DETAILED paragraphs — not short summaries. Cover every relevant fact.
4. Every paragraph must have multiple citations. Aim for 2-5 citations per paragraph.
5. Cite specific numbers, dates, names, percentages, and definitions.
6. Use EVERY evidence block at least once if it has relevant information.
7. Mark non-evidence statements with "(general knowledge)".
8. If evidence is insufficient, state what is missing."""

_MATH_INSTRUCTION = """
The user is asking for a calculation. From the evidence:
1. State the relevant formula with its source citation.
2. List each variable value with its source citation.
3. Show the substitution step by step.
4. Compute the final result.
5. Cite the source of every value used."""

_CONFLICT_INSTRUCTION = """
The evidence contains conflicting information. You must:
1. Present each position clearly with its source citation.
2. Note where the sources agree and disagree.
3. Do NOT pick a winner — let the user decide."""

_INSUFFICIENT_INSTRUCTION = """
The evidence does not fully answer the question. You must:
1. Answer what you can from the available evidence, with citations.
2. Clearly state what specific information is missing.
3. Do NOT guess or make up the missing information."""


def _extract_highlight_map(answer_text: str) -> tuple[dict, str]:
    """Extract the highlight_map JSON block from the LLM answer.

    Returns (highlight_map_dict, clean_answer_text_without_json_block).
    """
    highlight_map: dict = {}
    clean_text = answer_text

    # Find ```json ... ``` block containing highlight_map
    pattern = re.compile(r'```json\s*\n?(.*?)\n?\s*```', re.DOTALL)
    for m in pattern.finditer(answer_text):
        raw_json = m.group(1).strip()
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict) and "highlight_map" in parsed:
                highlight_map = parsed["highlight_map"]
                # Strip the JSON block from the answer
                clean_text = answer_text[:m.start()].rstrip() + answer_text[m.end():]
                clean_text = clean_text.strip()
                break
        except (json.JSONDecodeError, KeyError):
            continue

    if highlight_map:
        logger.info("Extracted highlight_map with %d citations", len(highlight_map))

    return highlight_map, clean_text


def _build_evidence_context(evidence: list[RankedEvidence]) -> str:
    """Format evidence blocks as numbered references for the LLM."""
    blocks: list[str] = []

    for i, ev in enumerate(evidence, 1):
        source_info = f"Source: {ev.chunk.filename or ev.chunk.source_id}"
        if ev.chunk.page_start >= 0:
            source_info += f", page {ev.chunk.page_start + 1}"
        if ev.chunk.heading_path:
            source_info += f" ({' > '.join(ev.chunk.heading_path)})"

        block = f"[{i}] {source_info}\n{ev.chunk.text}"
        blocks.append(block)

    return "\n\n---\n\n".join(blocks)


def _build_system_prompt(coverage: CoverageResult, config: RAGConfig) -> str:
    """Assemble the system prompt based on coverage verdict and config."""
    base = _SYSTEM_STRICT if config.grounding_mode == "strict" else _SYSTEM_RELAXED
    extras: list[str] = []

    if coverage.verdict == CoverageVerdict.MATH_READY:
        extras.append(_MATH_INSTRUCTION)
    elif coverage.verdict == CoverageVerdict.MATH_INCOMPLETE:
        extras.append(_MATH_INSTRUCTION)
        extras.append(
            f"\nNote: the following variables are MISSING from the evidence: "
            f"{', '.join(coverage.math_missing)}. State this clearly."
        )
    elif coverage.verdict == CoverageVerdict.CONFLICTING:
        extras.append(_CONFLICT_INSTRUCTION)
    elif coverage.verdict in (CoverageVerdict.INSUFFICIENT, CoverageVerdict.PARTIAL):
        extras.append(_INSUFFICIENT_INSTRUCTION)
        if coverage.missing_aspects:
            extras.append(
                f"\nSpecifically missing: {', '.join(coverage.missing_aspects)}"
            )

    return base + "\n".join(extras)


def _build_user_prompt(query: str, evidence_context: str) -> str:
    """Build the user message with the query and evidence."""
    return (
        f"## Evidence\n\n{evidence_context}\n\n"
        f"## Question\n\n{query}\n\n"
        f"REMEMBER: You MUST cite every sentence. Write [1], [2], etc. at the end of each sentence. "
        f"Example: \"The value is 20 [1]. It is calculated weekly [1][2].\"\n\n"
        f"=== HIGHLIGHT MAP (required after your answer) ===\n\n"
        f"After your answer, you MUST output a JSON block.\n"
        f"For EVERY citation number you used, copy-paste the EXACT sentence(s) from the evidence block.\n"
        f"Do NOT rewrite or paraphrase. Copy the text EXACTLY as it appears in the evidence so we can find and highlight it in the PDF.\n"
        f"The page number comes from the evidence block header (e.g. \"Source: file.pdf, page 1\" means page=1).\n\n"
        f"Example:\n"
        f'```json\n'
        f'{{"highlight_map": {{\n'
        f'  "1": {{\n'
        f'    "sentences": [\n'
        f'      "The total number of regular vacation days to be taken in 2026 is 20.",\n'
        f'      "This is expressed in a full-time five-day workweek."\n'
        f'    ],\n'
        f'    "page": 1\n'
        f'  }},\n'
        f'  "2": {{\n'
        f'    "sentences": ["The global vacation duration is calculated based on vacation funds."],\n'
        f'    "page": 1\n'
        f'  }}\n'
        f'}}}}\n'
        f'```\n\n'
        f"IMPORTANT: Include ALL citation numbers in the highlight_map, not just some. "
        f"Every [N] in your answer must have a matching entry in the highlight_map."
    )


# ── LLM call ───────────────────────────────────────────────────────────────

async def _call_llm(
    system: str,
    user: str,
    model: str,
    max_tokens: int | None = None,
) -> str:
    """Call OpenAI chat completion API."""
    api_key = os.environ.get("MAIA_RAG_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "") or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        logger.warning("No API key set (OPENAI_API_KEY or GROQ_API_KEY); returning placeholder answer")
        return (
            "I cannot generate an answer because the API key is not configured. "
            "The evidence has been retrieved and ranked successfully."
        )

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            os.environ.get("MAIA_RAG_LLM_BASE_URL", "https://api.openai.com/v1") + "/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                k: v for k, v in {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.1,  # low temp for factual grounding
                }.items() if v is not None
            },
        )
        if response.status_code != 200:
            error_body = response.text[:500]
            logger.error("LLM API error %d: %s", response.status_code, error_body)
            response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


# ── Response parsing ────────────────────────────────────────────────────────

_REF_PATTERN = re.compile(r"\[(\d+)\]")


def _parse_claims(
    answer_text: str,
    evidence: list[RankedEvidence],
) -> list[AnswerClaim]:
    """Parse the LLM answer into individual claims bound to evidence.

    Splits on sentence boundaries and extracts [ref] markers from each sentence.
    """
    # Split into sentences (simple heuristic)
    sentences = re.split(r"(?<=[.!?])\s+", answer_text)
    claims: list[AnswerClaim] = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Find all [N] references in this sentence
        refs = _REF_PATTERN.findall(sentence)
        ref_ids = [f"[{r}]" for r in refs]

        # Map to evidence objects (1-indexed)
        bound_evidence: list[RankedEvidence] = []
        bound_anchors = []
        for r in refs:
            idx = int(r) - 1
            if 0 <= idx < len(evidence):
                ev = evidence[idx]
                bound_evidence.append(ev)
                bound_anchors.extend(ev.anchors)

        # Detect if this is a calculation step
        is_calc = bool(re.search(r"[=×÷*/]\s*\d", sentence))
        calc_trace = sentence if is_calc else ""

        claims.append(
            AnswerClaim(
                text=sentence,
                evidence=bound_evidence,
                anchors=bound_anchors,
                ref_ids=ref_ids,
                is_calculation=is_calc,
                calculation_trace=calc_trace,
            )
        )

    return claims


def _check_grounding(claims: list[AnswerClaim]) -> bool:
    """Check if all substantive claims are grounded in evidence.

    Returns False if any non-trivial claim lacks a citation.
    """
    trivial_patterns = [
        r"^(in summary|to summarize|overall|in conclusion|therefore|thus|hence)",
        r"^(the evidence|the sources|based on|according to)",
        r"^(yes|no|it depends)\b",
    ]
    for claim in claims:
        if not claim.ref_ids:
            text_lower = claim.text.lower().strip()
            # Skip if it's a trivial/transition sentence
            is_trivial = any(re.match(p, text_lower) for p in trivial_patterns)
            if not is_trivial and len(claim.text.split()) > 5:
                return False
    return True


# ── Public API ──────────────────────────────────────────────────────────────

async def generate_answer(
    query: str,
    evidence: list[RankedEvidence],
    coverage: CoverageResult,
    config: RAGConfig,
) -> GeneratedAnswer:
    """Phase 12: Generate a grounded answer from ranked evidence.

    Constructs a prompt that enforces evidence-only answers with inline
    citations, calls the LLM, then parses the response into claims bound
    to their source evidence.

    Parameters
    ----------
    query : the user's question
    evidence : ranked evidence from Phase 10
    coverage : coverage analysis from Phase 11
    config : pipeline configuration

    Returns
    -------
    GeneratedAnswer with full text, parsed claims, and grounding status.
    """
    if not evidence:
        return GeneratedAnswer(
            text="I could not find any relevant evidence to answer this question.",
            claims=[],
            coverage=coverage,
            grounded=True,
            has_calculations=False,
        )

    # Build prompts
    system_prompt = _build_system_prompt(coverage, config)
    evidence_context = _build_evidence_context(evidence)
    user_prompt = _build_user_prompt(query, evidence_context)

    # Route math questions to the math model (o4-mini), everything else to cheap model
    is_math = coverage.verdict in (CoverageVerdict.MATH_READY, CoverageVerdict.MATH_INCOMPLETE) or await _is_math_question(query, config)
    selected_model = config.math_model if (is_math and config.math_model) else config.answer_model

    if is_math:
        logger.info("Math question detected — using model: %s", selected_model)

    # For image-heavy evidence or visual questions, render PDF pages as images
    # and send them alongside text to the vision model
    needs_vision = _needs_visual_context(query, evidence)
    if needs_vision:
        logger.info("Visual context needed — sending page images to vision model")
        try:
            answer_text = await _call_llm_with_page_images(
                query, evidence, system_prompt, selected_model, config,
            )
            if answer_text:
                claims = _parse_claims(answer_text, evidence)
                grounded = _check_grounding(claims)
                return GeneratedAnswer(
                    text=answer_text, claims=claims, coverage=coverage,
                    grounded=grounded, has_calculations=any(c.is_calculation for c in claims),
                )
        except Exception as exc:
            logger.warning("Vision answer failed, falling back to text: %s", exc)

    # If total prompt is very large, batch evidence into smaller calls
    total_chars = len(system_prompt) + len(user_prompt)
    if total_chars > 80000:
        answer_text = await _call_llm_batched(query, evidence, coverage, config, model_override=selected_model)
    else:
        answer_text = await _call_llm(
            system=system_prompt,
            user=user_prompt,
            model=selected_model,
            max_tokens=config.max_answer_tokens or None,
        )

    # Extract highlight_map JSON from the answer and strip it from the text
    highlight_map, clean_text = _extract_highlight_map(answer_text)
    answer_text = clean_text

    # Parse response into claims
    claims = _parse_claims(answer_text, evidence)

    # Check grounding
    grounded = _check_grounding(claims)
    has_calcs = any(c.is_calculation for c in claims)

    result = GeneratedAnswer(
        text=answer_text,
        claims=claims,
        coverage=coverage,
        grounded=grounded,
        has_calculations=has_calcs,
        highlight_map=highlight_map,
    )

    logger.info(
        "Answer: %d claims, grounded=%s, has_calcs=%s, coverage=%s",
        len(claims), grounded, has_calcs, coverage.verdict.value,
    )

    return result


async def _call_llm_batched(
    query: str,
    evidence: list[RankedEvidence],
    coverage: CoverageResult,
    config: RAGConfig,
    model_override: str = "",
) -> str:
    """Map-reduce for large evidence: summarize batches, then synthesize.
    No limits on evidence — handles any size by batching into LLM calls.
    """
    model = model_override or config.answer_model
    batch_size = 5
    summaries: list[str] = []

    for i in range(0, len(evidence), batch_size):
        batch = evidence[i : i + batch_size]
        batch_context = _build_evidence_context(batch)
        batch_prompt = (
            f"Extract the key findings relevant to this question from the evidence below.\n"
            f"Be specific and include numbers, facts, and sources.\n\n"
            f"Question: {query}\n\n{batch_context}"
        )
        try:
            summary = await _call_llm(
                system="You extract key findings from evidence. Be concise and factual.",
                user=batch_prompt,
                model=model,
            )
            summaries.append(f"[Batch {i // batch_size + 1}] {summary}")
        except Exception as exc:
            logger.warning("Batch %d summary failed: %s", i // batch_size + 1, exc)

    if not summaries:
        return "I found relevant evidence but could not generate an answer due to processing limits."

    combined = "\n\n---\n\n".join(summaries)
    system_prompt = _build_system_prompt(coverage, config)
    final_prompt = (
        f"Based on these evidence summaries, answer the question.\n"
        f"Cite sources using [1], [2], etc.\n\n"
        f"Question: {query}\n\n{combined}"
    )

    return await _call_llm(
        system=system_prompt,
        user=final_prompt,
        model=model,
    )
