from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import Task, TaskState
from app.services.task_service import MockTaskService


def test_task_persistence() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        task = MockTaskService().ensure_seed_task(db)
        assert task.state == TaskState.RECEIVED
        assert db.get(Task, task.id) is not None
