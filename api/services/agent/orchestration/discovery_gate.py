from __future__ import annotations

from typing import Any


def _clean_text(value: Any, *, limit: int = 220) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[: max(1, int(limit))]


def _clean_rows(rows: list[Any], *, limit: int = 8) -> list[str]:
    output: list[str] = []
    for row in rows:
        text = _clean_text(row)
        if not text or text in output:
            continue
        output.append(text)
        if len(output) >= max(1, int(limit)):
            break
    return output


def blocking_requirements_from_slots(
    *,
    slots: list[dict[str, Any]],
    fallback_requirements: list[str],
    limit: int = 6,
) -> list[str]:
    candidate_rows: list[str] = []
    for slot in slots[:16]:
        if not isinstance(slot, dict):
            continue
        requirement = _clean_text(slot.get("requirement"))
        if not requirement:
            continue
        if bool(slot.get("blocking")) and not bool(slot.get("discoverable")):
            candidate_rows.append(requirement)
    clean_rows = _clean_rows(candidate_rows, limit=limit)
    if clean_rows:
        return clean_rows
    return _clean_rows(list(fallback_requirements or []), limit=limit)


def clarification_questions_from_slots(
    *,
    slots: list[dict[str, Any]],
    requirements: list[str],
    limit: int = 6,
) -> list[str]:
    clean_requirements = _clean_rows(list(requirements or []), limit=limit)
    if not clean_requirements:
        return []
    question_by_requirement: dict[str, str] = {}
    for slot in slots[:24]:
        if not isinstance(slot, dict):
            continue
        requirement = _clean_text(slot.get("requirement"))
        question = _clean_text(slot.get("question"))
        if requirement and question and requirement not in question_by_requirement:
            question_by_requirement[requirement] = question
    questions: list[str] = []
    for requirement in clean_requirements:
        question = question_by_requirement.get(requirement) or f"Please provide: {requirement}"
        if question in questions:
            continue
        questions.append(question)
        if len(questions) >= max(1, int(limit)):
            break
    return questions

