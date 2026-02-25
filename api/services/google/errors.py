from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GoogleServiceError(RuntimeError):
    code: str
    message: str
    status_code: int = 400
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_detail(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class GoogleOAuthError(GoogleServiceError):
    pass


class GoogleTokenError(GoogleServiceError):
    pass


class GoogleApiError(GoogleServiceError):
    pass

