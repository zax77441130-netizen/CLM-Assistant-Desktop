from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.security import require_desktop_token
from app.db.session import get_db
from app.services.task_service import MockTaskService

router = APIRouter()


class RuntimeStatusResponse(BaseModel):
    host: str
    port: int
    pid: int
    state: str
    tokenExposedToRenderer: bool
    databaseReady: bool
    startedAt: str


STARTED_AT = datetime.now(UTC).isoformat()


@router.get("/runtime/status", response_model=RuntimeStatusResponse, dependencies=[Depends(require_desktop_token)])
def runtime_status(db: Session = Depends(get_db)) -> RuntimeStatusResponse:
    MockTaskService().ensure_seed_task(db)
    return RuntimeStatusResponse(
        host="127.0.0.1",
        port=int(os.environ.get("CLM_RUNTIME_PORT", "0")),
        pid=os.getpid(),
        state="running",
        tokenExposedToRenderer=False,
        databaseReady=True,
        startedAt=STARTED_AT,
    )


@router.post("/runtime/shutdown", dependencies=[Depends(require_desktop_token)])
def runtime_shutdown() -> dict[str, str]:
    return {"status": "shutdown_requested"}
