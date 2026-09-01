from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


ALLOWED_TOOLS = {
    "filesystem.list_directory",
    "filesystem.walk",
    "filesystem.directory_summary",
    "filesystem.find_large_files",
    "filesystem.list_by_extension",
    "filesystem.compare_files",
    "filesystem.preview_batch",
    "filesystem.stat",
    "filesystem.read_text",
    "filesystem.search",
    "filesystem.hash_file",
    "filesystem.find_duplicates",
    "filesystem.create_directory",
    "filesystem.write_new_text",
    "filesystem.append_text",
    "filesystem.copy",
    "filesystem.move",
    "filesystem.rename",
    "filesystem.batch_copy",
    "filesystem.batch_move",
    "filesystem.batch_rename",
    "filesystem.create_zip",
    "filesystem.extract_zip",
    "filesystem.move_to_recovery_bin",
    "filesystem.restore_from_recovery_bin",
    "filesystem.overwrite_text",
    "host.system_info",
    "host.list_processes",
    "host.list_registered_apps",
    "host.launch_registered_app",
    "host.open_workspace_file",
    "host.open_workspace_folder",
    "host.clipboard_read_text",
    "host.clipboard_write_text",
    "host.terminate_process",
}


TOOL_TO_TASK_TYPE = {
    "filesystem.list_directory": "LIST_DIRECTORY",
    "filesystem.walk": "WALK",
    "filesystem.directory_summary": "DIRECTORY_SUMMARY",
    "filesystem.find_large_files": "FIND_LARGE_FILES",
    "filesystem.list_by_extension": "LIST_BY_EXTENSION",
    "filesystem.compare_files": "COMPARE_FILES",
    "filesystem.preview_batch": "PREVIEW_BATCH",
    "filesystem.stat": "STAT_PATH",
    "filesystem.read_text": "READ_TEXT",
    "filesystem.search": "SEARCH_FILES",
    "filesystem.hash_file": "HASH_FILE",
    "filesystem.find_duplicates": "FIND_DUPLICATES",
    "filesystem.create_directory": "CREATE_DIRECTORY",
    "filesystem.write_new_text": "WRITE_NEW_TEXT",
    "filesystem.append_text": "APPEND_TEXT",
    "filesystem.copy": "COPY_FILE",
    "filesystem.move": "MOVE_FILE",
    "filesystem.rename": "RENAME_FILE",
    "filesystem.batch_copy": "BATCH_COPY",
    "filesystem.batch_move": "BATCH_MOVE",
    "filesystem.batch_rename": "BATCH_RENAME",
    "filesystem.create_zip": "CREATE_ZIP",
    "filesystem.extract_zip": "EXTRACT_ZIP",
    "filesystem.move_to_recovery_bin": "MOVE_TO_RECOVERY_BIN",
    "filesystem.restore_from_recovery_bin": "RESTORE_FROM_RECOVERY_BIN",
    "filesystem.overwrite_text": "OVERWRITE_TEXT",
    "host.system_info": "SYSTEM_INFO",
    "host.list_processes": "LIST_PROCESSES",
    "host.list_registered_apps": "LIST_REGISTERED_APPS",
    "host.launch_registered_app": "LAUNCH_REGISTERED_APP",
    "host.open_workspace_file": "OPEN_WORKSPACE_FILE",
    "host.open_workspace_folder": "OPEN_WORKSPACE_FOLDER",
    "host.clipboard_read_text": "CLIPBOARD_READ_TEXT",
    "host.clipboard_write_text": "CLIPBOARD_WRITE_TEXT",
    "host.terminate_process": "TERMINATE_PROCESS",
}


READ_ONLY_TOOLS = {
    "filesystem.list_directory",
    "filesystem.walk",
    "filesystem.directory_summary",
    "filesystem.find_large_files",
    "filesystem.list_by_extension",
    "filesystem.compare_files",
    "filesystem.preview_batch",
    "filesystem.stat",
    "filesystem.read_text",
    "filesystem.search",
    "filesystem.hash_file",
    "filesystem.find_duplicates",
    "host.system_info",
    "host.list_processes",
    "host.list_registered_apps",
}


APPROVAL_REQUIRED_TOOLS = {
    "filesystem.overwrite_text",
    "filesystem.extract_zip",
    "filesystem.move_to_recovery_bin",
    "host.clipboard_read_text",
    "host.launch_registered_app",
    "host.terminate_process",
}


WORKSPACE_TOOLS = {
    "filesystem.list_directory",
    "filesystem.walk",
    "filesystem.directory_summary",
    "filesystem.find_large_files",
    "filesystem.list_by_extension",
    "filesystem.compare_files",
    "filesystem.preview_batch",
    "filesystem.stat",
    "filesystem.read_text",
    "filesystem.search",
    "filesystem.hash_file",
    "filesystem.find_duplicates",
    "filesystem.create_directory",
    "filesystem.write_new_text",
    "filesystem.append_text",
    "filesystem.copy",
    "filesystem.move",
    "filesystem.rename",
    "filesystem.batch_copy",
    "filesystem.batch_move",
    "filesystem.batch_rename",
    "filesystem.create_zip",
    "filesystem.extract_zip",
    "filesystem.move_to_recovery_bin",
    "filesystem.restore_from_recovery_bin",
    "filesystem.overwrite_text",
    "host.open_workspace_file",
    "host.open_workspace_folder",
}


class PlanStepSpec(BaseModel):
    tool: str = Field(min_length=1, max_length=160)
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=500)
    dependsOn: list[int] = Field(default_factory=list, max_length=5)

    @field_validator("tool")
    @classmethod
    def tool_must_be_registered(cls, value: str) -> str:
        if value not in ALLOWED_TOOLS:
            raise ValueError("UNKNOWN_TOOL")
        return value


class AgentPlan(BaseModel):
    version: int = Field(default=1, ge=1)
    goal: str = Field(min_length=1, max_length=500)
    needsClarification: bool
    clarificationQuestion: str | None = Field(default=None, max_length=500)
    steps: list[PlanStepSpec] = Field(default_factory=list, max_length=10)

    @field_validator("steps")
    @classmethod
    def clarification_has_no_steps(cls, value: list[PlanStepSpec], info: object) -> list[PlanStepSpec]:
        return value


class PlanContext(BaseModel):
    request: str
    workspace_id: str | None = None
    provider_mode: str = "local"
    max_steps: int = 10
    max_replans: int = 2


class ProviderStatus(BaseModel):
    mode: str
    model: str
    apiKeyConfigured: bool
