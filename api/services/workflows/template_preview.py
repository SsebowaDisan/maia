"""Template Preview — generates and caches sample outputs for workflow templates.

When a user browses templates in the gallery, they can see a real example
of what the workflow produces. Previews are generated once and cached.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(".maia_agent") / "template_previews"
_CACHE_TTL = 7 * 86400  # 7 days


def _cache_key(template_id: str) -> str:
    return hashlib.sha256(template_id.encode()).hexdigest()[:16]


def _cache_path(template_id: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{_cache_key(template_id)}.json"


def get_cached_preview(template_id: str) -> dict[str, Any] | None:
    """Return cached preview if fresh, else None."""
    fpath = _cache_path(template_id)
    if not fpath.exists():
        return None
    try:
        data = json.loads(fpath.read_text(encoding="utf-8"))
        if time.time() - data.get("generated_at", 0) > _CACHE_TTL:
            return None
        return data
    except Exception:
        return None


def save_preview(template_id: str, preview: dict[str, Any]) -> None:
    """Cache a generated preview."""
    fpath = _cache_path(template_id)
    try:
        fpath.write_text(json.dumps({**preview, "generated_at": time.time()}, default=str), encoding="utf-8")
    except Exception as exc:
        logger.debug("Failed to cache preview: %s", exc)


def generate_preview(template_id: str, definition: dict[str, Any]) -> dict[str, Any]:
    """Generate a sample output preview for a workflow template.

    Uses the LLM to simulate what the workflow would produce with sample data.
    """
    cached = get_cached_preview(template_id)
    if cached:
        return cached

    name = str(definition.get("name", template_id))
    description = str(definition.get("description", ""))
    steps = definition.get("steps", [])

    step_descriptions = []
    for i, step in enumerate(steps):
        step_desc = str(step.get("description", "")).strip()
        agent_id = str(step.get("agent_id", "")).strip()
        step_descriptions.append(f"Step {i + 1} ({agent_id}): {step_desc}")

    prompt = f"""Generate a realistic sample output preview for this workflow template.

Workflow: {name}
Description: {description}
Steps:
{chr(10).join(step_descriptions)}

Write a realistic example of what each step would produce, using plausible sample data.
Keep each step output to 2-3 sentences. Format as markdown with step headers."""

    try:
        from api.services.agents.runner import run_agent_task
        parts: list[str] = []
        for chunk in run_agent_task(prompt, system_prompt="You generate realistic sample data previews for workflow templates. Use plausible business data.", max_tool_calls=0):
            text = chunk.get("text") or chunk.get("content") or ""
            if text:
                parts.append(str(text))
        sample_output = "".join(parts)[:3000]
    except Exception as exc:
        sample_output = f"Preview generation unavailable: {exc}"

    preview = {
        "template_id": template_id,
        "name": name,
        "sample_output": sample_output,
        "step_count": len(steps),
    }
    save_preview(template_id, preview)
    return preview


def list_previews() -> list[dict[str, Any]]:
    """List all cached previews."""
    if not _CACHE_DIR.exists():
        return []
    previews: list[dict[str, Any]] = []
    for fpath in _CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            previews.append({"template_id": data.get("template_id", fpath.stem), "name": data.get("name", ""), "has_preview": bool(data.get("sample_output"))})
        except Exception:
            pass
    return previews
