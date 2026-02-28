from __future__ import annotations

from fastapi import APIRouter

from .connectors import router as connectors_router
from .events import router as events_router
from .governance import router as governance_router
from .oauth import router as oauth_router
from .playbooks import router as playbooks_router
from .runs import router as runs_router
from .schedules import router as schedules_router

router = APIRouter(prefix="/api/agent", tags=["agent"])
router.include_router(connectors_router)
router.include_router(oauth_router)
router.include_router(events_router)
router.include_router(runs_router)
router.include_router(playbooks_router)
router.include_router(schedules_router)
router.include_router(governance_router)
