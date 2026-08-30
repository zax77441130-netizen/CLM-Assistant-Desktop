from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tool_sdk import argument_hash
from app.models import ExecutionLease, IdempotencyRecord


class ExecutionConflictError(ValueError):
    pass


class IdempotencyConflictError(ValueError):
    pass


def request_hash(payload: dict[str, Any]) -> str:
    return argument_hash(payload)


class IdempotencyService:
    def existing_response(self, db: Session, key: str | None, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not key:
            return None
        row = db.get(IdempotencyRecord, key)
        if row is None:
            return None
        if row.request_hash != request_hash(payload):
            raise IdempotencyConflictError("IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST")
        return row.response

    def remember(self, db: Session, key: str | None, payload: dict[str, Any], task_id: str, response: dict[str, Any]) -> None:
        if not key:
            return
        if db.get(IdempotencyRecord, key) is not None:
            return
        db.add(IdempotencyRecord(key=key, request_hash=request_hash(payload), task_id=task_id, response=json.loads(json.dumps(response, ensure_ascii=False))))


class ExecutionLockService:
    @contextmanager
    def hold(self, db: Session, workspace_id: str | None, task_id: str, path_keys: list[str]) -> Iterator[None]:
        if not workspace_id or not path_keys:
            yield
            return
        expires_at = datetime.now(UTC) + timedelta(minutes=5)
        normalized = sorted({key.lower().replace("/", "\\") for key in path_keys})
        held: list[ExecutionLease] = []
        try:
            for key in normalized:
                existing = db.scalar(
                    select(ExecutionLease)
                    .where(
                        ExecutionLease.workspace_id == workspace_id,
                        ExecutionLease.path_key == key,
                        ExecutionLease.status == "HELD",
                        ExecutionLease.expires_at > datetime.now(UTC),
                    )
                    .limit(1)
                )
                if existing and existing.holder_task_id != task_id:
                    raise ExecutionConflictError("WORKSPACE_PATH_BUSY")
                lease = ExecutionLease(workspace_id=workspace_id, path_key=key, holder_task_id=task_id, status="HELD", expires_at=expires_at)
                db.add(lease)
                held.append(lease)
            db.commit()
            yield
        finally:
            for lease in held:
                lease.status = "RELEASED"
            if held:
                db.commit()
