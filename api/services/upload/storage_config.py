"""File-tier storage path configuration.

Two root directories, both on D: drive by default so data survives OS failure.
Override via env vars if needed.

    MAIA_FILES_LIBRARY_DIR   — permanent admin-uploaded library files
    MAIA_FILES_USER_TEMP_DIR — composer uploads (30-day TTL, flaggable)
"""
from __future__ import annotations

from pathlib import Path

from decouple import config as _cfg


def _default(subpath: str) -> str:
    d = Path("D:/maia-data")
    if Path("D:/").exists():
        return str(d / subpath)
    return str(Path("ktem_app_data/user_data") / subpath)


LIBRARY_DIR: Path = Path(_cfg("MAIA_FILES_LIBRARY_DIR", default=_default("files/library")))
USER_TEMP_DIR: Path = Path(_cfg("MAIA_FILES_USER_TEMP_DIR", default=_default("files/user_temp")))

# TTL constants
USER_TEMP_TTL_DAYS: int = int(_cfg("MAIA_FILES_USER_TEMP_TTL_DAYS", default=30))
FLAGGED_TTL_DAYS: int = int(_cfg("MAIA_FILES_FLAGGED_TTL_DAYS", default=30))


def ensure_dirs() -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    USER_TEMP_DIR.mkdir(parents=True, exist_ok=True)
