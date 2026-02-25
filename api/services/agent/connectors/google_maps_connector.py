from __future__ import annotations

import os
from typing import Any

from .base import BaseConnector, ConnectorError, ConnectorHealth


class GoogleMapsConnector(BaseConnector):
    connector_id = "google_maps"

    def _api_key(self) -> str:
        key = (
            str(os.getenv("GOOGLE_MAPS_API_KEY", "")).strip()
            or str(os.getenv("GOOGLE_PLACES_API_KEY", "")).strip()
            or str(os.getenv("GOOGLE_GEO_API_KEY", "")).strip()
            or str(self.settings.get("GOOGLE_MAPS_API_KEY") or "").strip()
            or str(self.settings.get("GOOGLE_PLACES_API_KEY") or "").strip()
            or str(self.settings.get("GOOGLE_GEO_API_KEY") or "").strip()
        )
        if not key:
            raise ConnectorError(
                "GOOGLE_MAPS_API_KEY (or GOOGLE_PLACES_API_KEY / GOOGLE_GEO_API_KEY) is required."
            )
        return key

    def health_check(self) -> ConnectorHealth:
        try:
            self._api_key()
        except ConnectorError as exc:
            return ConnectorHealth(self.connector_id, False, str(exc))
        return ConnectorHealth(self.connector_id, True, "configured")

    def places_text_search(
        self,
        *,
        query: str,
        language: str = "en",
    ) -> dict[str, Any]:
        key = self._api_key()
        payload = self.request_json(
            method="GET",
            url="https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={
                "query": query,
                "language": language,
                "key": key,
            },
            timeout_seconds=25,
        )
        if not isinstance(payload, dict):
            raise ConnectorError("Google Places API returned invalid payload.")
        return payload

    def geocode(self, *, address: str, language: str = "en") -> dict[str, Any]:
        key = self._api_key()
        payload = self.request_json(
            method="GET",
            url="https://maps.googleapis.com/maps/api/geocode/json",
            params={
                "address": address,
                "language": language,
                "key": key,
            },
            timeout_seconds=25,
        )
        if not isinstance(payload, dict):
            raise ConnectorError("Google Geocoding API returned invalid payload.")
        return payload

    def distance_matrix(
        self,
        *,
        origins: list[str],
        destinations: list[str],
        mode: str = "driving",
        language: str = "en",
    ) -> dict[str, Any]:
        if not origins or not destinations:
            raise ConnectorError("Distance Matrix requires at least one origin and one destination.")
        key = self._api_key()
        payload = self.request_json(
            method="GET",
            url="https://maps.googleapis.com/maps/api/distancematrix/json",
            params={
                "origins": "|".join(origins),
                "destinations": "|".join(destinations),
                "mode": mode,
                "language": language,
                "key": key,
            },
            timeout_seconds=25,
        )
        if not isinstance(payload, dict):
            raise ConnectorError("Google Distance Matrix API returned invalid payload.")
        return payload
