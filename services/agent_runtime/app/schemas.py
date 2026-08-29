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


class AssistantTaskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    workspace_id: str | None = None


class AssistantPlanStepResponse(BaseModel):
    title: str
    reason: str
    status: str = "等待中"


class AssistantPlanResponse(BaseModel):
    goal: str
    needsClarification: bool
    clarificationQuestion: str | None = None
    steps: list[AssistantPlanStepResponse] = Field(default_factory=list)


class AssistantTaskResponse(BaseModel):
    id: str
    state: TaskState
    providerMode: str = "local"
    summary: str | None = None
    plan: AssistantPlanResponse | None = None
    progress: list[str] = Field(default_factory=list)
    resultText: str | None = None
    observationPreview: str | None = None
    technicalDetails: dict[str, Any] | None = None
    approval_id: str | None = None
    undo_record_id: str | None = None

    @classmethod
    def from_task(
        cls,
        task: object,
        *,
        plan: object | None = None,
        progress: list[str] | None = None,
        summary: str | None = None,
        observation: dict[str, Any] | None = None,
        approval_id: str | None = None,
        undo_record_id: str | None = None,
        providerMode: str = "local",
    ) -> "AssistantTaskResponse":
        safe_plan = None
        if plan is not None:
            plan_data = plan.model_dump() if isinstance(plan, BaseModel) else {}
            safe_plan = AssistantPlanResponse(
                goal=str(plan_data.get("goal", "")),
                needsClarification=bool(plan_data.get("needsClarification", False)),
                clarificationQuestion=plan_data.get("clarificationQuestion"),
                steps=[
                    AssistantPlanStepResponse(title=tool_title(str(step.get("tool", ""))), reason=str(step.get("reason", "")))
                    for step in plan_data.get("steps", [])
                    if isinstance(step, dict)
                ],
            )
        preview = observation_preview(observation)
        return cls(
            id=str(getattr(task, "id")),
            state=getattr(task, "state"),
            providerMode=providerMode,
            summary=summary,
            resultText=summary,
            plan=safe_plan,
            progress=progress or [],
            observationPreview=preview,
            technicalDetails=observation,
            approval_id=approval_id,
            undo_record_id=undo_record_id,
        )


class ProviderSettingsResponse(BaseModel):
    mode: str
    model: str
    apiKeyConfigured: bool


class ProviderSettingsUpdate(BaseModel):
    mode: str | None = Field(default=None, max_length=40)
    model: str | None = Field(default=None, max_length=120)


class ProviderKeyRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)


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


def tool_title(tool: str) -> str:
    return {
        "filesystem.list_directory": "列出工作區內容",
        "filesystem.stat": "查看檔案資訊",
        "filesystem.read_text": "讀取文字檔",
        "filesystem.search": "搜尋檔案",
        "filesystem.hash_file": "計算檔案雜湊",
        "filesystem.find_duplicates": "尋找重複檔案",
        "filesystem.create_directory": "建立資料夾",
        "filesystem.write_new_text": "建立文字檔",
        "filesystem.copy": "複製檔案",
        "filesystem.move": "移動檔案",
        "filesystem.rename": "重新命名",
        "filesystem.overwrite_text": "覆寫文字檔",
        "host.system_info": "查看系統資訊",
        "host.list_processes": "查看目前程序",
        "host.list_registered_apps": "查看可開啟的應用程式",
        "host.launch_registered_app": "開啟應用程式",
    }.get(tool, "執行安全步驟")


def observation_preview(observation: dict[str, Any] | None) -> str | None:
    if not observation:
        return None
    if "entries" in observation and isinstance(observation["entries"], list):
        return None
    if "content" in observation:
        content = str(observation.get("content", ""))
        return content[:2000]
    if "duplicates" in observation and isinstance(observation["duplicates"], list):
        if not observation["duplicates"]:
            return "沒有重複檔案。"
        lines = []
        for group in observation["duplicates"][:10]:
            if isinstance(group, dict):
                paths = group.get("paths", [])
                if isinstance(paths, list):
                    lines.append("、".join(str(path) for path in paths))
        return "\n".join(lines)
    return None
