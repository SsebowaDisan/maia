"""Pluggable filesystem backend for agent file operations."""
from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FileEntry:
    path: str
    is_dir: bool
    size: int = 0


@dataclass
class SearchMatch:
    path: str
    line_number: int
    line_text: str


class FilesystemBackend(ABC):
    """Abstract interface for agent file operations."""

    @abstractmethod
    def read(self, path: str, *, offset: int = 0, limit: int = 2000) -> str: ...

    @abstractmethod
    def write(self, path: str, content: str) -> None: ...

    @abstractmethod
    def edit(self, path: str, old_text: str, new_text: str) -> bool: ...

    @abstractmethod
    def list_dir(self, path: str = ".") -> list[FileEntry]: ...

    @abstractmethod
    def search(self, pattern: str, *, path: str = ".", glob: str = "*") -> list[SearchMatch]: ...

    @abstractmethod
    def exists(self, path: str) -> bool: ...

    @abstractmethod
    def delete(self, path: str) -> bool: ...


class LocalFilesystemBackend(FilesystemBackend):
    """Local-disk backend scoped to a workspace root.

    All paths are resolved relative to root and cannot escape it.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, path: str) -> Path:
        resolved = (self._root / path).resolve()
        if not str(resolved).startswith(str(self._root)):
            raise PermissionError(f"Path escapes workspace root: {path}")
        return resolved

    def read(self, path: str, *, offset: int = 0, limit: int = 2000) -> str:
        p = self._safe_path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Not a file: {path}")
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        selected = lines[offset : offset + limit]
        return "".join(
            f"{offset + i + 1:>6}\t{line}" for i, line in enumerate(selected)
        )

    def write(self, path: str, content: str) -> None:
        p = self._safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def edit(self, path: str, old_text: str, new_text: str) -> bool:
        p = self._safe_path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Not a file: {path}")
        current = p.read_text(encoding="utf-8")
        count = current.count(old_text)
        if count == 0:
            return False
        if count > 1:
            raise ValueError(f"old_text is ambiguous — found {count} occurrences")
        p.write_text(current.replace(old_text, new_text, 1), encoding="utf-8")
        return True

    def list_dir(self, path: str = ".") -> list[FileEntry]:
        p = self._safe_path(path)
        if not p.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        entries = []
        for child in sorted(p.iterdir()):
            try:
                entries.append(FileEntry(
                    path=str(child.relative_to(self._root)),
                    is_dir=child.is_dir(),
                    size=child.stat().st_size if child.is_file() else 0,
                ))
            except (OSError, ValueError):
                pass
        return entries

    def search(self, pattern: str, *, path: str = ".", glob: str = "*") -> list[SearchMatch]:
        p = self._safe_path(path)
        if not p.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        regex = re.compile(pattern, re.IGNORECASE)
        matches: list[SearchMatch] = []
        for file_path in sorted(p.rglob(glob)):
            if not file_path.is_file():
                continue
            try:
                for i, line in enumerate(
                    file_path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
                ):
                    if regex.search(line):
                        matches.append(SearchMatch(
                            path=str(file_path.relative_to(self._root)),
                            line_number=i,
                            line_text=line.rstrip(),
                        ))
                        if len(matches) >= 200:
                            return matches
            except (OSError, UnicodeDecodeError):
                pass
        return matches

    def exists(self, path: str) -> bool:
        return self._safe_path(path).exists()

    def delete(self, path: str) -> bool:
        p = self._safe_path(path)
        if p.is_file():
            p.unlink()
            return True
        return False
