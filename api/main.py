from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path

# Suppress known harmless third-party deprecation/compatibility warnings that
# appear at import time and cannot be fixed upstream.
warnings.filterwarnings("ignore", category=UserWarning, module=r"pydantic.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module=r"cryptography.*")
warnings.filterwarnings("ignore", message=r"urllib3.*chardet.*", category=UserWarning)
warnings.filterwarnings("ignore", message=r"ARC4 has been moved", category=DeprecationWarning)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
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
from api.routers.tenants import router as tenants_router
from api.routers.agent_definitions import router as agent_definitions_router
from api.routers.connectors import router as connectors_router
from api.routers.computer_use import router as computer_use_router
from api.routers.agents import router as agents_router
from api.routers.agents import webhook_router
from api.routers.marketplace import router as marketplace_router
from api.routers.page_monitor import router as page_monitor_router
from api.routers.proactive import router as proactive_router
from api.routers.workflows import router as workflows_router
from api.routers.observability import router as observability_router
from api.routers.canvas import router as canvas_router
from api.routers.auth import router as auth_router
from api.routers.api_keys import router as api_keys_router
from api.routers.developers import router as developers_router
from api.routers.users import router as users_router
from api.routers.sso import router as sso_router
from api.routers.audit import router as audit_router
from api.routers.versions import router as versions_router
from api.routers.secrets import router as secrets_router
from api.routers.mfa import router as mfa_router
from api.routers.roles import router as roles_router
from api.schemas import HealthResponse
from api.services.agent.report_scheduler import get_report_scheduler
from api.services.agents.scheduler import get_agent_scheduler
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


@asynccontextmanager
async def _lifespan(app: FastAPI):  # type: ignore[type-arg]
    # ── startup ──────────────────────────────────────────────────────────────
    load_local_env_if_present()
    startup_notices = run_upload_startup_checks()
    for message in startup_notices:
        logger.info(message)
    get_context()
    get_ingestion_manager().start()
    get_report_scheduler().start()
    get_agent_scheduler().start()
    try:
        from api.services.agents.event_triggers import seed_subscriptions_from_definitions
        seed_subscriptions_from_definitions()
    except Exception:
        pass
    try:
        from api.services.agent.skills.loader import seed_marketplace_agents
        seed_marketplace_agents()
    except Exception:
        pass
    try:
        from api.services.proactive.monitor import get_proactive_monitor
        get_proactive_monitor().start()
    except Exception:
        pass
    try:
        from api.services.marketplace.page_monitor import get_page_monitor
        get_page_monitor().start()
    except Exception:
        pass
    yield
    # ── shutdown ─────────────────────────────────────────────────────────────
    get_ingestion_manager().stop()
    get_report_scheduler().stop()
    get_agent_scheduler().stop()
    try:
        from api.services.proactive.monitor import get_proactive_monitor
        get_proactive_monitor().stop()
    except Exception:
        pass
    try:
        from api.services.marketplace.page_monitor import get_page_monitor
        get_page_monitor().stop()
    except Exception:
        pass


app = FastAPI(
    title="Maia API",
    version="0.1.0",
    description="FastAPI wrapper over Maia/KTEM backend logic.",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security & observability middleware (order matters: outermost runs first)
from api.middleware.audit import AuditMiddleware  # noqa: E402
from api.middleware.rate_limit import RateLimitMiddleware  # noqa: E402
from api.services.tenants.middleware import TenantContextMiddleware  # noqa: E402

app.add_middleware(AuditMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TenantContextMiddleware)

app.include_router(auth_router)
app.include_router(api_keys_router)
app.include_router(users_router)
app.include_router(developers_router)
app.include_router(conversations_router)
app.include_router(settings_router)
app.include_router(uploads_router)
app.include_router(chat_router)
app.include_router(mindmap_router)
app.include_router(agent_router)
app.include_router(integrations_router)
app.include_router(metrics_router)
app.include_router(web_preview_router)
app.include_router(tenants_router)
app.include_router(agent_definitions_router)
app.include_router(connectors_router)
app.include_router(computer_use_router)
app.include_router(agents_router)
app.include_router(webhook_router)
app.include_router(marketplace_router)
app.include_router(proactive_router)
app.include_router(workflows_router)
app.include_router(observability_router)
app.include_router(canvas_router)
app.include_router(page_monitor_router)

# Enterprise routers
app.include_router(sso_router)
app.include_router(audit_router)
app.include_router(versions_router)
app.include_router(secrets_router)
app.include_router(mfa_router)
app.include_router(roles_router)


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
