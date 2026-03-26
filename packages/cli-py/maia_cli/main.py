"""Maia CLI — entry point and argument parser.

Usage:
    maia stream <url>     Connect to an ACP stream and render events live
    maia replay <file>    Replay a recorded JSONL run file
    maia validate <file>  Validate ACP events against the schema
    maia emit <url>       Send a test ACP event to a stream
    maia init <name>      Scaffold a new ACP project
    maia serve <file>     Serve a JSONL file as a local SSE endpoint
    maia info             Show SDK version and environment info
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

from maia_cli import __version__
from maia_cli.colors import GREEN, CYAN, YELLOW, RESET, colored, dim
from maia_cli.commands import (
    LOGO,
    cmd_stream,
    cmd_replay,
    cmd_validate,
    cmd_emit,
    cmd_info,
)


def cli() -> None:
    """Entry point for the `maia` command."""
    parser = argparse.ArgumentParser(
        prog="maia",
        description="Maia CLI \u2014 stream, replay, and validate ACP agent events.",
    )
    parser.add_argument("--version", action="version", version=f"maia-cli {__version__}")
    sub = parser.add_subparsers(dest="command")

    # maia stream
    p = sub.add_parser("stream", help="Connect to a live ACP stream")
    p.add_argument("url", help="SSE endpoint URL")
    p.add_argument("--raw", action="store_true", help="Raw JSON output")
    p.add_argument("--save", metavar="FILE", help="Save events to JSONL")

    # maia replay
    p = sub.add_parser("replay", help="Replay a recorded JSONL run")
    p.add_argument("file", help="JSONL events file")
    p.add_argument("--speed", type=float, default=1.0, help="Playback speed")
    p.add_argument("--raw", action="store_true")

    # maia validate
    p = sub.add_parser("validate", help="Validate ACP events")
    p.add_argument("file", help="JSONL events file")

    # maia emit
    p = sub.add_parser("emit", help="Send a test ACP event")
    p.add_argument("url", help="POST endpoint")
    p.add_argument("--from", dest="from_agent", default="agent://cli-test")
    p.add_argument("--to", default="agent://broadcast")
    p.add_argument("--intent", default="propose")
    p.add_argument("--content", default="Hello from Maia CLI!")

    # maia init
    p = sub.add_parser("init", help="Scaffold a new ACP project")
    p.add_argument("name", nargs="?", default="my-acp-agent")

    # maia serve
    p = sub.add_parser("serve", help="Serve JSONL as local SSE")
    p.add_argument("file", help="JSONL events file")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--speed", type=float, default=1.0)

    # maia info
    sub.add_parser("info", help="Show version info")

    args = parser.parse_args()
    if not args.command:
        print(LOGO)
        parser.print_help()
        return

    dispatch = {
        "stream": cmd_stream,
        "replay": cmd_replay,
        "validate": cmd_validate,
        "emit": cmd_emit,
        "init": cmd_init,
        "serve": cmd_serve,
        "info": cmd_info,
    }

    try:
        dispatch[args.command](args)
    except KeyboardInterrupt:
        print(f"\n{dim('Interrupted.')}")
    except Exception as exc:
        print(f"\033[31mError: {exc}\033[0m", file=sys.stderr)
        sys.exit(1)


# ── Init & Serve live here (unique I/O, not in commands.py) ───────────────────

def cmd_init(args: argparse.Namespace) -> None:
    """Scaffold a new ACP project."""
    name = args.name
    d = Path(name)

    print(LOGO)
    print(f"  Creating project: {colored(name, CYAN)}\n")

    if d.exists():
        print(f"  {YELLOW}Directory '{name}' already exists.{RESET}")
        return

    d.mkdir(parents=True)
    (d / "events").mkdir()

    (d / "agent.py").write_text(
        f"\"\"\"ACP Agent \u2014 {name}\"\"\"\n"
        "from maia_sdk import ACPClient, message, activity, envelope\n\n"
        f"client = ACPClient(agent_id=\"agent://{name}\")\n\n\n"
        "def run(query: str):\n"
        "    run_id = f\"run_{int(__import__('time').time())}\"\n"
        "    yield envelope(\n"
        "        client.agent_id, run_id, \"event\",\n"
        "        activity(agent_id=client.agent_id, activity_type=\"thinking\", detail=f\"Processing: {query}\"),\n"
        "    )\n"
        "    result = f\"Result for: {query}\"\n"
        "    yield envelope(\n"
        "        client.agent_id, run_id, \"message\",\n"
        "        message(from_agent=client.agent_id, to=\"agent://user\", intent=\"propose\", content=result),\n"
        "    )\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    for event in run(\"Hello world\"):\n"
        "        print(event.model_dump_json())\n",
        encoding="utf-8",
    )

    (d / "server.py").write_text(
        "\"\"\"SSE server for ACP events.\"\"\"\n"
        "from http.server import HTTPServer, BaseHTTPRequestHandler\n"
        "from agent import run\n\n\n"
        "class Handler(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        if self.path == \"/acp/events\":\n"
        "            self.send_response(200)\n"
        "            self.send_header(\"Content-Type\", \"text/event-stream\")\n"
        "            self.send_header(\"Access-Control-Allow-Origin\", \"*\")\n"
        "            self.end_headers()\n"
        "            for event in run(\"Sample query\"):\n"
        "                self.wfile.write(f\"data: {event.model_dump_json()}\\n\\n\".encode())\n"
        "                self.wfile.flush()\n"
        "            self.wfile.write(b\"data: [DONE]\\n\\n\")\n"
        "        else:\n"
        "            self.send_error(404)\n"
        "    def log_message(self, *a): pass\n\n\n"
        "if __name__ == \"__main__\":\n"
        "    print(\"ACP server: http://localhost:8765/acp/events\")\n"
        "    HTTPServer((\"\", 8765), Handler).serve_forever()\n",
        encoding="utf-8",
    )

    print(f"  {GREEN}Created:{RESET}")
    print(f"    {name}/agent.py   \u2014 your agent")
    print(f"    {name}/server.py  \u2014 SSE server")
    print(f"    {name}/events/    \u2014 recorded runs")
    print(f"\n  {dim('Next: cd ' + name + ' && pip install maia-sdk && python agent.py')}")


def cmd_serve(args: argparse.Namespace) -> None:
    """Serve a JSONL file as a local SSE endpoint."""
    path = Path(args.file)
    if not path.exists():
        print(f"\033[31mFile not found: {args.file}\033[0m", file=sys.stderr)
        sys.exit(1)

    events: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s:
                try:
                    events.append(json.loads(s))
                except json.JSONDecodeError:
                    continue

    speed = args.speed
    port = args.port

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self_inner) -> None:
            if self_inner.path != "/acp/events":
                self_inner.send_error(404)
                return
            self_inner.send_response(200)
            self_inner.send_header("Content-Type", "text/event-stream")
            self_inner.send_header("Cache-Control", "no-cache")
            self_inner.send_header("Access-Control-Allow-Origin", "*")
            self_inner.end_headers()

            prev_ts = None
            for evt in events:
                ts = evt.get("timestamp", "")
                if prev_ts and ts:
                    from maia_cli.commands import _sleep_between
                    _sleep_between(prev_ts, ts, speed)
                prev_ts = ts
                data = json.dumps(evt, default=str)
                self_inner.wfile.write(f"data: {data}\n\n".encode())
                self_inner.wfile.flush()
            self_inner.wfile.write(b"data: [DONE]\n\n")

        def log_message(self_inner, *a: Any) -> None:
            pass

    print(LOGO)
    print(f"  Serving {colored(str(path), CYAN)} ({len(events)} events) at {speed}x")
    print(f"  {GREEN}http://localhost:{port}/acp/events{RESET}\n")
    print(f"  {dim('Press Ctrl+C to stop')}")

    HTTPServer(("", port), Handler).serve_forever()


if __name__ == "__main__":
    cli()
