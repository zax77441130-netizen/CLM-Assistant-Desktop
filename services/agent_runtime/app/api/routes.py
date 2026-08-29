from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.security import require_desktop_token
from app.db.session import get_db
from app.models import Approval, WorkspaceGrant
from app.schemas import ApprovalDecisionRequest, ApprovalResponse, StructuredTaskRequest, TaskResponse, WorkspaceGrantCreate, WorkspaceGrantResponse
from app.services.task_service import MockTaskService
from app.services.structured_task_service import StructuredTaskService

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


def workspace_response(grant: WorkspaceGrant) -> WorkspaceGrantResponse:
    return WorkspaceGrantResponse(
        id=grant.id,
        display_name=grant.display_name,
        display_path=grant.root_path,
        enabled=grant.enabled,
        permission_profile=grant.permission_profile,
    )


@router.post("/workspaces", response_model=WorkspaceGrantResponse, dependencies=[Depends(require_desktop_token)])
def create_workspace(payload: WorkspaceGrantCreate, db: Session = Depends(get_db)) -> WorkspaceGrantResponse:
    return workspace_response(StructuredTaskService().create_workspace(db, payload))


@router.get("/workspaces", response_model=list[WorkspaceGrantResponse], dependencies=[Depends(require_desktop_token)])
def list_workspaces(db: Session = Depends(get_db)) -> list[WorkspaceGrantResponse]:
    return [workspace_response(grant) for grant in StructuredTaskService().list_workspaces(db)]


@router.post("/tasks/structured", response_model=TaskResponse, dependencies=[Depends(require_desktop_token)])
def create_structured_task(payload: StructuredTaskRequest, db: Session = Depends(get_db)) -> TaskResponse:
    return StructuredTaskService().create_task(db, payload)


@router.post("/approvals/{approval_id}/decision", response_model=TaskResponse, dependencies=[Depends(require_desktop_token)])
def decide_approval(approval_id: str, payload: ApprovalDecisionRequest, db: Session = Depends(get_db)) -> TaskResponse:
    return StructuredTaskService().decide_approval(db, approval_id, payload.approve)


@router.get("/approvals", response_model=list[ApprovalResponse], dependencies=[Depends(require_desktop_token)])
def list_approvals(db: Session = Depends(get_db)) -> list[ApprovalResponse]:
    approvals = db.query(Approval).order_by(Approval.created_at.desc()).limit(50).all()
    return [
        ApprovalResponse(
            id=item.id,
            task_id=item.task_id,
            action_id=item.action_id,
            tool_name=item.tool_name,
            argument_hash=item.argument_hash,
            risk_level=item.risk_level,
            risk_reason=item.risk_reason,
            status=item.status,
            expires_at=item.expires_at.isoformat(),
        )
        for item in approvals
    ]


@router.post("/undo/{undo_record_id}", response_model=TaskResponse, dependencies=[Depends(require_desktop_token)])
def undo_action(undo_record_id: str, db: Session = Depends(get_db)) -> TaskResponse:
    return StructuredTaskService().undo(db, undo_record_id)
