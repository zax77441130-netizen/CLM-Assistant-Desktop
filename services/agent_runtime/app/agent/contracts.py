from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


ALLOWED_TOOLS = {
    "filesystem.list_directory",
    "filesystem.stat",
    "filesystem.read_text",
    "filesystem.search",
    "filesystem.hash_file",
    "filesystem.find_duplicates",
    "filesystem.create_directory",
    "filesystem.write_new_text",
    "filesystem.copy",
    "filesystem.move",
    "filesystem.rename",
    "filesystem.overwrite_text",
    "host.system_info",
    "host.list_processes",
    "host.list_registered_apps",
    "host.launch_registered_app",
}


TOOL_TO_TASK_TYPE = {
    "filesystem.list_directory": "LIST_DIRECTORY",
    "filesystem.stat": "STAT_PATH",
    "filesystem.read_text": "READ_TEXT",
    "filesystem.search": "SEARCH_FILES",
    "filesystem.hash_file": "HASH_FILE",
    "filesystem.find_duplicates": "FIND_DUPLICATES",
    "filesystem.create_directory": "CREATE_DIRECTORY",
    "filesystem.write_new_text": "WRITE_NEW_TEXT",
    "filesystem.copy": "COPY_FILE",
    "filesystem.move": "MOVE_FILE",
    "filesystem.rename": "RENAME_FILE",
    "filesystem.overwrite_text": "OVERWRITE_TEXT",
    "host.system_info": "SYSTEM_INFO",
    "host.list_processes": "LIST_PROCESSES",
    "host.list_registered_apps": "LIST_REGISTERED_APPS",
    "host.launch_registered_app": "LAUNCH_REGISTERED_APP",
}


READ_ONLY_TOOLS = {
    "filesystem.list_directory",
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
    "host.launch_registered_app",
}


WORKSPACE_TOOLS = {
    "filesystem.list_directory",
    "filesystem.stat",
    "filesystem.read_text",
    "filesystem.search",
    "filesystem.hash_file",
    "filesystem.find_duplicates",
    "filesystem.create_directory",
    "filesystem.write_new_text",
    "filesystem.copy",
    "filesystem.move",
    "filesystem.rename",
    "filesystem.overwrite_text",
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
