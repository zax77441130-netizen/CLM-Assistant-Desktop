from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    HIGH_RISK = "HIGH_RISK"
    BLOCKED = "BLOCKED"


class PolicyDecision(str, Enum):
    AUTO = "AUTO"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    BLOCK = "BLOCK"


class RetryPolicy(BaseModel):
    retryable: bool = False
    max_attempts: int = 1


class ToolEvidence(BaseModel):
    kind: str
    data: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    success: bool
    status: str
    summary: str
    observation: dict[str, Any] = Field(default_factory=dict)
    evidence: list[ToolEvidence] = Field(default_factory=list)
    error_code: str | None = None
    retryable: bool = False
    side_effect: bool = False
    undo_record_id: str | None = None
    started_at: datetime
    finished_at: datetime


InputModel = TypeVar("InputModel", bound=BaseModel)
OutputModel = TypeVar("OutputModel", bound=BaseModel)
Handler = Callable[[InputModel], ToolResult]


class ToolDefinition(BaseModel, Generic[InputModel, OutputModel]):
    name: str
    description: str
    input_schema: type[InputModel]
    output_schema: type[OutputModel]
    capability: str
    risk_level: RiskLevel
    required_permissions: list[str]
    timeout_seconds: int = Field(gt=0, le=120)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    has_side_effect: bool
    supports_undo: bool
    idempotency_policy: str
    handler: Handler[InputModel]

    model_config = {"arbitrary_types_allowed": True}


def now_utc() -> datetime:
    return datetime.now(UTC)


def argument_hash(arguments: dict[str, Any]) -> str:
    normalized = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition[Any, Any]] = {}

    def register(self, definition: ToolDefinition[Any, Any]) -> None:
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition[Any, Any]:
        if name not in self._tools:
            raise KeyError(name)
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)
