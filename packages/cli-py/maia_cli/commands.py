"""CLI command implementations — each function handles one subcommand."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from maia_cli import __version__
from maia_cli.colors import (
    BOLD, DIM, RESET, GREEN, YELLOW, RED, CYAN, MAGENTA, GRAY,
    bold, colored, dim,
)
from maia_cli.render import render_event

LOGO = f"""{MAGENTA}{BOLD}
  \u2554\u2566\u2557\u2554\u2550\u2557\u2566\u2554\u2550\u2557
  \u2551\u2551\u2551\u2560\u2550\u2563\u2551\u2560\u2550\u2563
  \u2569 \u2569\u2569 \u2569\u2569\u2569 \u2569{RESET} {dim(f'CLI v{__version__}')}
"""


def cmd_stream(args: argparse.Namespace) -> None:
    """Connect to a live ACP stream and render events."""
    from maia_sdk import connect_sse

    print(LOGO)
    print(f"  Connecting to {colored(args.url, CYAN)}")
    print(f"  {dim('Press Ctrl+C to stop')}\n")

    save_file = None
    if args.save:
        save_file = open(args.save, "a", encoding="utf-8")
        print(f"  Saving to {colored(args.save, GREEN)}\n")

    event_count = 0
    total_cost = 0.0

    try:
        for event in connect_sse(args.url):
            event_dict = event.model_dump()
            event_count += 1

            if args.raw:
                print(json.dumps(event_dict, default=str))
            else:
                print(render_event(event_dict))
                print()

            if save_file:
                save_file.write(json.dumps(event_dict, default=str) + "\n")

            if event.event_type == "event":
                cost = event.payload.get("cost", {})
                if isinstance(cost, dict):
                    total_cost += cost.get("cost_usd", 0)
    finally:
        if save_file:
            save_file.close()
        print(f"\n  {dim(f'{event_count} events. Cost: ${total_cost:.4f}')}")


def cmd_replay(args: argparse.Namespace) -> None:
    """Replay a recorded JSONL run with timing."""
    path = Path(args.file)
    if not path.exists():
        print(f"{RED}File not found: {args.file}{RESET}", file=sys.stderr)
        sys.exit(1)

    print(LOGO)
    print(f"  Replaying {colored(str(path), CYAN)} at {args.speed}x\n")

    events = _load_jsonl(path)
    if not events:
        print(f"  {YELLOW}No events found.{RESET}")
        return

    print(f"  {dim(f'{len(events)} events loaded')}\n")

    prev_ts = None
    for event in events:
        ts = event.get("timestamp", "")
        if prev_ts and ts:
            _sleep_between(prev_ts, ts, args.speed)
        prev_ts = ts

        if args.raw:
            print(json.dumps(event, default=str))
        else:
            print(render_event(event))
            print()

    print(f"\n  {dim(f'Replay complete. {len(events)} events.')}")


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate ACP events in a JSONL file."""
    path = Path(args.file)
    if not path.exists():
        print(f"{RED}File not found: {args.file}{RESET}", file=sys.stderr)
        sys.exit(1)

    print(LOGO)
    print(f"  Validating {colored(str(path), CYAN)}\n")

    required = {"acp_version", "run_id", "agent_id", "event_type", "timestamp", "payload"}
    valid_types = {"message", "handoff", "review", "artifact", "event", "capabilities"}
    valid = invalid = warnings = 0

    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"  {RED}Line {i}: Invalid JSON \u2014 {exc}{RESET}")
                invalid += 1
                continue

            if not isinstance(event, dict):
                print(f"  {RED}Line {i}: Not a JSON object{RESET}")
                invalid += 1
                continue

            missing = required - set(event.keys())
            if missing:
                print(f"  {RED}Line {i}: Missing: {', '.join(missing)}{RESET}")
                invalid += 1
                continue

            if event.get("acp_version") != "1.0":
                print(f"  {YELLOW}Line {i}: Unknown version: {event.get('acp_version')}{RESET}")
                warnings += 1
            if event.get("event_type") not in valid_types:
                print(f"  {YELLOW}Line {i}: Unknown type: {event.get('event_type')}{RESET}")
                warnings += 1
            if not str(event.get("agent_id", "")).startswith("agent://"):
                print(f"  {YELLOW}Line {i}: agent_id should start with 'agent://'{RESET}")
                warnings += 1

            valid += 1

    v = colored(str(valid), GREEN)
    inv = colored(str(invalid), RED) if invalid else dim("0")
    w = colored(str(warnings), YELLOW) if warnings else dim("0")
    print(f"\n  Results: {v} valid, {inv} invalid, {w} warnings")

    if invalid > 0:
        sys.exit(1)


def cmd_emit(args: argparse.Namespace) -> None:
    """Send a test ACP event to an endpoint."""
    from maia_sdk import envelope, message
    import httpx

    print(LOGO)
    event = envelope(
        args.from_agent, f"run_cli_{int(time.time())}", "message",
        message(from_agent=args.from_agent, to=args.to, intent=args.intent, content=args.content),
    )
    print(f"  Sending to {colored(args.url, CYAN)}:\n")
    print(f"  {event.model_dump_json(indent=2)}\n")

    try:
        r = httpx.post(args.url, json=event.model_dump(), timeout=10)
        if r.status_code < 300:
            print(f"  {GREEN}Sent ({r.status_code}){RESET}")
        else:
            print(f"  {RED}Server returned {r.status_code}{RESET}")
    except Exception as exc:
        print(f"  {RED}Failed: {exc}{RESET}")


def cmd_info(args: argparse.Namespace) -> None:
    """Show version and environment info."""
    print(LOGO)

    sdk_ver = _try_version("maia_sdk")
    acp_ver = _try_version("maia_acp")

    print(f"  {bold('Versions')}")
    print(f"    CLI:    {__version__}")
    print(f"    SDK:    {sdk_ver}")
    print(f"    ACP:    {acp_ver}")
    print(f"    Python: {sys.version.split()[0]}")
    print()

    frameworks = {"langchain-core": "langchain_core", "crewai": "crewai", "autogen": "autogen"}
    print(f"  {bold('Frameworks')}")
    for name, module in frameworks.items():
        ver = _try_version(module)
        color = GREEN if ver != "not installed" else DIM
        print(f"    {name}: {color}{ver}{RESET}")

    print()
    print(f"  {bold('Links')}")
    print(f"    Docs:   https://docs.maia.ai")
    print(f"    GitHub: https://github.com/maia-ai/maia-sdk")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return events


def _sleep_between(prev_ts: str, curr_ts: str, speed: float) -> None:
    try:
        from datetime import datetime
        prev = datetime.fromisoformat(prev_ts.replace("Z", "+00:00"))
        curr = datetime.fromisoformat(curr_ts.replace("Z", "+00:00"))
        delay = max(0.05, (curr - prev).total_seconds()) / speed
        time.sleep(min(delay, 3.0))
    except (ValueError, TypeError):
        time.sleep(0.3 / speed)


def _try_version(module_name: str) -> str:
    try:
        mod = __import__(module_name)
        return getattr(mod, "__version__", "installed")
    except ImportError:
        return "not installed"
