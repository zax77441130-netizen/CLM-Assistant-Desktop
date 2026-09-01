from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import asyncio
import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import RuntimeSettings
from app.db.migration_manager import (
    MigrationLock,
    MigrationLockError,
    UnrecognizedLegacyDatabaseError,
    backup_database,
    collect_diagnostics,
    migrate_to_head,
)
from app.models import Action, Task, UndoRecord
from app.services.structured_task_service import StructuredTaskService
from app.schemas import StructuredTaskRequest, WorkspaceGrantCreate


def settings(tmp_path: Path) -> RuntimeSettings:
    return RuntimeSettings(
        desktop_token="test-token",
        data_dir=tmp_path,
        resource_dir=tmp_path,
        state_file=tmp_path / "runtime-state.json",
    )


def db_path(tmp_path: Path) -> Path:
    return tmp_path / "clm_assistant.sqlite3"


def execute_script(path: Path, script: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(script)


def phase1_schema(path: Path) -> None:
    execute_script(
        path,
        """
        CREATE TABLE tasks (id VARCHAR(36) NOT NULL, title VARCHAR(240) NOT NULL, state VARCHAR(14) NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, PRIMARY KEY (id));
        CREATE TABLE task_steps (id VARCHAR(36) NOT NULL, task_id VARCHAR(36) NOT NULL, title VARCHAR(240) NOT NULL, state VARCHAR(14) NOT NULL, sort_order INTEGER NOT NULL, PRIMARY KEY (id), FOREIGN KEY(task_id) REFERENCES tasks (id));
        CREATE TABLE actions (id VARCHAR(36) NOT NULL, task_id VARCHAR(36) NOT NULL, tool_name VARCHAR(160) NOT NULL, arguments_hash VARCHAR(128) NOT NULL, risk_level VARCHAR(40) NOT NULL, status VARCHAR(40) NOT NULL, PRIMARY KEY (id), FOREIGN KEY(task_id) REFERENCES tasks (id));
        CREATE TABLE approvals (id VARCHAR(36) NOT NULL, action_id VARCHAR(36) NOT NULL, exact_tool VARCHAR(160) NOT NULL, exact_arguments JSON NOT NULL, argument_hash VARCHAR(128) NOT NULL, working_directory TEXT NOT NULL, risk_reason TEXT NOT NULL, expires_at DATETIME NOT NULL, approved BOOLEAN NOT NULL, PRIMARY KEY (id), FOREIGN KEY(action_id) REFERENCES actions (id));
        CREATE TABLE observations (id VARCHAR(36) NOT NULL, action_id VARCHAR(36) NOT NULL, summary TEXT NOT NULL, evidence JSON NOT NULL, created_at DATETIME NOT NULL, PRIMARY KEY (id), FOREIGN KEY(action_id) REFERENCES actions (id));
        CREATE TABLE artifacts (id VARCHAR(36) NOT NULL, task_id VARCHAR(36) NOT NULL, path TEXT NOT NULL, kind VARCHAR(80) NOT NULL, created_at DATETIME NOT NULL, PRIMARY KEY (id), FOREIGN KEY(task_id) REFERENCES tasks (id));
        CREATE TABLE undo_records (id VARCHAR(36) NOT NULL, action_id VARCHAR(36) NOT NULL, undo_type VARCHAR(80) NOT NULL, payload JSON NOT NULL, applied BOOLEAN NOT NULL, PRIMARY KEY (id), FOREIGN KEY(action_id) REFERENCES actions (id));
        CREATE TABLE audit_events (id VARCHAR(36) NOT NULL, event_type VARCHAR(120) NOT NULL, payload JSON NOT NULL, created_at DATETIME NOT NULL, PRIMARY KEY (id));
        CREATE TABLE scheduled_tasks (id VARCHAR(36) NOT NULL, task_template JSON NOT NULL, cron VARCHAR(120) NOT NULL, enabled BOOLEAN NOT NULL, PRIMARY KEY (id));
        INSERT INTO tasks VALUES ('task-1', 'LIST_DIRECTORY', 'COMPLETED', '2026-08-29 00:00:00', '2026-08-29 00:00:00');
        INSERT INTO task_steps VALUES ('step-1', 'task-1', 'LIST_DIRECTORY', 'COMPLETED', 1);
        INSERT INTO actions VALUES ('action-1', 'task-1', 'filesystem.list_directory', 'hash', 'READ', 'COMPLETED');
        INSERT INTO observations VALUES ('obs-1', 'action-1', 'ok', '{}', '2026-08-29 00:00:01');
        INSERT INTO undo_records VALUES ('undo-1', 'action-1', 'CREATE_DIRECTORY', '{}', 0);
        INSERT INTO audit_events VALUES ('audit-1', 'task.created', '{}', '2026-08-29 00:00:00');
        """,
    )


def phase2_partial_schema(path: Path, *, with_created_at: bool = False) -> None:
    phase1_schema(path)
    execute_script(
        path,
        """
        CREATE TABLE workspace_grants (id VARCHAR(36) NOT NULL, display_name VARCHAR(240) NOT NULL, root_path TEXT NOT NULL, enabled BOOLEAN NOT NULL, permission_profile VARCHAR(80) NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, last_used_at DATETIME, PRIMARY KEY (id));
        ALTER TABLE approvals ADD COLUMN task_id VARCHAR(36);
        ALTER TABLE approvals ADD COLUMN tool_name VARCHAR(160);
        ALTER TABLE approvals ADD COLUMN normalized_arguments JSON;
        ALTER TABLE approvals ADD COLUMN risk_level VARCHAR(40);
        ALTER TABLE approvals ADD COLUMN status VARCHAR(40);
        ALTER TABLE approvals ADD COLUMN created_at DATETIME;
        ALTER TABLE approvals ADD COLUMN decided_at DATETIME;
        ALTER TABLE undo_records ADD COLUMN task_id VARCHAR(36);
        ALTER TABLE undo_records ADD COLUMN operation VARCHAR(80);
        ALTER TABLE undo_records ADD COLUMN source TEXT;
        ALTER TABLE undo_records ADD COLUMN destination TEXT;
        ALTER TABLE undo_records ADD COLUMN precondition JSON;
        ALTER TABLE undo_records ADD COLUMN postcondition JSON;
        ALTER TABLE undo_records ADD COLUMN backup_path TEXT;
        ALTER TABLE undo_records ADD COLUMN status VARCHAR(40);
        ALTER TABLE undo_records ADD COLUMN applied_at DATETIME;
        """,
    )
    if with_created_at:
        execute_script(path, "ALTER TABLE undo_records ADD COLUMN created_at DATETIME;")


def row_count(path: Path, table: str) -> int:
    with sqlite3.connect(path) as connection:
        return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def columns(path: Path, table: str) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def revision(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return str(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0])


def test_empty_database_upgrades_to_head(tmp_path: Path) -> None:
    migrate_to_head(settings(tmp_path))
    diagnostics = collect_diagnostics(settings(tmp_path))
    assert diagnostics.current_revision == diagnostics.head_revision
    assert diagnostics.issues == []
    assert "created_at" in columns(db_path(tmp_path), "undo_records")


def test_phase1_legacy_database_upgrades_to_head_and_keeps_rows(tmp_path: Path) -> None:
    phase1_schema(db_path(tmp_path))
    before = {table: row_count(db_path(tmp_path), table) for table in ["tasks", "actions", "undo_records"]}
    migrate_to_head(settings(tmp_path))
    after = {table: row_count(db_path(tmp_path), table) for table in before}
    assert before == after
    assert revision(db_path(tmp_path)) == "0006_capabilities_recovery"
    assert collect_diagnostics(settings(tmp_path)).issues == []


def test_phase2_1_partial_database_adds_undo_created_at(tmp_path: Path) -> None:
    phase2_partial_schema(db_path(tmp_path), with_created_at=False)
    migrate_to_head(settings(tmp_path))
    assert "created_at" in columns(db_path(tmp_path), "undo_records")
    with sqlite3.connect(db_path(tmp_path)) as connection:
        assert connection.execute("SELECT created_at FROM undo_records WHERE id='undo-1'").fetchone()[0]


def test_phase2_legacy_without_alembic_version_is_baselined(tmp_path: Path) -> None:
    phase2_partial_schema(db_path(tmp_path), with_created_at=True)
    migrate_to_head(settings(tmp_path))
    assert revision(db_path(tmp_path)) == "0006_capabilities_recovery"
    assert collect_diagnostics(settings(tmp_path)).issues == []


def test_schema_revision_inconsistency_fails_closed(tmp_path: Path) -> None:
    phase2_partial_schema(db_path(tmp_path), with_created_at=False)
    execute_script(db_path(tmp_path), "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL); INSERT INTO alembic_version VALUES ('0003_reconcile_legacy');")
    with pytest.raises(Exception):
        migrate_to_head(settings(tmp_path), create_backup=False)


def test_repeated_migration_is_idempotent(tmp_path: Path) -> None:
    phase2_partial_schema(db_path(tmp_path), with_created_at=False)
    migrate_to_head(settings(tmp_path))
    first_columns = columns(db_path(tmp_path), "undo_records")
    migrate_to_head(settings(tmp_path))
    assert columns(db_path(tmp_path), "undo_records") == first_columns


def test_phase4_migration_adds_task_execution_tables(tmp_path: Path) -> None:
    phase2_partial_schema(db_path(tmp_path), with_created_at=True)
    migrate_to_head(settings(tmp_path))
    assert "workspace_id" in columns(db_path(tmp_path), "tasks")
    assert "idempotency_key" in columns(db_path(tmp_path), "tasks")
    assert "workspace_id" in columns(db_path(tmp_path), "actions")
    assert "task_id" in columns(db_path(tmp_path), "observations")
    assert "version" in columns(db_path(tmp_path), "plans")
    assert "retry_count" in columns(db_path(tmp_path), "plan_steps")
    assert columns(db_path(tmp_path), "task_events")
    assert columns(db_path(tmp_path), "execution_leases")
    assert columns(db_path(tmp_path), "idempotency_records")


def test_phase5_migration_adds_capability_manifest_and_recovery_tables(tmp_path: Path) -> None:
    phase2_partial_schema(db_path(tmp_path), with_created_at=True)
    migrate_to_head(settings(tmp_path))
    assert "capability" in columns(db_path(tmp_path), "capability_grants")
    assert "manifest_hash" in columns(db_path(tmp_path), "batch_manifests")
    assert "source_hash" in columns(db_path(tmp_path), "batch_manifest_items")
    assert "recovery_path" in columns(db_path(tmp_path), "recovery_items")


def test_migrated_orm_queries_and_task_list_succeed(tmp_path: Path) -> None:
    phase2_partial_schema(db_path(tmp_path), with_created_at=False)
    migrate_to_head(settings(tmp_path))
    engine = create_engine(f"sqlite:///{db_path(tmp_path)}", connect_args={"check_same_thread": False})
    with Session(engine) as session:
        assert session.scalar(select(Task).limit(1)) is not None
        assert session.scalar(select(Action).limit(1)) is not None
        assert session.scalar(select(UndoRecord).limit(1)) is not None
        workspace_root = tmp_path / "workspace"
        workspace_root.mkdir()
        workspace = StructuredTaskService().create_workspace(session, WorkspaceGrantCreate(root_path=str(workspace_root)))
        result = StructuredTaskService().create_task(session, StructuredTaskRequest(task_type="LIST_DIRECTORY", workspace_id=workspace.id, path="."))
        assert result.state == "COMPLETED"


def test_unrecognized_legacy_database_fails_without_deleting(tmp_path: Path) -> None:
    execute_script(db_path(tmp_path), "CREATE TABLE tasks (id TEXT PRIMARY KEY); INSERT INTO tasks VALUES ('task-1');")
    with pytest.raises(UnrecognizedLegacyDatabaseError):
        migrate_to_head(settings(tmp_path), create_backup=False)
    assert row_count(db_path(tmp_path), "tasks") == 1


def test_migration_lock_blocks_concurrent_upgrade(tmp_path: Path) -> None:
    active = settings(tmp_path)
    with MigrationLock(active, timeout_seconds=0.1):
        with pytest.raises(MigrationLockError):
            with MigrationLock(active, timeout_seconds=0.1):
                pass


def test_backup_failure_does_not_modify_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    phase2_partial_schema(db_path(tmp_path), with_created_at=False)
    original = shutil.copy2

    def fail_copy(source: Path, destination: Path) -> Path:
        raise OSError("copy failed")

    monkeypatch.setattr(shutil, "copy2", fail_copy)
    with pytest.raises(OSError):
        backup_database(settings(tmp_path))
    monkeypatch.setattr(shutil, "copy2", original)
    assert "created_at" not in columns(db_path(tmp_path), "undo_records")


def test_runtime_safe_error_payload_hides_sql_and_logs_correlation() -> None:
    from app.api.errors import database_exception_handler

    class Request:
        headers = {"X-Request-ID": "corr-test"}

    response = asyncio.run(database_exception_handler(Request(), OperationalError("SELECT * FROM secrets", {}, None)))  # type: ignore[arg-type]
    payload = response.body.decode("utf-8")
    assert response.status_code == 500
    assert "corr-test" in payload
    assert "SELECT" not in payload
    assert "sqlite" not in payload.lower()
    assert "sqlalchemy" not in payload.lower()
    parsed = response.body.decode("utf-8")
    assert "本機資料庫需要更新" in parsed
