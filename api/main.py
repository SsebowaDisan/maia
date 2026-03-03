from __future__ import annotations

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
from api.schemas import HealthResponse
from api.services.agent.report_scheduler import get_report_scheduler
from api.services.ingestion_service import get_ingestion_manager

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


@app.on_event("startup")
def warm_backend_context() -> None:
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
