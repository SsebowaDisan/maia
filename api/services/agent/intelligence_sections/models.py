from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaskIntelligence:
    objective: str
    target_url: str
    target_host: str
    delivery_email: str
    requires_delivery: bool
    requires_web_inspection: bool
    requested_report: bool
    preferred_tone: str = ""
    preferred_format: str = ""
    intent_tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "target_url": self.target_url,
            "target_host": self.target_host,
            "delivery_email": self.delivery_email,
            "requires_delivery": self.requires_delivery,
            "requires_web_inspection": self.requires_web_inspection,
            "requested_report": self.requested_report,
            "preferred_tone": self.preferred_tone,
            "preferred_format": self.preferred_format,
            "intent_tags": list(self.intent_tags),
        }
