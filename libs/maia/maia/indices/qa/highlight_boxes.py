from __future__ import annotations

from typing import Any

from maia.loaders.utils.box import union_points

MAX_HIGHLIGHT_BOXES = 24


def _to_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed != parsed:  # NaN
        return None
    return parsed


def _normalize_xywh(
    *,
    x: Any,
    y: Any,
    width: Any,
    height: Any,
    page_width: float | None,
    page_height: float | None,
) -> dict[str, float] | None:
    left = _to_float(x)
    top = _to_float(y)
    w = _to_float(width)
    h = _to_float(height)
    if left is None or top is None or w is None or h is None:
        return None
    if (
        page_width
        and page_height
        and page_width > 1.0
        and page_height > 1.0
        and (left > 1.0 or top > 1.0 or w > 1.0 or h > 1.0)
    ):
        left /= page_width
        top /= page_height
        w /= page_width
        h /= page_height
    left = max(0.0, min(1.0, left))
    top = max(0.0, min(1.0, top))
    w = max(0.0, min(1.0 - left, w))
    h = max(0.0, min(1.0 - top, h))
    if w < 0.002 or h < 0.002:
        return None
    return {
        "x": round(left, 6),
        "y": round(top, 6),
        "width": round(w, 6),
        "height": round(h, 6),
    }


def _normalize_xyxy(
    *,
    x0: Any,
    y0: Any,
    x1: Any,
    y1: Any,
    page_width: float | None,
    page_height: float | None,
) -> dict[str, float] | None:
    left = _to_float(x0)
    top = _to_float(y0)
    right = _to_float(x1)
    bottom = _to_float(y1)
    if left is None or top is None or right is None or bottom is None:
        return None
    return _normalize_xywh(
        x=left,
        y=top,
        width=right - left,
        height=bottom - top,
        page_width=page_width,
        page_height=page_height,
    )


def _normalize_points_box(
    points: Any,
    *,
    page_width: float | None,
    page_height: float | None,
) -> dict[str, float] | None:
    if not isinstance(points, list) or len(points) < 2:
        return None
    xs: list[float] = []
    ys: list[float] = []
    for point in points:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            px = _to_float(point[0])
            py = _to_float(point[1])
        elif isinstance(point, dict):
            px = _to_float(point.get("x"))
            py = _to_float(point.get("y"))
        else:
            px = None
            py = None
        if px is None or py is None:
            continue
        xs.append(px)
        ys.append(py)
    if len(xs) < 2 or len(ys) < 2:
        return None
    return _normalize_xyxy(
        x0=min(xs),
        y0=min(ys),
        x1=max(xs),
        y1=max(ys),
        page_width=page_width,
        page_height=page_height,
    )


def _dedupe_boxes(boxes: list[dict[str, float]]) -> list[dict[str, float]]:
    deduped: list[dict[str, float]] = []
    seen: set[tuple[float, float, float, float]] = set()
    for box in boxes:
        key = (
            float(box["x"]),
            float(box["y"]),
            float(box["width"]),
            float(box["height"]),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(box)
    return deduped


def normalize_highlight_boxes(
    raw: Any,
    *,
    page_width: float | None = None,
    page_height: float | None = None,
    max_boxes: int = MAX_HIGHLIGHT_BOXES,
) -> list[dict[str, float]]:
    if not isinstance(raw, list):
        return []

    out: list[dict[str, float]] = []
    for row in raw:
        normalized: dict[str, float] | None = None
        if isinstance(row, dict):
            if {"x", "y", "width", "height"}.issubset(row):
                normalized = _normalize_xywh(
                    x=row.get("x"),
                    y=row.get("y"),
                    width=row.get("width"),
                    height=row.get("height"),
                    page_width=page_width,
                    page_height=page_height,
                )
            elif {"x0", "y0", "x1", "y1"}.issubset(row):
                normalized = _normalize_xyxy(
                    x0=row.get("x0"),
                    y0=row.get("y0"),
                    x1=row.get("x1"),
                    y1=row.get("y1"),
                    page_width=page_width,
                    page_height=page_height,
                )
            elif {"l", "t", "r", "b"}.issubset(row):
                normalized = _normalize_xyxy(
                    x0=row.get("l"),
                    y0=row.get("t"),
                    x1=row.get("r"),
                    y1=row.get("b"),
                    page_width=page_width,
                    page_height=page_height,
                )
            elif isinstance(row.get("points"), list):
                normalized = _normalize_points_box(
                    row.get("points"),
                    page_width=page_width,
                    page_height=page_height,
                )
            elif isinstance(row.get("location"), list):
                normalized = _normalize_points_box(
                    row.get("location"),
                    page_width=page_width,
                    page_height=page_height,
                )
        elif isinstance(row, (list, tuple)):
            if len(row) == 4:
                normalized = _normalize_xyxy(
                    x0=row[0],
                    y0=row[1],
                    x1=row[2],
                    y1=row[3],
                    page_width=page_width,
                    page_height=page_height,
                )
            else:
                normalized = _normalize_points_box(
                    list(row),
                    page_width=page_width,
                    page_height=page_height,
                )
        if not normalized:
            continue
        out.append(normalized)
        if len(out) >= max(1, int(max_boxes)):
            break
    return _dedupe_boxes(out)


def extract_highlight_boxes_from_metadata(
    metadata: dict[str, Any],
    *,
    max_boxes: int = MAX_HIGHLIGHT_BOXES,
) -> list[dict[str, float]]:
    page_width = _to_float(metadata.get("page_width") or metadata.get("pdf_page_width"))
    page_height = _to_float(metadata.get("page_height") or metadata.get("pdf_page_height"))

    candidates: list[Any] = []
    for key in (
        "highlight_boxes",
        "boxes",
        "box",
        "bbox",
        "bounding_box",
        "location",
        "coordinates",
    ):
        value = metadata.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            if (
                key in ("box", "bbox", "bounding_box")
                and len(value) == 4
                and not isinstance(value[0], (list, tuple, dict))
            ):
                candidates.append(value)
            else:
                candidates.extend(value)
        else:
            candidates.append(value)
    return normalize_highlight_boxes(
        candidates,
        page_width=page_width,
        page_height=page_height,
        max_boxes=max_boxes,
    )


def _box_bottom(box: dict[str, float]) -> float:
    return float(box["y"]) + float(box["height"])


def _box_right(box: dict[str, float]) -> float:
    return float(box["x"]) + float(box["width"])


def _boxes_are_adjacent(left: dict[str, float], right: dict[str, float]) -> bool:
    left_top = float(left["y"])
    right_top = float(right["y"])
    left_bottom = _box_bottom(left)
    right_bottom = _box_bottom(right)
    left_height = float(left["height"])
    right_height = float(right["height"])

    vertical_overlap = min(left_bottom, right_bottom) - max(left_top, right_top)
    vertical_overlap_ratio = vertical_overlap / max(0.001, min(left_height, right_height))
    vertical_gap = max(0.0, max(left_top, right_top) - min(left_bottom, right_bottom))
    nearby_row = vertical_gap <= max(left_height, right_height) * 0.85

    left_x = float(left["x"])
    right_x = float(right["x"])
    left_right = _box_right(left)
    right_right = _box_right(right)
    horizontal_overlap = min(left_right, right_right) - max(left_x, right_x)
    horizontal_overlap_ratio = horizontal_overlap / max(
        0.001, min(float(left["width"]), float(right["width"]))
    )
    center_delta = abs((left_x + left_right) * 0.5 - (right_x + right_right) * 0.5)
    similar_column = center_delta <= 0.16

    return vertical_overlap_ratio >= 0.35 or (
        nearby_row and (horizontal_overlap_ratio >= 0.1 or similar_column)
    )


def _union_group_boxes(group: list[dict[str, float]]) -> dict[str, float]:
    if len(group) == 1:
        return group[0]

    scale = 10000
    points: list[tuple[int, int]] = []
    for box in group:
        x0 = int(round(float(box["x"]) * scale))
        y0 = int(round(float(box["y"]) * scale))
        x1 = int(round(_box_right(box) * scale))
        y1 = int(round(_box_bottom(box) * scale))
        points.extend([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    x0, y0, x1, y1 = union_points(points)
    return {
        "x": round(max(0.0, min(1.0, x0 / scale)), 6),
        "y": round(max(0.0, min(1.0, y0 / scale)), 6),
        "width": round(max(0.0, min(1.0, (x1 - x0) / scale)), 6),
        "height": round(max(0.0, min(1.0, (y1 - y0) / scale)), 6),
    }


def merge_adjacent_highlight_boxes(
    boxes: list[dict[str, float]],
    *,
    max_groups: int = 10,
) -> list[dict[str, float]]:
    normalized = normalize_highlight_boxes(boxes)
    if not normalized:
        return []

    sorted_boxes = sorted(
        normalized,
        key=lambda item: (
            float(item["y"]),
            float(item["x"]),
            -float(item["width"]),
        ),
    )

    groups: list[list[dict[str, float]]] = []
    for box in sorted_boxes:
        if not groups:
            groups.append([box])
            continue
        last_group = groups[-1]
        if _boxes_are_adjacent(last_group[-1], box):
            last_group.append(box)
            continue
        groups.append([box])

    merged = [_union_group_boxes(group) for group in groups if group]
    merged = [row for row in _dedupe_boxes(merged) if row["width"] >= 0.002 and row["height"] >= 0.002]
    return merged[: max(1, int(max_groups))]

