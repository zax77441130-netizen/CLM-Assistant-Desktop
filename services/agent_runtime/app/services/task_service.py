from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Task, TaskState


class MockTaskService:
    """Foundation-only service used to validate persistence and UI data flow."""

    def ensure_seed_task(self, db: Session) -> Task:
        existing = db.scalar(select(Task).limit(1))
        if existing:
            return existing
        task = Task(title="Foundation runtime boot check", state=TaskState.RECEIVED)
        db.add(task)
        db.commit()
        db.refresh(task)
        return task
