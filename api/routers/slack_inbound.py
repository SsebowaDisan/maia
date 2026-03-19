"""Slack Inbound Integration — receive commands from Slack and run agents.

Users can type "/maia run weekly-report" in Slack and the agent runs,
posting results back to the Slack channel.

Endpoints:
    POST /api/integrations/slack/commands   — Slack slash command receiver
    POST /api/integrations/slack/events     — Slack Events API receiver
    GET  /api/integrations/slack/status     — integration status
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/integrations/slack", tags=["slack-integration"])


def _verify_slack_signature(request_body: bytes, timestamp: str, signature: str, signing_secret: str) -> bool:
    """Verify that the request came from Slack."""
    if not signing_secret:
        return True  # Dev mode — no verification
    if abs(time.time() - float(timestamp or 0)) > 300:
        return False
    base = f"v0:{timestamp}:{request_body.decode('utf-8')}"
    expected = "v0=" + hmac.new(signing_secret.encode(), base.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _get_signing_secret() -> str:
    import os
    return os.getenv("SLACK_SIGNING_SECRET", "").strip()


@router.post("/commands")
async def handle_slack_command(request: Request) -> dict[str, Any]:
    """Handle Slack slash commands like /maia run weekly-report."""
    body = await request.body()
    form = dict(x.split("=", 1) for x in body.decode().split("&") if "=" in x)

    # URL decode
    from urllib.parse import unquote_plus
    command = unquote_plus(form.get("command", ""))
    text = unquote_plus(form.get("text", "")).strip()
    user_id = unquote_plus(form.get("user_id", ""))
    user_name = unquote_plus(form.get("user_name", ""))
    channel_id = unquote_plus(form.get("channel_id", ""))
    response_url = unquote_plus(form.get("response_url", ""))

    if not text:
        return {
            "response_type": "ephemeral",
            "text": "Usage: /maia <command>\n• `/maia run <workflow-name>` — run a workflow\n• `/maia ask <question>` — ask an agent\n• `/maia status` — check running tasks",
        }

    parts = text.split(None, 1)
    action = parts[0].lower()
    argument = parts[1] if len(parts) > 1 else ""

    if action == "run":
        return await _handle_run(argument, user_id, user_name, channel_id, response_url)
    if action == "ask":
        return await _handle_ask(argument, user_id, user_name, channel_id, response_url)
    if action == "status":
        return _handle_status(user_id)

    return {"response_type": "ephemeral", "text": f"Unknown command: `{action}`. Try `/maia run <workflow>` or `/maia ask <question>`."}


async def _handle_run(workflow_name: str, user_id: str, user_name: str, channel_id: str, response_url: str) -> dict[str, Any]:
    """Run a workflow and post results back to Slack."""
    if not workflow_name:
        return {"response_type": "ephemeral", "text": "Specify a workflow name. Usage: `/maia run weekly-report`"}

    # Find the workflow
    try:
        from api.routers.workflows import _db_list
        workflows = _db_list(user_id)
        match = next(
            (w for w in workflows if workflow_name.lower() in str(w.name or "").lower()),
            None,
        )
        if not match:
            return {"response_type": "ephemeral", "text": f"No workflow found matching '{workflow_name}'."}
    except Exception as exc:
        return {"response_type": "ephemeral", "text": f"Error finding workflow: {exc}"}

    # Acknowledge immediately (Slack requires response within 3s)
    # Run the workflow in background and post results via response_url
    import threading

    def _run_and_respond():
        try:
            from api.services.agents.workflow_executor import execute_workflow
            from api.schemas.workflow_definition import WorkflowDefinitionSchema
            definition = match.definition if hasattr(match, "definition") else {}
            if isinstance(definition, str):
                definition = json.loads(definition)
            wf = WorkflowDefinitionSchema.model_validate(definition)
            outputs = execute_workflow(wf, tenant_id=user_id)
            # Format result
            result_text = "\n".join(f"*{k}*: {str(v)[:500]}" for k, v in outputs.items())
            _post_to_slack(response_url, f"✅ Workflow *{match.name}* completed:\n{result_text[:2500]}")
        except Exception as exc:
            _post_to_slack(response_url, f"❌ Workflow failed: {str(exc)[:500]}")

    threading.Thread(target=_run_and_respond, daemon=True).start()
    return {"response_type": "in_channel", "text": f"⏳ Running workflow *{match.name}*... Results will be posted here."}


async def _handle_ask(question: str, user_id: str, user_name: str, channel_id: str, response_url: str) -> dict[str, Any]:
    """Ask an agent a question and post the answer."""
    if not question:
        return {"response_type": "ephemeral", "text": "Ask a question. Usage: `/maia ask what happened with our ads spend?`"}

    import threading

    def _ask_and_respond():
        try:
            from api.services.agents.runner import run_agent_task
            parts = []
            for chunk in run_agent_task(question, tenant_id=user_id):
                text = chunk.get("text") or chunk.get("content") or ""
                if text:
                    parts.append(str(text))
            answer = "".join(parts)[:2500]
            _post_to_slack(response_url, f"💬 *{question}*\n\n{answer}")
        except Exception as exc:
            _post_to_slack(response_url, f"❌ Failed: {str(exc)[:500]}")

    threading.Thread(target=_ask_and_respond, daemon=True).start()
    return {"response_type": "ephemeral", "text": f"⏳ Thinking about: *{question[:100]}*..."}


def _handle_status(user_id: str) -> dict[str, Any]:
    """Check running tasks."""
    try:
        from api.services.agents.runner import list_active_runs
        runs = list_active_runs(tenant_id=user_id)
        if not runs:
            return {"response_type": "ephemeral", "text": "No active tasks."}
        lines = [f"• {r.get('agent_id', '?')} — {r.get('status', '?')}" for r in runs[:10]]
        return {"response_type": "ephemeral", "text": f"Active tasks:\n" + "\n".join(lines)}
    except Exception:
        return {"response_type": "ephemeral", "text": "No active tasks."}


def _post_to_slack(response_url: str, text: str) -> None:
    """Post a message back to Slack via the response URL."""
    if not response_url:
        return
    try:
        import urllib.request
        data = json.dumps({"response_type": "in_channel", "text": text}).encode()
        req = urllib.request.Request(response_url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.warning("Failed to post to Slack: %s", exc)


@router.get("/status")
def slack_integration_status() -> dict[str, Any]:
    """Check if Slack integration is configured."""
    import os
    return {
        "configured": bool(os.getenv("SLACK_SIGNING_SECRET", "").strip()),
        "bot_token_set": bool(os.getenv("SLACK_BOT_TOKEN", "").strip()),
        "commands_url": "/api/integrations/slack/commands",
    }
