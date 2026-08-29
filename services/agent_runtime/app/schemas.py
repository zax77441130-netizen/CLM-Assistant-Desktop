from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import TaskState


class WorkspaceGrantCreate(BaseModel):
    root_path: str = Field(min_length=1, max_length=2048)
    display_name: str | None = Field(default=None, max_length=240)
    permission_profile: str = Field(default="standard", max_length=80)


class WorkspaceGrantResponse(BaseModel):
    id: str
    display_name: str
    display_path: str
    enabled: bool
    permission_profile: str


class StructuredTaskRequest(BaseModel):
    task_type: Literal[
        "LIST_DIRECTORY",
        "STAT_PATH",
        "READ_TEXT",
        "SEARCH_FILES",
        "HASH_FILE",
        "FIND_DUPLICATES",
        "CREATE_DIRECTORY",
        "WRITE_NEW_TEXT",
        "COPY_FILE",
        "MOVE_FILE",
        "RENAME_FILE",
        "OVERWRITE_TEXT",
        "SYSTEM_INFO",
        "LIST_PROCESSES",
        "LIST_REGISTERED_APPS",
        "LAUNCH_REGISTERED_APP",
        "UNDO_ACTION",
    ]
    workspace_id: str | None = None
    path: str | None = None
    destination: str | None = None
    content: str | None = Field(default=None, max_length=1024 * 1024)
    query: str | None = Field(default=None, max_length=120)
    search_content: bool = False
    approval_id: str | None = None
    undo_record_id: str | None = None
    app_id: str | None = None


class TaskResponse(BaseModel):
    id: str
    title: str
    state: TaskState
    summary: str | None = None
    observation: dict[str, Any] | None = None
    approval_id: str | None = None
    undo_record_id: str | None = None


class ApprovalDecisionRequest(BaseModel):
    approve: bool


class ApprovalResponse(BaseModel):
    id: str
    task_id: str
    action_id: str
    tool_name: str
    argument_hash: str
    risk_level: str
    risk_reason: str
    status: str
    expires_at: str
