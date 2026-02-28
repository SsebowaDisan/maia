from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Lock
from typing import Any

from api.services.agent.models import new_id, utc_now


def _root() -> Path:
    root = Path(".maia_agent")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _runs_path() -> Path:
    return _root() / "runs.json"


def _playbooks_path() -> Path:
    return _root() / "playbooks.json"


class JsonStore:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self._lock = Lock()
        if not self.file_path.exists():
            self.file_path.write_text("[]", encoding="utf-8")

    def _load(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _save(self, rows: list[dict[str, Any]]) -> None:
        self.file_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

    def append(self, row: dict[str, Any]) -> None:
        with self._lock:
            rows = self._load()
            rows.append(row)
            self._save(rows)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._load()
        rows.sort(key=lambda item: item.get("date_created", ""), reverse=True)
        return rows[: max(1, limit)]

    def upsert(self, row_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            rows = self._load()
            for index, row in enumerate(rows):
                if row.get("id") == row_id:
                    merged = {**row, **payload, "id": row_id, "date_updated": utc_now().isoformat()}
                    rows[index] = merged
                    self._save(rows)
                    return merged
            created = {
                "id": row_id,
                "date_created": utc_now().isoformat(),
                "date_updated": utc_now().isoformat(),
                **payload,
            }
            rows.append(created)
            self._save(rows)
            return created

    def get(self, row_id: str) -> dict[str, Any] | None:
        rows = self._load()
        return next((row for row in rows if row.get("id") == row_id), None)


class AgentMemoryService:
    def __init__(self) -> None:
        self.runs = JsonStore(_runs_path())
        self.playbooks = JsonStore(_playbooks_path())

    def save_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        run_id = payload.get("run_id") or new_id("runmem")
        record = {
            "id": run_id,
            "run_id": run_id,
            "date_created": utc_now().isoformat(),
            **payload,
        }
        self.runs.append(record)
        return record

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.runs.list(limit=limit)

    def save_playbook(
        self,
        *,
        name: str,
        prompt_template: str,
        tool_ids: list[str],
        owner_id: str,
    ) -> dict[str, Any]:
        playbook_id = new_id("playbook")
        return self.playbooks.upsert(
            playbook_id,
            {
                "name": name,
                "prompt_template": prompt_template,
                "tool_ids": tool_ids,
                "owner_id": owner_id,
                "version": 1,
            },
        )

    def update_playbook(self, playbook_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        existing = self.playbooks.get(playbook_id)
        version = int(existing.get("version", 1)) + 1 if existing else 1
        return self.playbooks.upsert(playbook_id, {**patch, "version": version})

    def list_playbooks(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.playbooks.list(limit=limit)

    def retrieve_context_snippets(
        self,
        *,
        query: str,
        limit: int = 4,
    ) -> list[str]:
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        candidates: list[tuple[float, str]] = []
        for row in self.runs.list(limit=120):
            snippet = _run_snippet(row)
            if not snippet:
                continue
            score = _score_overlap(query_tokens=query_tokens, text=snippet)
            if score <= 0.0:
                continue
            candidates.append((score, snippet))
        for row in self.playbooks.list(limit=80):
            snippet = _playbook_snippet(row)
            if not snippet:
                continue
            score = _score_overlap(query_tokens=query_tokens, text=snippet)
            if score <= 0.0:
                continue
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


def _run_snippet(row: dict[str, Any]) -> str:
    message = " ".join(str(row.get("message") or "").split()).strip()
    goal = " ".join(str(row.get("agent_goal") or "").split()).strip()
    answer = " ".join(str(row.get("answer") or "").split()).strip()
    joined = " | ".join([item for item in [message, goal, answer] if item]).strip()
    return joined[:420]


def _playbook_snippet(row: dict[str, Any]) -> str:
    name = " ".join(str(row.get("name") or "").split()).strip()
    prompt_template = " ".join(str(row.get("prompt_template") or "").split()).strip()
    tools_raw = row.get("tool_ids")
    tools = ", ".join(
        str(item).strip()
        for item in tools_raw
        if str(item).strip()
    ) if isinstance(tools_raw, list) else ""
    joined = " | ".join([item for item in [name, prompt_template, tools] if item]).strip()
    return joined[:420]


_memory_service: AgentMemoryService | None = None


def get_memory_service() -> AgentMemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = AgentMemoryService()
    return _memory_service
