from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class DeliveryRuntime:
    step: int
    started_at: str
    tool_id: str = "mailer.report_send"
    title: str = "Send report email (server-side)"
