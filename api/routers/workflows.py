"""P6-02 — Workflow REST router.

Routes:
    POST /api/workflows/generate    — NL description → workflow YAML/JSON
    POST /api/workflows/validate    — validate a workflow definition dict
    GET  /api/workflows             — list saved workflows for this tenant
    POST /api/workflows             — save a new workflow definition
    GET  /api/workflows/{id}        — get a saved workflow
    PUT  /api/workflows/{id}        — update a saved workflow
    DELETE /api/workflows/{id}      — delete a workflow (204)
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.auth import get_current_user_id

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# ── Request bodies ─────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    description: str
    max_steps: int = 8


class ValidateRequest(BaseModel):
    definition: dict[str, Any]


class SaveWorkflowRequest(BaseModel):
    name: str
    description: str = ""
    definition: dict[str, Any]


# ── Simple in-process store (JSON file) ───────────────────────────────────────
# A lightweight file-backed store matching the pattern used by report_scheduler.

import threading
from pathlib import Path

_store_lock = threading.Lock()


def _store_path() -> Path:
    root = Path(".maia_agent")
    root.mkdir(parents=True, exist_ok=True)
    return root / "workflows.json"


def _load_all() -> list[dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_all(rows: list[dict[str, Any]]) -> None:
    _store_path().write_text(json.dumps(rows, indent=2), encoding="utf-8")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/generate")
def generate_workflow(
    body: GenerateRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Generate a workflow definition from a plain-English description."""
    from api.services.agents.nl_workflow_builder import generate_workflow as _gen

    if not body.description.strip():
        raise HTTPException(status_code=400, detail="description must not be empty.")
    try:
        definition = _gen(
            body.description,
            tenant_id=user_id,
            max_steps=max(1, min(body.max_steps, 20)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"definition": definition}


@router.post("/validate")
def validate_workflow(
    body: ValidateRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Validate a workflow definition dict against the schema."""
    from api.services.agents.nl_workflow_builder import validate_workflow as _val
    return _val(body.definition)


@router.get("")
def list_workflows(
    user_id: str = Depends(get_current_user_id),
) -> list[dict[str, Any]]:
    with _store_lock:
        rows = _load_all()
    return [r for r in rows if r.get("tenant_id") == user_id]


@router.post("", status_code=status.HTTP_201_CREATED)
def save_workflow(
    body: SaveWorkflowRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    now = time.time()
    row: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "tenant_id": user_id,
        "name": body.name.strip() or "Untitled workflow",
        "description": body.description,
        "definition": body.definition,
        "created_at": now,
        "updated_at": now,
    }
    with _store_lock:
        rows = _load_all()
        rows.append(row)
        _save_all(rows)
    return row


@router.get("/{workflow_id}")
def get_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    with _store_lock:
        rows = _load_all()
    row = next((r for r in rows if r["id"] == workflow_id and r.get("tenant_id") == user_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return row


@router.put("/{workflow_id}")
def update_workflow(
    workflow_id: str,
    body: SaveWorkflowRequest,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    with _store_lock:
        rows = _load_all()
        for i, row in enumerate(rows):
            if row["id"] == workflow_id and row.get("tenant_id") == user_id:
                rows[i] = {
                    **row,
                    "name": body.name.strip() or row["name"],
                    "description": body.description,
                    "definition": body.definition,
                    "updated_at": time.time(),
                }
                _save_all(rows)
                return rows[i]
    raise HTTPException(status_code=404, detail="Workflow not found.")


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user_id),
) -> None:
    with _store_lock:
        rows = _load_all()
        before = len(rows)
        rows = [r for r in rows if not (r["id"] == workflow_id and r.get("tenant_id") == user_id)]
        if len(rows) == before:
            raise HTTPException(status_code=404, detail="Workflow not found.")
        _save_all(rows)
