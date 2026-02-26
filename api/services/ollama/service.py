from __future__ import annotations

import json
from typing import Any, Callable

import httpx

from api.services.ollama.errors import OllamaError

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
_STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=30.0)
_DEFAULT_TIMEOUT = httpx.Timeout(15.0)


def normalize_ollama_base_url(value: str | None) -> str:
    base = str(value or DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"http://{base}"
    return base


def openai_compatible_base_url(ollama_base_url: str) -> str:
    return f"{normalize_ollama_base_url(ollama_base_url)}/v1"


class OllamaService:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = normalize_ollama_base_url(base_url)
        self.transport = transport

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=_DEFAULT_TIMEOUT, transport=self.transport) as client:
                response = client.request(method, url, json=payload)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise OllamaError(
                code="ollama_unreachable",
                message="Cannot connect to Ollama. Start Ollama and retry.",
                status_code=503,
                details={"url": self.base_url},
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaError(
                code="ollama_timeout",
                message="Ollama request timed out.",
                status_code=504,
                details={"path": path},
            ) from exc
        except httpx.HTTPStatusError as exc:
            body_text = exc.response.text[:240] if exc.response is not None else ""
            status = int(exc.response.status_code) if exc.response is not None else 502
            raise OllamaError(
                code="ollama_http_error",
                message=f"Ollama request failed with status {status}.",
                status_code=status if 400 <= status <= 599 else 502,
                details={"response": body_text, "path": path},
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaError(
                code="ollama_request_error",
                message="Ollama request failed.",
                status_code=502,
                details={"error": str(exc), "path": path},
            ) from exc

        try:
            parsed = response.json()
        except ValueError as exc:
            raise OllamaError(
                code="ollama_invalid_json",
                message="Ollama returned invalid JSON.",
                status_code=502,
                details={"path": path},
            ) from exc

        if not isinstance(parsed, dict):
            raise OllamaError(
                code="ollama_invalid_payload",
                message="Ollama returned an invalid payload.",
                status_code=502,
                details={"path": path},
            )
        return parsed

    def get_version(self) -> str | None:
        payload = self._request_json(method="GET", path="/api/version")
        version = payload.get("version")
        if version is None:
            return None
        return str(version).strip() or None

    def list_models(self) -> list[dict[str, Any]]:
        payload = self._request_json(method="GET", path="/api/tags")
        rows = payload.get("models")
        if not isinstance(rows, list):
            return []

        models: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            models.append(
                {
                    "name": name,
                    "size": int(row.get("size") or 0),
                    "digest": str(row.get("digest") or ""),
                    "modified_at": str(row.get("modified_at") or ""),
                    "details": row.get("details") if isinstance(row.get("details"), dict) else {},
                }
            )

        models.sort(key=lambda item: item.get("name", ""))
        return models

    def pull_model(
        self,
        *,
        model: str,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        model_name = " ".join(str(model or "").split()).strip()
        if not model_name:
            raise OllamaError(
                code="ollama_model_missing",
                message="Model name is required.",
                status_code=400,
            )

        url = f"{self.base_url}/api/pull"
        request_payload = {
            "model": model_name,
            "stream": True,
        }
        latest_status = "starting"
        latest_percent = 0.0
        updates = 0

        try:
            with httpx.Client(timeout=_STREAM_TIMEOUT, transport=self.transport) as client:
                with client.stream("POST", url, json=request_payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(chunk, dict):
                            continue

                        status = str(chunk.get("status") or "").strip() or latest_status
                        latest_status = status
                        total = int(chunk.get("total") or 0)
                        completed = int(chunk.get("completed") or 0)
                        if total > 0 and completed >= 0:
                            latest_percent = min(100.0, max(0.0, (completed / total) * 100.0))
                        elif status.lower() == "success":
                            latest_percent = 100.0

                        update = {
                            "status": latest_status,
                            "percent": round(latest_percent, 1),
                            "total": total,
                            "completed": completed,
                        }
                        updates += 1
                        if on_progress:
                            on_progress(update)
        except httpx.ConnectError as exc:
            raise OllamaError(
                code="ollama_unreachable",
                message="Cannot connect to Ollama. Start Ollama and retry.",
                status_code=503,
                details={"url": self.base_url},
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaError(
                code="ollama_pull_timeout",
                message="Ollama pull timed out.",
                status_code=504,
                details={"model": model_name},
            ) from exc
        except httpx.HTTPStatusError as exc:
            body_text = exc.response.text[:240] if exc.response is not None else ""
            status = int(exc.response.status_code) if exc.response is not None else 502
            raise OllamaError(
                code="ollama_pull_http_error",
                message=f"Ollama pull failed with status {status}.",
                status_code=status if 400 <= status <= 599 else 502,
                details={"response": body_text, "model": model_name},
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaError(
                code="ollama_pull_request_error",
                message="Ollama pull request failed.",
                status_code=502,
                details={"error": str(exc), "model": model_name},
            ) from exc

        return {
            "model": model_name,
            "status": latest_status,
            "percent": round(latest_percent, 1),
            "updates": updates,
            "completed": latest_percent >= 100.0 or latest_status.lower() == "success",
        }
