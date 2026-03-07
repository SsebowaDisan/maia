from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

EvidenceSourceType = Literal["web", "pdf", "doc", "sheet", "email", "api", "file", "unknown"]


def _clean_text(value: Any, *, max_len: int = 240) -> str:
    return " ".join(str(value or "").split()).strip()[: max(1, int(max_len))]


def _clamp01(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed != parsed:
        return None
    return max(0.0, min(1.0, parsed))


def _normalize_ref_ids(value: Any, *, max_items: int = 10, max_len: int = 160) -> list[str]:
    rows = value if isinstance(value, list) else [value]
    cleaned: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if isinstance(row, list):
            nested = _normalize_ref_ids(row, max_items=max_items, max_len=max_len)
            for item in nested:
                lowered_nested = item.lower()
                if lowered_nested in seen:
                    continue
                seen.add(lowered_nested)
                cleaned.append(item)
                if len(cleaned) >= max(1, int(max_items)):
                    return cleaned
            continue
        text = _clean_text(row, max_len=max_len)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(text)
        if len(cleaned) >= max(1, int(max_items)):
            break
    return cleaned


def infer_evidence_source_type(
    *,
    source_type: str,
    source_url: str = "",
    file_id: str = "",
) -> EvidenceSourceType:
    normalized = _clean_text(source_type, max_len=48).lower()
    if normalized in {"web", "website", "url"}:
        return "web"
    if normalized in {"pdf"}:
        return "pdf"
    if normalized in {"doc", "document", "docs"}:
        return "doc"
    if normalized in {"sheet", "sheets", "spreadsheet"}:
        return "sheet"
    if normalized in {"email", "gmail", "outlook"}:
        return "email"
    if normalized in {"api"}:
        return "api"
    if normalized in {"file"}:
        return "file"
    if _clean_text(source_url, max_len=512):
        return "web"
    if _clean_text(file_id, max_len=256):
        return "file"
    return "unknown"


class EvidenceRegion(BaseModel):
    x: float
    y: float
    width: float
    height: float

    @classmethod
    def from_payload(cls, value: Any) -> EvidenceRegion | None:
        if not isinstance(value, dict):
            return None
        try:
            raw_x = float(value.get("x", 0.0))
            raw_y = float(value.get("y", 0.0))
            raw_width = float(value.get("width", 0.0))
            raw_height = float(value.get("height", 0.0))
        except Exception:
            return None
        x = max(0.0, min(1.0, raw_x))
        y = max(0.0, min(1.0, raw_y))
        width = max(0.0, min(1.0 - x, raw_width))
        height = max(0.0, min(1.0 - y, raw_height))
        if width < 0.002 or height < 0.002:
            return None
        return cls(
            x=round(x, 6),
            y=round(y, 6),
            width=round(width, 6),
            height=round(height, 6),
        )


class EvidenceItem(BaseModel):
    evidence_id: str
    source_type: EvidenceSourceType = "unknown"
    title: str
    source_name: str
    source_url: str | None = None
    file_id: str | None = None
    page: str | None = None
    extract: str = ""
    unit_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    match_quality: str | None = None
    strength_score: float | None = None
    strength_tier: int | None = None
    confidence: float | None = None
    collected_by: str = "agent.research"
    highlight_boxes: list[EvidenceRegion] = Field(default_factory=list)
    graph_node_ids: list[str] = Field(default_factory=list)
    scene_refs: list[str] = Field(default_factory=list)
    event_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)

    def to_info_panel_payload(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json", exclude_none=True)
        payload["id"] = payload.pop("evidence_id")
        if payload.get("highlight_boxes") and isinstance(payload["highlight_boxes"], list):
            first = payload["highlight_boxes"][0]
            if isinstance(first, dict):
                payload["region"] = first
        return payload

    @classmethod
    def refs_from_metadata(cls, metadata: dict[str, Any], *keys: str) -> list[str]:
        values: list[Any] = []
        for key in keys:
            if key in metadata:
                values.append(metadata.get(key))
        return _normalize_ref_ids(values, max_items=10, max_len=180)

    @classmethod
    def confidence_from(cls, *values: Any) -> float | None:
        for value in values:
            normalized = _clamp01(value)
            if normalized is not None:
                return round(normalized, 6)
        return None


__all__ = [
    "EvidenceItem",
    "EvidenceRegion",
    "EvidenceSourceType",
    "infer_evidence_source_type",
]
