from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKED = "BLOCKED"


class ToolCapability(str, Enum):
    FILE_READ = "FILE_READ"
    FILE_WRITE = "FILE_WRITE"
    PROCESS_READ = "PROCESS_READ"
    COMMAND_EXECUTION = "COMMAND_EXECUTION"


class ToolDefinition(BaseModel):
    name: str
    capability: ToolCapability
    risk_level: RiskLevel
    required_permission: str
    timeout_seconds: int = Field(gt=0, le=600)
    retryable: bool
    has_side_effects: bool
    supports_undo: bool
    supports_idempotency_key: bool


class ToolObservation(BaseModel):
    status: str
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    sanitized_output: str = ""
