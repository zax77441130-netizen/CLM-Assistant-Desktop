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
        "WALK",
        "DIRECTORY_SUMMARY",
        "FIND_LARGE_FILES",
        "LIST_BY_EXTENSION",
        "COMPARE_FILES",
        "PREVIEW_BATCH",
        "STAT_PATH",
        "READ_TEXT",
        "SEARCH_FILES",
        "HASH_FILE",
        "FIND_DUPLICATES",
        "CREATE_DIRECTORY",
        "WRITE_NEW_TEXT",
        "APPEND_TEXT",
        "COPY_FILE",
        "MOVE_FILE",
        "RENAME_FILE",
        "BATCH_COPY",
        "BATCH_MOVE",
        "BATCH_RENAME",
        "CREATE_ZIP",
        "EXTRACT_ZIP",
        "MOVE_TO_RECOVERY_BIN",
        "RESTORE_FROM_RECOVERY_BIN",
        "OVERWRITE_TEXT",
        "SYSTEM_INFO",
        "LIST_PROCESSES",
        "LIST_REGISTERED_APPS",
        "LAUNCH_REGISTERED_APP",
        "OPEN_WORKSPACE_FILE",
        "OPEN_WORKSPACE_FOLDER",
        "CLIPBOARD_READ_TEXT",
        "CLIPBOARD_WRITE_TEXT",
        "TERMINATE_PROCESS",
        "DESKTOP_LIST_WINDOWS",
        "DESKTOP_WAIT_FOR_WINDOW",
        "DESKTOP_ACTIVATE_WINDOW",
        "DESKTOP_GET_WINDOW_STATE",
        "DESKTOP_SET_WINDOW_STATE",
        "DESKTOP_INSPECT_CONTROLS",
        "DESKTOP_READ_CONTROL_TEXT",
        "DESKTOP_INVOKE_CONTROL",
        "DESKTOP_SET_CONTROL_TEXT",
        "DESKTOP_SELECT_ITEM",
        "DESKTOP_SCROLL_CONTROL",
        "DESKTOP_CLOSE_WINDOW",
        "DESKTOP_CAPTURE_WINDOW",
        "ENGINEERING_RUN",
        "UNDO_ACTION",
    ]
    workspace_id: str | None = None
    path: str | None = None
    destination: str | None = None
    content: str | None = Field(default=None, max_length=1024 * 1024)
    text: str | None = Field(default=None, max_length=1024 * 1024)
    query: str | None = Field(default=None, max_length=120)
    search_content: bool = False
    max_depth: int = Field(default=5, ge=0, le=20)
    limit: int = Field(default=100, gt=0, le=1000)
    min_size_bytes: int | None = Field(default=None, ge=0)
    extension: str | None = Field(default=None, max_length=40)
    other_path: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list, max_length=1000)
    recovery_item_id: str | None = Field(default=None, max_length=80)
    process_id: int | None = Field(default=None, ge=1)
    app: str | None = Field(default=None, max_length=80)
    window: dict[str, Any] | None = None
    control: dict[str, Any] | None = None
    window_state: str | None = Field(default=None, max_length=20)
    item_name: str | None = Field(default=None, max_length=240)
    direction: str | None = Field(default=None, max_length=20)
    timeout_seconds: int = Field(default=10, gt=0, le=60)
    approval_id: str | None = None
    undo_record_id: str | None = None
    app_id: str | None = None
    command_id: str | None = Field(default=None, pattern="^(test|build)$")


class TaskResponse(BaseModel):
    id: str
    title: str
    state: TaskState
    workspace_id: str | None = None
    created_at: str | None = None
    summary: str | None = None
    observation: dict[str, Any] | None = None
    approval_id: str | None = None
    undo_record_id: str | None = None


class AssistantTaskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    workspace_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=120)


class ClarificationAnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=1000)


class TaskEventResponse(BaseModel):
    event_type: str
    from_state: str | None = None
    to_state: str | None = None
    message: str
    created_at: str


class TaskCenterItemResponse(BaseModel):
    id: str
    title: str
    state: TaskState
    workspace_id: str | None = None
    workspace_path: str | None = None
    created_at: str
    progress: list[str] = Field(default_factory=list)
    pending_approval: bool = False
    summary: str | None = None


class AssistantPlanStepResponse(BaseModel):
    title: str
    reason: str
    status: str = "等待中"


class TaskCenterDetailResponse(TaskCenterItemResponse):
    events: list[TaskEventResponse] = Field(default_factory=list)
    steps: list[AssistantPlanStepResponse] = Field(default_factory=list)
    observationPreview: str | None = None
    technicalDetails: dict[str, Any] | None = None
    undo_record_id: str | None = None


class AssistantPlanResponse(BaseModel):
    version: int = 1
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
                version=int(plan_data.get("version", 1)),
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
        "desktop.list_windows": "列出目前視窗",
        "desktop.wait_for_window": "尋找目標視窗",
        "desktop.activate_window": "切換到視窗",
        "desktop.get_window_state": "查看視窗狀態",
        "desktop.set_window_state": "調整視窗狀態",
        "desktop.inspect_controls": "檢查視窗控制項",
        "desktop.read_control_text": "讀取控制項文字",
        "desktop.invoke_control": "操作控制項",
        "desktop.set_control_text": "輸入文字",
        "desktop.select_item": "選擇項目",
        "desktop.scroll_control": "捲動控制項",
        "desktop.close_window": "關閉視窗",
        "desktop.capture_window": "擷取視窗畫面",
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
