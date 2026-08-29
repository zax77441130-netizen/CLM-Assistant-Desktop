from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


class TaskState(str, enum.Enum):
    RECEIVED = "RECEIVED"
    ANALYZING = "ANALYZING"
    NEEDS_INPUT = "NEEDS_INPUT"
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(240))
    state: Mapped[TaskState] = mapped_column(Enum(TaskState), default=TaskState.RECEIVED)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    steps: Mapped[list[TaskStep]] = relationship(back_populates="task", cascade="all, delete-orphan")
    actions: Mapped[list[Action]] = relationship(back_populates="task", cascade="all, delete-orphan")


class TaskStep(Base):
    __tablename__ = "task_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    title: Mapped[str] = mapped_column(String(240))
    state: Mapped[TaskState] = mapped_column(Enum(TaskState), default=TaskState.RECEIVED)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    task: Mapped[Task] = relationship(back_populates="steps")


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    tool_name: Mapped[str] = mapped_column(String(160))
    arguments_hash: Mapped[str] = mapped_column(String(128))
    risk_level: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="PENDING")
    task: Mapped[Task] = relationship(back_populates="actions")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"))
    exact_tool: Mapped[str] = mapped_column(String(160))
    exact_arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    argument_hash: Mapped[str] = mapped_column(String(128))
    working_directory: Mapped[str] = mapped_column(Text)
    risk_reason: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"))
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    path: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class UndoRecord(Base):
    __tablename__ = "undo_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action_id: Mapped[str] = mapped_column(ForeignKey("actions.id"))
    undo_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_template: Mapped[dict[str, Any]] = mapped_column(JSON)
    cron: Mapped[str] = mapped_column(String(120))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
