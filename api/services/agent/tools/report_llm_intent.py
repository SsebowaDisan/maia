from __future__ import annotations

from typing import Any

from api.services.agent.llm_runtime import call_json_response, call_text_response, env_bool
from api.services.agent.tools.report_utils import _coerce_bool


def _classify_report_intent_with_llm(
    *,
    prompt: str,
    summary: str,
    title: str,
    settings: dict[str, Any],
) -> dict[str, bool]:
    if not env_bool("MAIA_AGENT_LLM_REPORT_INTENT_ENABLED", default=True):
        return {}
    payload = {
        "prompt": " ".join(str(prompt or "").split()).strip()[:520],
        "summary": " ".join(str(summary or "").split()).strip()[:520],
        "title": " ".join(str(title or "").split()).strip()[:200],
        "preferences": settings.get("__user_preferences") if isinstance(settings.get("__user_preferences"), dict) else {},
    }
    response = call_json_response(
        system_prompt=(
            "You classify report-generation intent flags for an agent. "
            "Return strict JSON only."
        ),
        user_prompt=(
            "Return JSON only in this schema:\n"
            "{\n"
            '  "location_objective": false,\n'
            '  "direct_question": false,\n'
            '  "simple_explanation_required": false\n'
            "}\n"
            "Rules:\n"
            "- Infer only from provided input.\n"
            "- Do not fabricate facts.\n\n"
            f"Input:\n{payload}"
        ),
        temperature=0.0,
        timeout_seconds=9,
        max_tokens=120,
    )
    if not isinstance(response, dict):
        return {}
    location_objective = _coerce_bool(response.get("location_objective"))
    direct_question = _coerce_bool(response.get("direct_question"))
    simple_explanation = _coerce_bool(response.get("simple_explanation_required"))
    output: dict[str, bool] = {}
    if location_objective is not None:
        output["location_objective"] = location_objective
    if direct_question is not None:
        output["direct_question"] = direct_question
    if simple_explanation is not None:
        output["simple_explanation_required"] = simple_explanation
    return output


def _extract_location_signal_with_llm(text: str) -> str:
    clean = " ".join(str(text or "").split()).strip()
    if not clean:
        return ""
    if not env_bool("MAIA_AGENT_LLM_LOCATION_SIGNAL_ENABLED", default=True):
        return ""
    response = call_json_response(
        system_prompt="Extract concrete location evidence from text. Return strict JSON only.",
        user_prompt=(
            "Return JSON only in this schema:\n"
            '{ "location_signal": "string", "has_location_signal": false }\n'
            "Rules:\n"
            "- Keep location_signal empty when no explicit location evidence exists.\n"
            "- Do not infer or guess.\n\n"
            f"Input text:\n{clean[:1200]}"
        ),
        temperature=0.0,
        timeout_seconds=8,
        max_tokens=120,
    )
    if not isinstance(response, dict):
        return ""
    has_location = _coerce_bool(response.get("has_location_signal"))
    signal = " ".join(str(response.get("location_signal") or "").split()).strip(" .,:;")
    if has_location is False:
        return ""
    return signal[:160]


def _draft_direct_answer(question: str) -> str:
    if not env_bool("MAIA_AGENT_LLM_REPORT_QA_ENABLED", default=True):
        return ""
    payload = " ".join(str(question or "").split()).strip()
    if not payload:
        return ""
    response = call_text_response(
        system_prompt=(
            "You answer user questions clearly and concisely for enterprise reports. "
            "Do not mention tools or execution steps."
        ),
        user_prompt=(
            "Provide a direct answer in 2-5 sentences.\n"
            "If confidence is low, state uncertainty briefly.\n\n"
            f"Question:\n{payload}"
        ),
        temperature=0.1,
        timeout_seconds=10,
        max_tokens=260,
    )
    clean = " ".join(str(response or "").split()).strip()
    if not clean:
        return ""
    if len(clean) > 900:
        return f"{clean[:899].rstrip()}..."
    return clean


def _prefers_simple_explanation(
    *,
    prompt: str,
    summary: str,
    title: str,
    settings: dict[str, Any],
    llm_intent_flags: dict[str, bool] | None = None,
) -> bool:
    if bool(settings.get("__simple_explanation_required")):
        return True
    if isinstance(llm_intent_flags, dict) and bool(llm_intent_flags.get("simple_explanation_required")):
        return True
    prefs = settings.get("__user_preferences")
    if not isinstance(prefs, dict):
        prefs = {}
    explicit_pref = _coerce_bool(prefs.get("simple_explanation_required"))
    if explicit_pref is not None:
        return explicit_pref
    inferred = _classify_report_intent_with_llm(
        prompt=prompt,
        summary=summary,
        title=title,
        settings=settings,
    )
    return bool(inferred.get("simple_explanation_required"))
