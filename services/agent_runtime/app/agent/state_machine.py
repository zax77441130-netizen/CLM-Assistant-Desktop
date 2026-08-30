from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Task, TaskEvent, TaskState


ALLOWED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.CREATED: {TaskState.PLANNING, TaskState.QUEUED, TaskState.CANCELLING, TaskState.FAILED},
    TaskState.PLANNING: {TaskState.WAITING_CLARIFICATION, TaskState.QUEUED, TaskState.RUNNING, TaskState.FAILED, TaskState.CANCELLING},
    TaskState.WAITING_CLARIFICATION: {TaskState.PLANNING, TaskState.CANCELLING, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.QUEUED: {TaskState.RUNNING, TaskState.CANCELLING, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.RUNNING: {TaskState.WAITING_APPROVAL, TaskState.RETRYING, TaskState.CANCELLING, TaskState.COMPLETED, TaskState.FAILED, TaskState.NEEDS_REVIEW},
    TaskState.WAITING_APPROVAL: {TaskState.RUNNING, TaskState.CANCELLING, TaskState.CANCELLED, TaskState.BLOCKED, TaskState.FAILED},
    TaskState.RETRYING: {TaskState.RUNNING, TaskState.CANCELLING, TaskState.FAILED, TaskState.NEEDS_REVIEW},
    TaskState.CANCELLING: {TaskState.CANCELLED, TaskState.NEEDS_REVIEW},
    TaskState.NEEDS_REVIEW: {TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.RECEIVED: {TaskState.PLANNING, TaskState.RUNNING, TaskState.FAILED, TaskState.BLOCKED},
    TaskState.ANALYZING: {TaskState.RUNNING, TaskState.COMPLETED, TaskState.FAILED, TaskState.BLOCKED, TaskState.WAITING_APPROVAL},
    TaskState.NEEDS_INPUT: {TaskState.PLANNING, TaskState.CANCELLED},
    TaskState.PLANNED: {TaskState.QUEUED, TaskState.RUNNING, TaskState.CANCELLED},
    TaskState.VERIFYING: {TaskState.COMPLETED, TaskState.FAILED, TaskState.NEEDS_REVIEW},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
    TaskState.BLOCKED: set(),
}


class InvalidTransitionError(ValueError):
    pass


class TaskStateService:
    def transition(self, db: Session, task: Task, to_state: TaskState, message: str, payload: dict[str, Any] | None = None) -> None:
        from_state = task.state
        if from_state != to_state and to_state not in ALLOWED_TRANSITIONS.get(from_state, set()):
            raise InvalidTransitionError(f"INVALID_TASK_TRANSITION:{from_state.value}->{to_state.value}")
        task.state = to_state
        db.add(
            TaskEvent(
                task_id=task.id,
                event_type="state.transition",
                from_state=from_state.value,
                to_state=to_state.value,
                message=message,
                payload=payload or {},
            )
        )
