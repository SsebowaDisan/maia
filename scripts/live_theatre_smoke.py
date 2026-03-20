"""Live smoke test for Brain assemble-and-run SSE theatre signals.

Usage:
  .venv311\\Scripts\\python.exe scripts/live_theatre_smoke.py ^
    --description "Research machine learning and email a report to ssebowadisan1@gmail.com"

Environment:
  MAIA_BASE_URL      default http://127.0.0.1:8000
  MAIA_TEST_BEARER   optional Bearer token for authenticated environments
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from typing import Any, Dict, Iterable, Optional, Tuple

import requests


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def _iter_sse_events(lines: Iterable[str]) -> Iterable[Tuple[str, str]]:
    event_name = ""
    data_lines: list[str] = []
    for raw in lines:
        line = str(raw or "").rstrip("\r")
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
            continue
        if line == "":
            if event_name or data_lines:
                yield event_name, "\n".join(data_lines)
            event_name = ""
            data_lines = []


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_browserish(event_type: str, payload: Dict[str, Any], data: Dict[str, Any]) -> bool:
    if event_type.startswith("browser_") or event_type.startswith("web_"):
        return True
    tool_id = _normalize(data.get("tool_id") or payload.get("tool_id"))
    scene_surface = _normalize(data.get("scene_surface") or payload.get("scene_surface"))
    return (
        scene_surface in {"browser", "website", "web"}
        or tool_id.startswith("browser.")
        or "web_research" in tool_id
    )


def run_smoke(base_url: str, description: str, max_seconds: int, bearer_token: str = "") -> int:
    url = f"{base_url.rstrip('/')}/api/workflows/assemble-and-run"
    headers = {"Content-Type": "application/json"}
    if bearer_token.strip():
        headers["Authorization"] = f"Bearer {bearer_token.strip()}"

    response = requests.post(
        url,
        json={"description": description},
        headers=headers,
        stream=True,
        timeout=30,
    )
    if response.status_code != 200:
        body = response.text[:1200]
        print(f"[FAIL] HTTP {response.status_code} from {url}")
        print(body)
        return 1

    started_at = time.time()
    last_event_at = started_at
    event_counts: Counter[str] = Counter()
    saw_done = False
    saw_assembly_start = False
    saw_assembly_step = False
    saw_execution_start = False
    saw_live_browser = False
    saw_team_signal = False

    for event_name, data_text in _iter_sse_events(response.iter_lines(decode_unicode=True)):
        if time.time() - started_at > max_seconds:
            break
        if not data_text:
            continue
        if data_text == "[DONE]":
            saw_done = True
            break

        payload: Dict[str, Any]
        try:
            parsed = json.loads(data_text)
            payload = _as_dict(parsed)
        except json.JSONDecodeError:
            payload = {"detail": data_text}

        event_type = _normalize(payload.get("event_type") or event_name)
        if not event_type:
            continue

        event_counts[event_type] += 1
        last_event_at = time.time()
        data = _as_dict(payload.get("data"))
        tool_id = _normalize(data.get("tool_id") or payload.get("tool_id"))

        if event_type == "assembly_started":
            saw_assembly_start = True
        if event_type == "assembly_step_added":
            saw_assembly_step = True
        if event_type == "execution_starting":
            saw_execution_start = True
        if _is_browserish(event_type, payload, data):
            saw_live_browser = True
        if (
            event_type.startswith("agent_dialogue")
            or event_type in {"role_handoff", "agent_handoff", "agent.resume", "agent.waiting", "assembly_narration"}
            or (event_type.startswith("tool_") and "agent.delegate" in tool_id)
        ):
            saw_team_signal = True

    elapsed = round(time.time() - started_at, 1)
    idle = round(time.time() - last_event_at, 1)
    print(f"[INFO] elapsed={elapsed}s idle={idle}s done={saw_done}")
    top = ", ".join([f"{name}:{count}" for name, count in event_counts.most_common(12)])
    print(f"[INFO] top events: {top or 'none'}")

    checks = {
        "assembly_started": saw_assembly_start,
        "assembly_step_added": saw_assembly_step,
        "execution_starting": saw_execution_start,
        "live_browser_or_web_event": saw_live_browser,
        "team_conversation_signal": saw_team_signal,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        print("[FAIL] Missing required live signals:")
        for name in failed:
            print(f"  - {name}")
        return 2

    print("[PASS] Live theatre smoke checks passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Live assemble-and-run SSE smoke test")
    parser.add_argument(
        "--description",
        default="Research machine learning and email a report to ssebowadisan1@gmail.com",
        help="Natural-language request for brain assemble-and-run",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("MAIA_BASE_URL", "http://127.0.0.1:8000"),
        help="Backend base URL",
    )
    parser.add_argument(
        "--max-seconds",
        type=int,
        default=180,
        help="Maximum seconds to observe stream events",
    )
    args = parser.parse_args()
    token = os.getenv("MAIA_TEST_BEARER", "")
    return run_smoke(args.base_url, args.description, max(30, args.max_seconds), token)


if __name__ == "__main__":
    sys.exit(main())
