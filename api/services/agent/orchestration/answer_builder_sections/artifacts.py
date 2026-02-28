from __future__ import annotations

from .models import AnswerBuildContext


def append_files_and_documents(lines: list[str], ctx: AnswerBuildContext) -> None:
    artifact_urls: list[str] = []
    artifact_paths: list[str] = []
    for action in ctx.actions:
        metadata = action.metadata if isinstance(action.metadata, dict) else {}
        for key in ("url", "document_url", "spreadsheet_url"):
            raw = metadata.get(key)
            value = str(raw or "").strip()
            if not value or value in artifact_urls:
                continue
            artifact_urls.append(value)
        for key in ("path", "pdf_path"):
            raw = metadata.get(key)
            value = str(raw or "").strip()
            if not value or value in artifact_paths:
                continue
            artifact_paths.append(value)

    if not artifact_urls and not artifact_paths:
        return

    lines.append("")
    lines.append("## Files and Documents")
    for url in artifact_urls[:10]:
        lines.append(f"- {url}")
    for path in artifact_paths[:10]:
        lines.append(f"- {path}")
