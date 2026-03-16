"""B5-03 — Error classification and alerting.

Responsibility: classify run errors into known categories and evaluate
alert rules, sending notifications when thresholds are breached.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Literal, Optional, Sequence

from sqlmodel import Field, Session, SQLModel, select

from ktem.db.engine import engine

logger = logging.getLogger(__name__)

ErrorClass = Literal[
    "tool_timeout",
    "credential_expired",
    "llm_error",
    "gate_rejected",
    "context_overflow",
    "computer_use_step_limit",
    "computer_use_session_error",
    "unknown",
]


# ── Error classification ───────────────────────────────────────────────────────

_CLASSIFIERS: list[tuple[str, ErrorClass]] = [
    ("timed out",                 "tool_timeout"),
    ("timeout",                   "tool_timeout"),
    ("credential",                "credential_expired"),
    ("token expired",             "credential_expired"),
    ("401",                       "credential_expired"),
    ("gate_rejected",             "gate_rejected"),
    ("rejected",                  "gate_rejected"),
    ("context length",            "context_overflow"),
    ("context_length_exceeded",   "context_overflow"),
    ("max_steps",                 "computer_use_step_limit"),
    ("step limit",                "computer_use_step_limit"),
    ("computer_use",              "computer_use_session_error"),
    ("browser session",           "computer_use_session_error"),
    ("overloaded",                "llm_error"),
    ("rate_limit",                "llm_error"),
]


def classify_error(error_message: str) -> ErrorClass:
    """Map an error string to a known ErrorClass."""
    lower = (error_message or "").lower()
    for keyword, klass in _CLASSIFIERS:
        if keyword in lower:
            return klass
    return "unknown"


# ── Alert rules ────────────────────────────────────────────────────────────────

class AlertRule(SQLModel, table=True):
    __tablename__ = "maia_alert_rule"

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str = Field(index=True)
    error_class: str = ""  # empty = any
    error_rate_threshold: float = 0.2  # fraction 0.0–1.0
    window_seconds: int = 3600
    notification_channel: str = "log"  # "log" | "slack" | "email"
    notification_target: str = ""  # channel ID / email address
    enabled: bool = True
    last_fired_at: Optional[float] = Field(default=None)


def _ensure_tables() -> None:
    SQLModel.metadata.create_all(engine)


def set_alert(
    tenant_id: str,
    *,
    error_class: str = "",
    error_rate_threshold: float = 0.2,
    window_seconds: int = 3600,
    notification_channel: str = "log",
    notification_target: str = "",
) -> AlertRule:
    _ensure_tables()
    rule = AlertRule(
        tenant_id=tenant_id,
        error_class=error_class,
        error_rate_threshold=error_rate_threshold,
        window_seconds=window_seconds,
        notification_channel=notification_channel,
        notification_target=notification_target,
    )
    with Session(engine) as session:
        session.add(rule)
        session.commit()
        session.refresh(rule)
    return rule


def check_alert_rules(tenant_id: str) -> list[dict[str, Any]]:
    """Evaluate all rules for the tenant.  Returns list of fired alerts."""
    _ensure_tables()
    with Session(engine) as session:
        rules = session.exec(
            select(AlertRule)
            .where(AlertRule.tenant_id == tenant_id)
            .where(AlertRule.enabled == True)  # noqa: E712
        ).all()

    fired: list[dict[str, Any]] = []
    for rule in rules:
        rate, error_count, total = _compute_error_rate(tenant_id, rule)
        if total == 0:
            continue
        if rate >= rule.error_rate_threshold:
            alert = {
                "rule_id": rule.id,
                "tenant_id": tenant_id,
                "error_class": rule.error_class or "any",
                "error_rate": round(rate, 4),
                "error_count": error_count,
                "total_runs": total,
                "window_seconds": rule.window_seconds,
            }
            fired.append(alert)
            _send_notification(rule, alert)
            with Session(engine) as session:
                rec = session.get(AlertRule, rule.id)
                if rec:
                    rec.last_fired_at = time.time()
                    session.add(rec)
                    session.commit()

    return fired


# ── Private ────────────────────────────────────────────────────────────────────

def _compute_error_rate(tenant_id: str, rule: AlertRule) -> tuple[float, int, int]:
    """Return (rate, error_count, total) for the rule's window."""
    from api.services.observability.telemetry import query_runs

    since = time.time() - rule.window_seconds
    runs = query_runs(tenant_id, start_after=since, limit=10_000)
    total = len(runs)
    if total == 0:
        return 0.0, 0, 0

    errors = [
        r for r in runs
        if r.status == "failed" and (
            not rule.error_class
            or classify_error(r.error or "") == rule.error_class
        )
    ]
    return len(errors) / total, len(errors), total


def _send_notification(rule: AlertRule, alert: dict[str, Any]) -> None:
    channel = rule.notification_channel
    if channel == "log":
        logger.warning("ALERT fired: %s", alert)
    elif channel == "slack":
        _send_slack(rule.notification_target, alert)
    elif channel == "email":
        _send_email(rule.notification_target, alert)


def _send_email(recipient: str, alert: dict[str, Any]) -> None:
    """Send an alert notification via SMTP.

    Reads connection details from env vars:
      MAIA_SMTP_HOST      (default: localhost)
      MAIA_SMTP_PORT      (default: 587)
      MAIA_SMTP_USER      (optional — omit for unauthenticated relay)
      MAIA_SMTP_PASSWORD  (optional)
      MAIA_SMTP_FROM      (default: maia-alerts@localhost)
      MAIA_SMTP_USE_TLS   (default: "true")
    """
    if not recipient:
        logger.warning("Email alert has no recipient configured — skipping")
        return
    try:
        import os
        import smtplib
        from email.mime.text import MIMEText

        host = os.environ.get("MAIA_SMTP_HOST", "localhost")
        port = int(os.environ.get("MAIA_SMTP_PORT", "587"))
        user = os.environ.get("MAIA_SMTP_USER", "")
        password = os.environ.get("MAIA_SMTP_PASSWORD", "")
        from_addr = os.environ.get("MAIA_SMTP_FROM", "maia-alerts@localhost")
        use_tls = os.environ.get("MAIA_SMTP_USE_TLS", "true").lower() not in ("0", "false", "no")

        subject = (
            f"Maia Alert — error rate {alert['error_rate'] * 100:.1f}% "
            f"for class '{alert['error_class']}'"
        )
        body = (
            f"Maia Alert\n\n"
            f"Error class : {alert['error_class']}\n"
            f"Error rate  : {alert['error_rate'] * 100:.1f}%\n"
            f"Errors      : {alert['error_count']} / {alert['total_runs']} runs\n"
            f"Window      : {alert['window_seconds'] // 60} minutes\n"
            f"Tenant      : {alert.get('tenant_id', '')}\n"
        )
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = recipient

        smtp_cls = smtplib.SMTP_SSL if (use_tls and port == 465) else smtplib.SMTP
        with smtp_cls(host, port, timeout=10) as server:
            if use_tls and port != 465:
                server.starttls()
            if user:
                server.login(user, password)
            server.sendmail(from_addr, [recipient], msg.as_string())

        logger.info("Alert email sent to %s", recipient)
    except Exception as exc:
        logger.warning("Email alert send failed (recipient=%s): %s", recipient, exc)


def _send_slack(channel: str, alert: dict[str, Any]) -> None:
    if not channel:
        return
    try:
        import urllib.request, os

        token = os.environ.get("MAIA_ALERT_SLACK_TOKEN", "")
        if not token:
            logger.warning("No MAIA_ALERT_SLACK_TOKEN set — cannot send Slack alert")
            return
        text = (
            f":warning: *Maia Alert*\n"
            f"Error rate {alert['error_rate'] * 100:.1f}% for class `{alert['error_class']}` "
            f"in the last {alert['window_seconds'] // 60}min "
            f"({alert['error_count']}/{alert['total_runs']} runs)"
        )
        payload = json.dumps({"channel": channel, "text": text}).encode()
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:
        logger.debug("Slack alert send failed: %s", exc)
