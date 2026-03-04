from __future__ import annotations

import os
import time
from typing import Any

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal CI env
    httpx = None  # type: ignore[assignment]

from api.services.search.errors import BraveSearchError

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
BRAVE_DEFAULT_COUNTRY = "BE"
BRAVE_DEFAULT_SAFESEARCH = "moderate"
BRAVE_MAX_RETRIES = 2
BRAVE_TIMEOUT_SECONDS = 20


def _normalize_country(country: str) -> str:
    value = str(country or BRAVE_DEFAULT_COUNTRY).strip().upper()
    if len(value) != 2:
        return BRAVE_DEFAULT_COUNTRY
    return value


def _normalize_safesearch(safesearch: str) -> str:
    value = str(safesearch or BRAVE_DEFAULT_SAFESEARCH).strip().lower()
    if value not in {"off", "moderate", "strict"}:
        return BRAVE_DEFAULT_SAFESEARCH
    return value


def _clean_query(query: str) -> str:
    return " ".join(str(query or "").split())


class BraveSearchService:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_seconds: int = BRAVE_TIMEOUT_SECONDS,
        max_retries: int = BRAVE_MAX_RETRIES,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if httpx is None:
            raise BraveSearchError(
                code="brave_dependency_missing",
                message="Brave search dependency is missing: install httpx.",
                status_code=500,
            )
        self.api_key = str(api_key or os.getenv("BRAVE_SEARCH_API_KEY", "")).strip()
        self.timeout_seconds = max(5, int(timeout_seconds))
        self.max_retries = max(0, int(max_retries))
        self.transport = transport
        if not self.api_key:
            raise BraveSearchError(
                code="brave_api_key_missing",
                message="BRAVE_SEARCH_API_KEY is not configured.",
                status_code=400,
            )

    @staticmethod
    def is_configured(api_key: str | None = None) -> bool:
        value = str(api_key or os.getenv("BRAVE_SEARCH_API_KEY", "")).strip()
        return bool(value)

    def _request(self, *, query: str, count: int, offset: int, country: str, safesearch: str) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": query,
            "count": max(1, min(int(count), 20)),
            "offset": max(0, min(int(offset), 200)),
            "country": _normalize_country(country),
            "safesearch": _normalize_safesearch(safesearch),
            "search_lang": "en",
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with httpx.Client(
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                ) as client:
                    response = client.get(
                        BRAVE_SEARCH_URL,
                        headers=headers,
                        params=params,
                    )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    time.sleep(0.35 * (attempt + 1))
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise BraveSearchError(
                        code="brave_invalid_payload",
                        message="Brave Search returned invalid payload.",
                        status_code=502,
                    )
                return payload
            except BraveSearchError:
                raise
            except httpx.HTTPStatusError as exc:
                status_code = int(exc.response.status_code)
                if status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    time.sleep(0.35 * (attempt + 1))
                    continue
                response_text = exc.response.text[:240] if exc.response is not None else ""
                raise BraveSearchError(
                    code="brave_http_error",
                    message=f"Brave Search request failed with status {status_code}.",
                    status_code=status_code if 400 <= status_code <= 599 else 502,
                    details={"response": response_text},
                ) from exc
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.35 * (attempt + 1))
                    continue
                raise BraveSearchError(
                    code="brave_timeout",
                    message="Brave Search request timed out.",
                    status_code=504,
                ) from exc
            except httpx.RequestError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(0.35 * (attempt + 1))
                    continue
                raise BraveSearchError(
                    code="brave_request_error",
                    message="Brave Search request failed.",
                    status_code=502,
                    details={"error": str(exc)},
                ) from exc
            except ValueError as exc:
                raise BraveSearchError(
                    code="brave_invalid_json",
                    message="Brave Search response was not valid JSON.",
                    status_code=502,
                ) from exc
        raise BraveSearchError(
            code="brave_request_failed",
            message="Brave Search request failed after retries.",
            status_code=502,
            details={"error": str(last_error) if last_error else ""},
        )

    @staticmethod
    def _normalize_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
        web = payload.get("web")
        if not isinstance(web, dict):
            return []
        rows = web.get("results")
        if not isinstance(rows, list):
            return []

        normalized: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            url = str(row.get("url") or "").strip()
            description = str(row.get("description") or "").strip()
            age = str(row.get("age") or "").strip()
            profile = row.get("profile") or {}
            source = str(profile.get("name") or profile.get("hostname") or "").strip() if isinstance(profile, dict) else ""
            if not title and url:
                title = url
            if not url:
                continue
            normalized.append(
                {
                    "title": title,
                    "url": url,
                    "description": description,
                    "source": source or None,
                    "age": age or None,
                }
            )
        return normalized

    def web_search(
        self,
        *,
        query: str,
        count: int = 10,
        offset: int = 0,
        country: str = BRAVE_DEFAULT_COUNTRY,
        safesearch: str = BRAVE_DEFAULT_SAFESEARCH,
    ) -> dict[str, Any]:
        clean_query = _clean_query(query)
        if not clean_query:
            raise BraveSearchError(
                code="brave_query_missing",
                message="Search query is required.",
                status_code=400,
            )
        payload = self._request(
            query=clean_query,
            count=count,
            offset=offset,
            country=country,
            safesearch=safesearch,
        )
        results = self._normalize_results(payload)
        return {
            "provider": "brave",
            "query": clean_query,
            "count": max(1, min(int(count), 20)),
            "offset": max(0, int(offset)),
            "country": _normalize_country(country),
            "safesearch": _normalize_safesearch(safesearch),
            "total": len(results),
            "results": results,
            "raw": payload,
        }

    def site_search(
        self,
        *,
        domain: str,
        query: str,
        count: int = 10,
        offset: int = 0,
        country: str = BRAVE_DEFAULT_COUNTRY,
        safesearch: str = BRAVE_DEFAULT_SAFESEARCH,
    ) -> dict[str, Any]:
        clean_domain = str(domain or "").strip()
        clean_query = _clean_query(query)
        if not clean_domain:
            raise BraveSearchError(
                code="brave_domain_missing",
                message="Domain is required for site search.",
                status_code=400,
            )
        scoped_query = f"site:{clean_domain} {clean_query}".strip()
        result = self.web_search(
            query=scoped_query,
            count=count,
            offset=offset,
            country=country,
            safesearch=safesearch,
        )
        result["domain"] = clean_domain
        return result
