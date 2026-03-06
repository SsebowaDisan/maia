from __future__ import annotations

from typing import Any


def _bounded_percent(value: float, *, minimum: float, maximum: float) -> float:
    return max(float(minimum), min(float(maximum), float(value)))


def cursor_payload(
    *,
    lane: str,
    primary_index: int = 1,
    secondary_index: int = 1,
    min_x: float = 8.0,
    max_x: float = 92.0,
    min_y: float = 10.0,
    max_y: float = 92.0,
) -> dict[str, float]:
    normalized_lane = " ".join(str(lane or "").split()).strip().lower() or "interaction"
    seed = sum((idx + 1) * ord(ch) for idx, ch in enumerate(normalized_lane))
    x_span = max(1, int(round(max_x - min_x)))
    y_span = max(1, int(round(max_y - min_y)))
    x = min_x + float((seed + (max(1, int(primary_index)) * 17) + (max(1, int(secondary_index)) * 29)) % (x_span + 1))
    y = min_y + float(((seed * 3) + (max(1, int(primary_index)) * 11) + (max(1, int(secondary_index)) * 13)) % (y_span + 1))
    return {
        "cursor_x": round(_bounded_percent(x, minimum=min_x, maximum=max_x), 2),
        "cursor_y": round(_bounded_percent(y, minimum=min_y, maximum=max_y), 2),
    }


def with_scene(
    payload: dict[str, Any] | None,
    *,
    scene_surface: str,
    lane: str,
    primary_index: int = 1,
    secondary_index: int = 1,
) -> dict[str, Any]:
    base = dict(payload or {})
    base["scene_surface"] = str(scene_surface or "website")
    base.update(
        cursor_payload(
            lane=lane,
            primary_index=primary_index,
            secondary_index=secondary_index,
        )
    )
    return base
