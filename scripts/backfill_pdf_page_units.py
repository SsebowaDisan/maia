from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")


def _bootstrap_repo() -> Path:
    root = Path(__file__).resolve().parents[1]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root


ROOT = _bootstrap_repo()

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from api.context import get_context  # noqa: E402
from api.services.upload.pdf_highlight_locator import precompute_page_units_for_pdf  # noqa: E402
from ktem.db.engine import engine  # noqa: E402


def _safe_print(message: str) -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    text = str(message)
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))


def _resolve_pdf_sources(*, index_id: int | None, file_ids: set[str] | None) -> list[tuple[int, str, str, Path]]:
    context = get_context()
    indices = context.app.index_manager.indices
    if index_id is not None:
        indices = [context.get_index(index_id)]

    results: list[tuple[int, str, str, Path]] = []
    seen_paths: set[str] = set()

    for index in indices:
        Source = index._resources["Source"]
        fs_path = Path(index._resources["FileStoragePath"])
        with Session(engine) as session:
            rows = session.execute(select(Source)).all()

        for row in rows:
            source = row[0]
            source_id = str(source.id or "").strip()
            if not source_id:
                continue
            if file_ids and source_id not in file_ids:
                continue

            stored_name = str(source.name or "").strip()
            stored_path = str(source.path or "").strip()
            if not stored_path:
                continue

            candidate = Path(stored_path)
            if not candidate.is_absolute():
                candidate = fs_path / candidate
            try:
                candidate = candidate.resolve()
            except Exception:
                candidate = candidate.absolute()

            suffix = str(Path(stored_name).suffix or candidate.suffix).lower()
            if suffix != ".pdf":
                continue
            if not candidate.exists() or not candidate.is_file():
                continue

            key = str(candidate).lower()
            if key in seen_paths:
                continue
            seen_paths.add(key)
            results.append((int(index.id), source_id, stored_name or candidate.name, candidate))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill cached PDF page units for already indexed PDFs.",
    )
    parser.add_argument("--index-id", type=int, default=None, help="Only backfill one index.")
    parser.add_argument(
        "--file-id",
        action="append",
        default=[],
        help="Restrict to one or more indexed file ids.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N PDFs (0 = no limit).",
    )
    parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="Skip the first N matched PDFs before processing.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Cap pages processed per PDF (0 = all pages).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the PDFs that would be processed without doing work.",
    )
    args = parser.parse_args()

    file_ids = {str(value).strip() for value in list(args.file_id or []) if str(value).strip()} or None
    sources = _resolve_pdf_sources(index_id=args.index_id, file_ids=file_ids)
    if args.skip and args.skip > 0:
        sources = sources[int(args.skip) :]
    if args.limit and args.limit > 0:
        sources = sources[: int(args.limit)]

    if not sources:
        _safe_print("No indexed PDFs matched the requested filters.")
        return 0

    processed = 0
    failed = 0
    _safe_print(f"Found {len(sources)} indexed PDF(s) to backfill.")

    for index_pos, (resolved_index_id, source_id, source_name, file_path) in enumerate(sources, start=1):
        label = f"[{index_pos}/{len(sources)}] index={resolved_index_id} file_id={source_id} name={source_name}"
        if args.dry_run:
            _safe_print(f"{label} path={file_path}")
            continue
        try:
            summary = precompute_page_units_for_pdf(file_path, max_pages=max(0, int(args.max_pages or 0)))
            processed += 1
            _safe_print(
                f"{label} pages_cached={summary.get('pages_cached', 0)} "
                f"pages_with_ocr={summary.get('pages_with_ocr', 0)} total_pages={summary.get('total_pages', 0)}"
            )
        except Exception as exc:
            failed += 1
            _safe_print(f"{label} failed={exc}")

    _safe_print(f"Done. processed={processed} failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
