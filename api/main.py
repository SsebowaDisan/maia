from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.context import get_context
from api.metrics import router as metrics_router
from api.routers.agent import router as agent_router
from api.routers.chat import router as chat_router
from api.routers.conversations import router as conversations_router
from api.routers.integrations import router as integrations_router
from api.routers.mindmap import router as mindmap_router
from api.routers.settings import router as settings_router
from api.routers.uploads import router as uploads_router
from api.routers.web_preview import router as web_preview_router
from api.schemas import HealthResponse
from api.services.agent.report_scheduler import get_report_scheduler
from api.services.ingestion_service import get_ingestion_manager
from api.services.upload.indexing import run_upload_startup_checks

_ENV_FILE_LOADED = False
logger = logging.getLogger(__name__)


def _strip_wrapped_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_key = key.strip()
        if not env_key or env_key in os.environ:
            continue
        os.environ[env_key] = _strip_wrapped_quotes(value.strip())


def load_local_env_if_present() -> None:
    global _ENV_FILE_LOADED
    if _ENV_FILE_LOADED:
        return
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    ]
    visited: set[str] = set()
    for candidate in candidates:
        resolved = str(candidate.resolve())
        if resolved in visited:
            continue
        visited.add(resolved)
        if candidate.exists() and candidate.is_file():
            _load_env_file(candidate)
            break
    _ENV_FILE_LOADED = True


app = FastAPI(
    title="Maia API",
    version="0.1.0",
    description="FastAPI wrapper over Maia/KTEM backend logic.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(conversations_router)
app.include_router(settings_router)
app.include_router(uploads_router)
app.include_router(chat_router)
app.include_router(mindmap_router)
app.include_router(agent_router)
app.include_router(integrations_router)
app.include_router(metrics_router)
app.include_router(web_preview_router)


@app.on_event("startup")
def warm_backend_context() -> None:
    load_local_env_if_present()
    startup_notices = run_upload_startup_checks()
    for message in startup_notices:
        logger.info(message)
    # Ensure indices/reasonings/settings are initialized once at server startup.
    get_context()
    get_ingestion_manager().start()
    get_report_scheduler().start()


@app.on_event("shutdown")
def stop_background_services() -> None:
    get_ingestion_manager().stop()
    get_report_scheduler().stop()


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "user_interface" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
else:

    @app.get("/")
    def root():
        return JSONResponse(
            {
                "message": "Maia API is running.",
                "frontend_dist_found": False,
                "hint": "Build frontend/user_interface to generate dist files.",
            }
        )
