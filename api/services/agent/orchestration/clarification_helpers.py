from __future__ import annotations

import re

# Keep tokenization generic and language-neutral; no fixed keyword tables.
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{4,}")


def _token_set(text: str) -> set[str]:
    return {
        match.group(0).lower()
        for match in _TOKEN_RE.finditer(" ".join(str(text or "").split()).strip())
    }


def _is_semantically_related(requirement: str, contract_missing_item: str) -> bool:
    requirement_tokens = _token_set(requirement)
    if not requirement_tokens:
        return False
    missing_tokens = _token_set(contract_missing_item)
    if not missing_tokens:
        return False
    overlap = requirement_tokens.intersection(missing_tokens)
    return bool(overlap)


def select_relevant_clarification_requirements(
    *,
    deferred_missing_requirements: list[str],
    contract_missing_items: list[str],
    limit: int = 6,
) -> list[str]:
    """Keep only deferred requirements that are relevant to current contract failures."""
    clean_requirements = [
        " ".join(str(item or "").split()).strip()
        for item in deferred_missing_requirements
        if " ".join(str(item or "").split()).strip()
    ]
    clean_requirements = list(dict.fromkeys(clean_requirements))[: max(1, int(limit))]
    if not clean_requirements:
        return []

    clean_contract_missing = [
        " ".join(str(item or "").split()).strip()
        for item in contract_missing_items
        if " ".join(str(item or "").split()).strip()
    ]
    if not clean_contract_missing:
        return clean_requirements[: max(1, int(limit))]

    selected: list[str] = []
    for requirement in clean_requirements:
        if any(
            _is_semantically_related(requirement=requirement, contract_missing_item=missing)
            for missing in clean_contract_missing
        ):
            selected.append(requirement)
    return selected[: max(1, int(limit))]


def questions_for_requirements(
    *,
    requirements: list[str],
    all_requirements: list[str],
    all_questions: list[str],
) -> list[str]:
    normalized_requirements = [
        " ".join(str(item or "").split()).strip() for item in requirements if str(item or "").strip()
    ]
    normalized_all_requirements = [
        " ".join(str(item or "").split()).strip() for item in all_requirements if str(item or "").strip()
    ]
    normalized_all_questions = [
        " ".join(str(item or "").split()).strip() for item in all_questions if str(item or "").strip()
    ]
    if not normalized_requirements:
        return []

    question_map: dict[str, str] = {}
    for idx, requirement in enumerate(normalized_all_requirements):
        if idx < len(normalized_all_questions):
            question_map.setdefault(requirement, normalized_all_questions[idx])

    selected_questions: list[str] = []
    for requirement in normalized_requirements:
        question = question_map.get(requirement) or f"Please provide: {requirement}"
        if question in selected_questions:
            continue
        selected_questions.append(question)
    return selected_questions
