from __future__ import annotations

from typing import Any

import httpx

from api.services.llamacpp.errors import LlamaCppError

DEFAULT_LLAMACPP_PORT = 8082
DEFAULT_LLAMACPP_HOST = "127.0.0.1"

_DEFAULT_TIMEOUT = httpx.Timeout(15.0)


def build_base_url(host: str = DEFAULT_LLAMACPP_HOST, port: int = DEFAULT_LLAMACPP_PORT) -> str:
    host = str(host or DEFAULT_LLAMACPP_HOST).strip()
    return f"http://{host}:{int(port)}"


def openai_compatible_base_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/v1"


class LlamaCppService:
    """HTTP client for the llama-cpp-python OpenAI-compatible server."""

    def __init__(self, *, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _get_json(self, path: str) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=_DEFAULT_TIMEOUT) as client:
                response = client.get(url)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise LlamaCppError(
                code="llamacpp_unreachable",
                message="Cannot connect to llama-cpp-python server. Start the server and retry.",
                status_code=503,
                details={"url": self.base_url},
            ) from exc
        except httpx.TimeoutException as exc:
            raise LlamaCppError(
                code="llamacpp_timeout",
                message="llama-cpp-python server request timed out.",
                status_code=504,
                details={"path": path},
            ) from exc
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:240] if exc.response is not None else ""
            status = int(exc.response.status_code) if exc.response is not None else 502
            raise LlamaCppError(
                code="llamacpp_http_error",
                message=f"llama-cpp-python server returned status {status}.",
                status_code=status if 400 <= status <= 599 else 502,
                details={"response": body, "path": path},
            ) from exc
        except httpx.RequestError as exc:
            raise LlamaCppError(
                code="llamacpp_request_error",
                message="llama-cpp-python server request failed.",
                status_code=502,
                details={"error": str(exc), "path": path},
            ) from exc

        try:
            parsed = response.json()
        except ValueError as exc:
            raise LlamaCppError(
                code="llamacpp_invalid_json",
                message="llama-cpp-python server returned invalid JSON.",
                status_code=502,
                details={"path": path},
            ) from exc
        if not isinstance(parsed, dict):
            raise LlamaCppError(
                code="llamacpp_invalid_payload",
                message="llama-cpp-python server returned an unexpected payload.",
                status_code=502,
                details={"path": path},
            )
        return parsed

    def is_reachable(self) -> bool:
        """Return True if the server is up and healthy."""
        try:
            self._get_json("/health")
            return True
        except LlamaCppError:
            return False

    def list_models(self) -> list[dict[str, Any]]:
        """Return models reported by /v1/models."""
        try:
            payload = self._get_json("/v1/models")
        except LlamaCppError:
            return []
        data = payload.get("data")
        if not isinstance(data, list):
            return []
        models = []
        for item in data:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if not model_id:
                continue
            models.append({"id": model_id, "object": str(item.get("object") or "model")})
        return models
