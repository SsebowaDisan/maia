from __future__ import annotations

import json
import os
import re
from pathlib import Path
from threading import Lock
from typing import Any

from api.services.agent.models import utc_now

_WORD_RE = re.compile(r"[a-z0-9]{3,}")


def _tokenize(text: str) -> set[str]:
    return {match.group(0) for match in _WORD_RE.finditer(str(text or "").lower())}


def _score_overlap(*, query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    text_tokens = _tokenize(text)
    if not text_tokens:
        return 0.0
    overlap = len(query_tokens.intersection(text_tokens))
    return overlap / float(max(1, len(query_tokens)))


def _clean_text(value: Any, *, max_chars: int = 420) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text[: max(1, int(max_chars))]


def _session_snippet(row: dict[str, Any]) -> str:
    message = _clean_text(row.get("message"), max_chars=220)
    goal = _clean_text(row.get("agent_goal"), max_chars=220)
    next_steps = row.get("next_recommended_steps")
    next_steps_text = (
        "; ".join(
            _clean_text(item, max_chars=120)
            for item in next_steps
            if _clean_text(item, max_chars=120)
        )
        if isinstance(next_steps, list)
        else ""
    )
    joined = " | ".join(
        # Keep retrieval anchored to prior task framing rather than prior model
        # completions, which can inject scope drift into later runs.
        item for item in (message, goal, next_steps_text) if item
    ).strip()
    return joined[:420]


class SessionStore:
    def __init__(self, *, root: Path | None = None) -> None:
        base_root = root if isinstance(root, Path) else Path(".maia_agent")
        self.root = base_root
        self.root.mkdir(parents=True, exist_ok=True)
        self.file_path = self.root / "session_runs.json"
        self._lock = Lock()
        if not self.file_path.exists():
            self.file_path.write_text("[]", encoding="utf-8")

    def _load(self) -> list[dict[str, Any]]:
        try:
            rows = json.loads(self.file_path.read_text(encoding="utf-8"))
            return rows if isinstance(rows, list) else []
        except json.JSONDecodeError:
            return []

    def _save(self, rows: list[dict[str, Any]]) -> None:
        try:
            max_rows = int(os.getenv("MAIA_SESSION_RUN_STORE_MAX_ROWS", "240"))
        except Exception:
            max_rows = 240
        if max_rows > 0 and len(rows) > max_rows:
            rows = rows[-max_rows:]
        self.file_path.write_text(
            json.dumps(rows, ensure_ascii=True, separators=(",", ":")),
            encoding="utf-8",
        )

    def save_session_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = _clean_text(payload.get("run_id"), max_chars=120)
        if not run_id:
            raise ValueError("session run payload requires `run_id`")
        now_iso = utc_now().isoformat()
        with self._lock:
            rows = self._load()
            updated: dict[str, Any] | None = None
            for index, row in enumerate(rows):
                if _clean_text(row.get("run_id"), max_chars=120) != run_id:
                    continue
                merged = {
                    **row,
                    **payload,
                    "run_id": run_id,
                    "date_updated": now_iso,
                }
                if not _clean_text(merged.get("date_created"), max_chars=80):
                    merged["date_created"] = now_iso
                rows[index] = merged
                updated = merged
                break
            if updated is None:
                updated = {
                    "run_id": run_id,
                    "date_created": now_iso,
                    "date_updated": now_iso,
                    **payload,
                }
                rows.append(updated)
            self._save(rows)
        return updated

    def list_session_runs(
        self,
        *,
        user_id: str = "",
        conversation_id: str = "",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        rows = self._load()
        clean_user_id = _clean_text(user_id, max_chars=120)
        clean_conversation_id = _clean_text(conversation_id, max_chars=120)
        filtered: list[dict[str, Any]] = []
        for row in rows:
            if clean_user_id and _clean_text(row.get("user_id"), max_chars=120) != clean_user_id:
                continue
            if (
                clean_conversation_id
                and _clean_text(row.get("conversation_id"), max_chars=120) != clean_conversation_id
            ):
                continue
            filtered.append(row)
        filtered.sort(key=lambda item: _clean_text(item.get("date_updated"), max_chars=80), reverse=True)
        return filtered[: max(1, int(limit))]

    def retrieve_context_snippets(
        self,
        *,
        query: str,
        user_id: str = "",
        conversation_id: str = "",
        limit: int = 4,
    ) -> list[str]:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []
        clean_user_id = _clean_text(user_id, max_chars=120)
        clean_conversation_id = _clean_text(conversation_id, max_chars=120)
        candidates: list[tuple[float, str]] = []
        for row in self.list_session_runs(user_id=clean_user_id, limit=160):
            snippet = _session_snippet(row)
            if not snippet:
                continue
            score = _score_overlap(query_tokens=query_tokens, text=snippet)
            if score <= 0.0:
                continue
            row_conversation = _clean_text(row.get("conversation_id"), max_chars=120)
            if clean_conversation_id and row_conversation == clean_conversation_id:
                score += 0.35
            candidates.append((score, snippet))
        if not candidates:
            return []
        candidates.sort(key=lambda item: item[0], reverse=True)
        output: list[str] = []
        seen: set[str] = set()
        for _, snippet in candidates:
            key = snippet.lower()
            if key in seen:
                continue
            seen.add(key)
            output.append(snippet)
            if len(output) >= max(1, int(limit)):
                break
        return output


_session_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        _session_store = SessionStore()
    return _session_store

