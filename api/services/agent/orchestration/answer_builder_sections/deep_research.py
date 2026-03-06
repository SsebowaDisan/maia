from __future__ import annotations

import re

from .models import AnswerBuildContext

TOP_LEVEL_HEADING_RE = re.compile(r"^\s*##\s+(.+?)\s*$")
DETAILED_REPORT_HEADING_RE = re.compile(r"^\s*##\s+Detailed Research Report\s*$", re.IGNORECASE)
TITLE_HEADING_RE = re.compile(r"^\s*#{1,2}\s+(.+?)\s*$")

BLOCKED_TOP_LEVEL_SECTIONS = {
    "key findings",
    "delivery status",
    "contract gate",
    "verification",
    "files and documents",
    "task understanding",
    "execution plan",
    "research blueprint",
    "execution summary",
    "execution issues",
    "evidence citations",
    "evidence backed value add",
}


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _strip_ops_sections(report_lines: list[str]) -> list[str]:
    if not report_lines:
        return report_lines

    detail_start_index: int | None = None
    for idx, line in enumerate(report_lines):
        if DETAILED_REPORT_HEADING_RE.match(line):
            detail_start_index = idx + 1
            break
    if detail_start_index is not None:
        report_lines = report_lines[detail_start_index:]

    while report_lines and not report_lines[0].strip():
        report_lines = report_lines[1:]

    if report_lines:
        title_match = TITLE_HEADING_RE.match(report_lines[0])
        if title_match:
            normalized = _normalize_title(title_match.group(1))
            if normalized.endswith("report") or normalized in {"research", "website analysis"}:
                report_lines = report_lines[1:]
                while report_lines and not report_lines[0].strip():
                    report_lines = report_lines[1:]

    filtered_lines: list[str] = []
    index = 0
    while index < len(report_lines):
        line = report_lines[index]
        heading_match = TOP_LEVEL_HEADING_RE.match(line)
        if not heading_match:
            filtered_lines.append(line)
            index += 1
            continue

        heading_title = _normalize_title(heading_match.group(1))
        section_lines = [line]
        index += 1
        while index < len(report_lines) and not TOP_LEVEL_HEADING_RE.match(report_lines[index]):
            section_lines.append(report_lines[index])
            index += 1

        if heading_title in BLOCKED_TOP_LEVEL_SECTIONS:
            continue
        filtered_lines.extend(section_lines)

    while filtered_lines and not filtered_lines[0].strip():
        filtered_lines = filtered_lines[1:]

    return filtered_lines


def append_deep_research_report(lines: list[str], ctx: AnswerBuildContext) -> None:
    depth_tier = " ".join(str(ctx.runtime_settings.get("__research_depth_tier") or "").split()).strip().lower()
    if depth_tier not in {"deep_research", "deep_analytics"}:
        return

    report_content = str(ctx.runtime_settings.get("__latest_report_content") or "").strip()
    if not report_content:
        return

    report_lines = _strip_ops_sections([line.rstrip() for line in report_content.splitlines()])

    if not report_lines:
        return

    lines.append("")
    lines.append("## Detailed Research Report")
    max_lines = 220
    lines.extend(report_lines[:max_lines])
    if len(report_lines) > max_lines:
        lines.append("")
        lines.append("_Detailed report truncated in chat view; full draft was generated during execution._")
