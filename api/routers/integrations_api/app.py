from __future__ import annotations

from fastapi import APIRouter

from .brave import router as brave_router
from .google_workspace import router as google_workspace_router
from .maps import router as maps_router
from .ollama import router as ollama_router

router = APIRouter(prefix="/api/agent", tags=["agent-integrations"])
router.include_router(maps_router)
router.include_router(ollama_router)
router.include_router(brave_router)
router.include_router(google_workspace_router)
