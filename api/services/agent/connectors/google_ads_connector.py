from __future__ import annotations

from typing import Any

from .base import BaseConnector, ConnectorError, ConnectorHealth


class GoogleAdsConnector(BaseConnector):
    connector_id = "google_ads"

    def _developer_token(self) -> str:
        token = self._read_secret("GOOGLE_ADS_DEVELOPER_TOKEN")
        if not token:
            raise ConnectorError("GOOGLE_ADS_DEVELOPER_TOKEN is not configured.")
        return token

    def _customer_id(self) -> str:
        customer_id = self._read_secret("GOOGLE_ADS_CUSTOMER_ID").replace("-", "")
        if not customer_id:
            raise ConnectorError("GOOGLE_ADS_CUSTOMER_ID is not configured.")
        return customer_id

    def _access_token(self) -> str:
        token = self._read_secret("GOOGLE_ADS_ACCESS_TOKEN")
        if not token:
            raise ConnectorError("GOOGLE_ADS_ACCESS_TOKEN is not configured.")
        return token

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "developer-token": self._developer_token(),
            "Content-Type": "application/json",
        }
        login_customer = self._read_secret("GOOGLE_ADS_LOGIN_CUSTOMER_ID").replace("-", "")
        if login_customer:
            headers["login-customer-id"] = login_customer
        return headers

    def health_check(self) -> ConnectorHealth:
        try:
            self._developer_token()
            self._customer_id()
            self._access_token()
        except ConnectorError as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        return ConnectorHealth(self.connector_id, True, "configured")

    def _extract_metrics(self, response_payload: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        chunks = response_payload if isinstance(response_payload, list) else [response_payload]
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            for result in chunk.get("results", []) or []:
                if not isinstance(result, dict):
                    continue
                metrics = result.get("metrics") or {}
                campaign = result.get("campaign") or {}
                cost_micros_raw = metrics.get("costMicros")
                try:
                    cost_micros = float(cost_micros_raw)
                except (TypeError, ValueError):
                    cost_micros = 0.0
                rows.append(
                    {
                        "campaign_id": campaign.get("id"),
                        "campaign_name": campaign.get("name"),
                        "impressions": metrics.get("impressions", 0),
                        "clicks": metrics.get("clicks", 0),
                        "cost": cost_micros / 1_000_000.0,
                        "conversions": metrics.get("conversions", 0),
                    }
                )
        return rows

    def fetch_metrics(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("metrics"):
            # Keep manual payload mode for deterministic local tests and demo runs.
            return {
                "provider": "google_ads",
                "mode": "local_payload",
                "metrics": payload.get("metrics", []),
            }

        health = self.health_check()
        if not health.ok:
            raise ConnectorError(health.message)

        query = str(payload.get("query") or "").strip()
        if not query:
            query = (
                "SELECT campaign.id, campaign.name, metrics.impressions, metrics.clicks, "
                "metrics.cost_micros, metrics.conversions "
                "FROM campaign "
                "WHERE segments.date DURING LAST_30_DAYS "
                "LIMIT 100"
            )

        api_version = str(payload.get("api_version") or "v18").strip() or "v18"
        customer_id = self._customer_id()
        url = (
            f"https://googleads.googleapis.com/{api_version}/customers/"
            f"{customer_id}/googleAds:searchStream"
        )
        response = self.request_json(
            method="POST",
            url=url,
            headers=self._headers(),
            payload={"query": query},
            timeout_seconds=int(payload.get("timeout_seconds") or 40),
        )
        metrics = self._extract_metrics(response)
        return {
            "provider": "google_ads",
            "mode": "api",
            "query": query,
            "metrics": metrics,
            "row_count": len(metrics),
        }
