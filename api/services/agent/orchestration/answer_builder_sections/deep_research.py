from __future__ import annotations

import re

from .models import AnswerBuildContext

TOP_LEVEL_HEADING_RE = re.compile(r"^\s*##\s+(.+?)\s*$")
SUB_HEADING_RE = re.compile(r"^\s*###\s+(.+?)\s*$")
DETAILED_REPORT_HEADING_RE = re.compile(r"^\s*##\s+Detailed Research Report\s*$", re.IGNORECASE)
TITLE_HEADING_RE = re.compile(r"^\s*#{1,2}\s+(.+?)\s*$")

BLOCKED_TOP_LEVEL_SECTIONS = {
    "key findings",
    "research execution status",
    "delivery status",
    "delivery attempt overview",
    "contract gate",
    "contract gate summary",
    "verification",
    "verification and quality assessment",
    "verification and quality",
    "verification quality",
    "files and documents",
    "task understanding",
    "execution plan",
    "research blueprint",
    "execution summary",
    "execution issues",
    "evidence and citations",
    "evidence citations",
    "evidence backed value add",
    "recommended next steps",
}

BLOCKED_TOP_LEVEL_SUBSTRINGS = (
    "delivery status",
    "delivery attempt",
    "contract gate",
    "verification and quality",
    "execution status",
    "execution stability",
    "evidence citations",
    "evidence and citations",
    "recommended next steps",
    "files and documents",
)

BLOCKED_SUBSECTIONS = {
    "highlights",
    "reference links",
    "recommended next steps",
    "evidence citations",
    "delivery status",
    "contract gate",
    "verification",
    "files and documents",
}

CONTRACT_CLAUSE_RE = re.compile(
    r"\b(contract objective|required outputs|required facts|success checks|deliverables)\s*:",
    flags=re.IGNORECASE,
)


def _normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _is_blocked_top_level_section(title: str) -> bool:
    normalized = _normalize_title(title)
    if not normalized:
        return False
    if normalized in BLOCKED_TOP_LEVEL_SECTIONS:
        return True
    return any(token in normalized for token in BLOCKED_TOP_LEVEL_SUBSTRINGS)


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

        heading_title = heading_match.group(1)
        section_lines = [line]
        index += 1
        while index < len(report_lines) and not TOP_LEVEL_HEADING_RE.match(report_lines[index]):
            section_lines.append(report_lines[index])
            index += 1

        if _is_blocked_top_level_section(heading_title):
            continue
        filtered_lines.extend(section_lines)

    while filtered_lines and not filtered_lines[0].strip():
        filtered_lines = filtered_lines[1:]

    return filtered_lines


def _clean_summary_contract_noise(line: str) -> str:
    text = str(line or "")
    if not text:
        return text
    match = CONTRACT_CLAUSE_RE.search(text)
    if not match:
        return text
    cleaned = text[: match.start()].strip()
    return cleaned


def _sanitize_subsections(report_lines: list[str]) -> list[str]:
    if not report_lines:
        return report_lines

    cleaned: list[str] = []
    current_section = ""
    skip_section = False
    bullet_count_in_section = 0
    max_bullets_per_section = 16

    for raw in report_lines:
        line = str(raw or "").rstrip()
        heading_match = SUB_HEADING_RE.match(line)
        if heading_match:
            current_section = _normalize_title(heading_match.group(1))
            skip_section = current_section in BLOCKED_SUBSECTIONS
            bullet_count_in_section = 0
            if skip_section:
                continue
            cleaned.append(line)
            continue

        if skip_section:
            continue

        stripped = line.strip()
        if stripped.startswith("- "):
            bullet_count_in_section += 1
            if bullet_count_in_section > max_bullets_per_section:
                continue

        if current_section == "executive summary":
            line = _clean_summary_contract_noise(line)
            if not line.strip():
                continue

        cleaned.append(line)

    while cleaned and not cleaned[0].strip():
        cleaned = cleaned[1:]
    while cleaned and not cleaned[-1].strip():
        cleaned = cleaned[:-1]

    normalized: list[str] = []
    blank_streak = 0
    for line in cleaned:
        if line.strip():
            blank_streak = 0
            normalized.append(line)
            continue
        blank_streak += 1
        if blank_streak <= 1:
            normalized.append("")
    return normalized


def append_deep_research_report(lines: list[str], ctx: AnswerBuildContext) -> None:
    depth_tier = " ".join(str(ctx.runtime_settings.get("__research_depth_tier") or "").split()).strip().lower()
    report_content = str(ctx.runtime_settings.get("__latest_report_content") or "").strip()
    if not report_content:
        return
    analytics_snapshot_report = "### GA4 Full Report Snapshot" in report_content
    if depth_tier not in {"deep_research", "deep_analytics", "expert"} and not analytics_snapshot_report:
        return

    report_lines = _strip_ops_sections([line.rstrip() for line in report_content.splitlines()])
    report_lines = _sanitize_subsections(report_lines)

    if not report_lines:
        return

    lines.append("")
    lines.append("## Analytics Report" if analytics_snapshot_report else "## Detailed Research Report")
    # Expert tier gets full report; deep tiers get up to 500 lines; standard analytics reports remain concise.
    max_lines = 800 if depth_tier == "expert" else (500 if depth_tier in {"deep_research", "deep_analytics"} else 380)
    lines.extend(report_lines[:max_lines])
    if len(report_lines) > max_lines:
        lines.append("")
        lines.append("_Detailed report truncated in chat view; full draft was generated during execution._")
