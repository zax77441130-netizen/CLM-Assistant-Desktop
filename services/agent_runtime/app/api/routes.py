from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.security import require_desktop_token
from app.agent.planner import OpenAIPlannerProvider
from app.agent.provider_settings import ProviderSettingsService
from app.agent.orchestrator import AgentOrchestrator, CancellationService
from app.core import host_tools
from app.db.session import get_db
from app.models import Action, Approval, Observation, Task, UndoRecord, WorkspaceGrant
from app.schemas import (
    ApprovalDecisionRequest,
    ApprovalResponse,
    AssistantTaskRequest,
    AssistantTaskResponse,
    ProviderKeyRequest,
    ProviderSettingsResponse,
    ProviderSettingsUpdate,
    StructuredTaskRequest,
    TaskResponse,
    WorkspaceGrantCreate,
    WorkspaceGrantResponse,
)
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


@router.post("/assistant/tasks", response_model=AssistantTaskResponse, dependencies=[Depends(require_desktop_token)])
def create_assistant_task(payload: AssistantTaskRequest, db: Session = Depends(get_db)) -> AssistantTaskResponse:
    return AgentOrchestrator(settings=ProviderSettingsService(db=db)).run(db, payload)


@router.post("/assistant/tasks/{task_id}/cancel", response_model=AssistantTaskResponse, dependencies=[Depends(require_desktop_token)])
def cancel_assistant_task(task_id: str, db: Session = Depends(get_db)) -> AssistantTaskResponse:
    return CancellationService().cancel(db, task_id)


def task_response(task: Task, db: Session) -> TaskResponse:
    action_ids = [item.id for item in db.query(Action).filter(Action.task_id == task.id).all()]
    observation = (
        db.query(Observation)
        .filter(Observation.action_id.in_(action_ids))
        .order_by(Observation.created_at.desc())
        .first()
        if action_ids
        else None
    )
    undo = (
        db.query(UndoRecord)
        .filter(UndoRecord.action_id.in_(action_ids), UndoRecord.status == "PENDING")
        .order_by(UndoRecord.created_at.desc())
        .first()
        if action_ids
        else None
    )
    return TaskResponse(
        id=task.id,
        title=task.title,
        state=task.state,
        summary=observation.summary if observation else None,
        observation=observation.evidence if observation else None,
        undo_record_id=undo.id if undo else None,
    )


@router.get("/tasks", response_model=list[TaskResponse], dependencies=[Depends(require_desktop_token)])
def list_tasks(db: Session = Depends(get_db)) -> list[TaskResponse]:
    tasks = db.query(Task).order_by(Task.created_at.desc()).limit(50).all()
    return [task_response(task, db) for task in tasks]


@router.get("/tasks/{task_id}", response_model=TaskResponse, dependencies=[Depends(require_desktop_token)])
def get_task(task_id: str, db: Session = Depends(get_db)) -> TaskResponse:
    task = db.get(Task, task_id)
    if task is None:
        raise ValueError("TASK_NOT_FOUND")
    return task_response(task, db)


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


@router.get("/host/registered-apps", dependencies=[Depends(require_desktop_token)])
def get_registered_apps() -> dict[str, object]:
    return host_tools.list_registered_apps().observation


@router.get("/provider/settings", response_model=ProviderSettingsResponse, dependencies=[Depends(require_desktop_token)])
def get_provider_settings(db: Session = Depends(get_db)) -> ProviderSettingsResponse:
    service = ProviderSettingsService(db=db)
    return ProviderSettingsResponse(mode=service.get_mode(), model=service.get_model(), apiKeyConfigured=service.api_key_configured())


@router.patch("/provider/settings", response_model=ProviderSettingsResponse, dependencies=[Depends(require_desktop_token)])
def update_provider_settings(payload: ProviderSettingsUpdate, db: Session = Depends(get_db)) -> ProviderSettingsResponse:
    service = ProviderSettingsService(db=db)
    if payload.mode is not None:
        service.set_mode(payload.mode)
    if payload.model is not None:
        service.set_model(payload.model)
    return ProviderSettingsResponse(mode=service.get_mode(), model=service.get_model(), apiKeyConfigured=service.api_key_configured())


@router.put("/provider/openai-key", response_model=ProviderSettingsResponse, dependencies=[Depends(require_desktop_token)])
def save_provider_key(payload: ProviderKeyRequest, db: Session = Depends(get_db)) -> ProviderSettingsResponse:
    service = ProviderSettingsService(db=db)
    service.set_api_key(payload.api_key)
    return ProviderSettingsResponse(mode=service.get_mode(), model=service.get_model(), apiKeyConfigured=service.api_key_configured())


@router.delete("/provider/openai-key", response_model=ProviderSettingsResponse, dependencies=[Depends(require_desktop_token)])
def delete_provider_key(db: Session = Depends(get_db)) -> ProviderSettingsResponse:
    service = ProviderSettingsService(db=db)
    service.delete_api_key()
    return ProviderSettingsResponse(mode=service.get_mode(), model=service.get_model(), apiKeyConfigured=service.api_key_configured())


@router.post("/provider/test", dependencies=[Depends(require_desktop_token)])
def test_provider(db: Session = Depends(get_db)) -> dict[str, object]:
    service = ProviderSettingsService(db=db)
    if service.get_mode() == "local":
        return {"ok": True, "message": "本機指令模式可用。"}
    return {"ok": OpenAIPlannerProvider(service).test_connection(), "message": "OpenAI API Key 已設定。" if service.api_key_configured() else "尚未設定 OpenAI API Key。"}
