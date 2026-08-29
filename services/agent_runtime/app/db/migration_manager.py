from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine

from app.config import RuntimeSettings, get_settings
from app.db.session import Base
from app.models import entities as _entities  # noqa: F401

LOGGER = logging.getLogger(__name__)

HEAD_REVISION = "head"
BASE_REVISION = "base"
PHASE1_REVISION = "0001_initial"
PHASE2_REVISION = "0002_workspace_tool"
LOCK_TIMEOUT_SECONDS = 30.0


class MigrationError(RuntimeError):
    pass


class UnrecognizedLegacyDatabaseError(MigrationError):
    pass


class MigrationLockError(MigrationError):
    pass


@dataclass(frozen=True)
class BackupResult:
    path: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class SchemaIssue:
    table: str
    kind: str
    detail: str


@dataclass(frozen=True)
class DatabaseDiagnostics:
    database_path: Path
    current_revision: str | None
    head_revision: str
    legacy_state: str
    issues: list[SchemaIssue]
    row_counts: dict[str, int]


def database_path(settings: RuntimeSettings | None = None) -> Path:
    active = settings or get_settings()
    return active.data_dir / "clm_assistant.sqlite3"


def alembic_config(settings: RuntimeSettings | None = None) -> Config:
    active = settings or get_settings()
    runtime_root = _runtime_root()
    ini_path = runtime_root / "alembic.ini"
    script_location = runtime_root / "alembic"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(script_location))
    cfg.set_main_option("sqlalchemy.url", active.database_url)
    return cfg


def _runtime_root() -> Path:
    frozen_root = getattr(__import__("sys"), "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parents[2]


def get_head_revision(settings: RuntimeSettings | None = None) -> str:
    return str(ScriptDirectory.from_config(alembic_config(settings)).get_current_head())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def backup_database(settings: RuntimeSettings | None = None) -> BackupResult | None:
    path = database_path(settings)
    if not path.exists() or path.stat().st_size == 0:
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    revision = "unversioned"
    with contextlib.suppress(Exception), sqlite3.connect(path) as connection:
        revision = _current_revision(connection) or identify_legacy_state(connection)
    safe_revision = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in revision)
    backup_path = path.with_name(f"{path.name}.{safe_revision}.{stamp}.bak")
    shutil.copy2(path, backup_path)
    if sha256_file(path) != sha256_file(backup_path) or path.stat().st_size != backup_path.stat().st_size:
        raise MigrationError("Database backup verification failed.")
    return BackupResult(path=backup_path, size=backup_path.stat().st_size, sha256=sha256_file(backup_path))


class MigrationLock:
    def __init__(self, settings: RuntimeSettings | None = None, timeout_seconds: float = LOCK_TIMEOUT_SECONDS) -> None:
        active = settings or get_settings()
        self.path = active.data_dir / "migration.lock"
        self.timeout_seconds = timeout_seconds
        self.fd: int | None = None

    def __enter__(self) -> MigrationLock:
        deadline = time.monotonic() + self.timeout_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                payload = {"pid": os.getpid(), "createdAt": datetime.now(UTC).isoformat()}
                os.write(self.fd, json.dumps(payload).encode("utf-8"))
                return self
            except FileExistsError as exc:
                if time.monotonic() >= deadline:
                    raise MigrationLockError("Another runtime is migrating this database.") from exc
                time.sleep(0.2)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()


def migrate_to_head(settings: RuntimeSettings | None = None, *, create_backup: bool = True) -> BackupResult | None:
    active = settings or get_settings()
    active.data_dir.mkdir(parents=True, exist_ok=True)
    with MigrationLock(active):
        backup = backup_database(active) if create_backup else None
        baseline_legacy_database(active)
        command.upgrade(alembic_config(active), HEAD_REVISION)
        diagnostics = collect_diagnostics(active)
        if diagnostics.current_revision != diagnostics.head_revision or diagnostics.issues:
            detail = "; ".join(f"{issue.table}:{issue.kind}:{issue.detail}" for issue in diagnostics.issues)
            raise MigrationError(f"Database schema validation failed: {detail}")
        return backup


def baseline_legacy_database(settings: RuntimeSettings | None = None) -> str:
    active = settings or get_settings()
    path = database_path(active)
    if not path.exists() or path.stat().st_size == 0:
        return "empty"
    with sqlite3.connect(path) as connection:
        tables = _tables(connection)
        if not tables:
            return "empty"
        revision = _current_revision(connection)
        if revision:
            return f"revision:{revision}"
        state = identify_legacy_state(connection)
    if state == "phase1":
        command.stamp(alembic_config(active), PHASE1_REVISION)
    elif state in {"phase2", "phase2_1_partial", "head_without_version"}:
        command.stamp(alembic_config(active), PHASE2_REVISION)
    else:
        raise UnrecognizedLegacyDatabaseError(f"Unrecognized legacy database schema: {state}")
    return state


def identify_legacy_state(connection: sqlite3.Connection) -> str:
    tables = _tables(connection)
    required_phase1 = {
        "tasks",
        "task_steps",
        "actions",
        "approvals",
        "observations",
        "artifacts",
        "undo_records",
        "audit_events",
        "scheduled_tasks",
    }
    if not required_phase1.issubset(tables):
        return "unknown"
    undo = _columns(connection, "undo_records")
    approvals = _columns(connection, "approvals")
    has_workspace = "workspace_grants" in tables
    phase1_undo = {"id", "action_id", "undo_type", "payload", "applied"}
    phase2_undo = phase1_undo | {
        "task_id",
        "operation",
        "source",
        "destination",
        "precondition",
        "postcondition",
        "backup_path",
        "status",
        "created_at",
        "applied_at",
    }
    phase2_approval = {
        "id",
        "task_id",
        "action_id",
        "tool_name",
        "normalized_arguments",
        "exact_tool",
        "exact_arguments",
        "argument_hash",
        "risk_level",
        "working_directory",
        "risk_reason",
        "status",
        "expires_at",
        "created_at",
        "decided_at",
        "approved",
    }
    if not has_workspace and undo == phase1_undo:
        return "phase1"
    if has_workspace and phase2_undo.issubset(undo) and phase2_approval.issubset(approvals):
        return "head_without_version"
    if has_workspace and (phase2_undo - {"created_at"}).issubset(undo):
        return "phase2_1_partial"
    if has_workspace:
        return "phase2"
    return "unknown"


def collect_diagnostics(settings: RuntimeSettings | None = None) -> DatabaseDiagnostics:
    active = settings or get_settings()
    path = database_path(active)
    head = get_head_revision(active)
    if not path.exists():
        return DatabaseDiagnostics(path, None, head, "missing", list(_model_issues({})), {})
    with sqlite3.connect(path) as connection:
        tables = _tables(connection)
        actual = {table: _column_details(connection, table) for table in tables}
        current_revision = _current_revision(connection)
        legacy_state = f"revision:{current_revision}" if current_revision else identify_legacy_state(connection)
        issues = list(_model_issues(actual))
        issues.extend(_foreign_key_issues(connection))
        row_counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in tables
            if table != "alembic_version"
        }
    return DatabaseDiagnostics(path, current_revision, head, legacy_state, issues, row_counts)


def _model_issues(actual: dict[str, dict[str, tuple[object, ...]]]) -> Iterator[SchemaIssue]:
    for table in sorted(Base.metadata.tables.values(), key=lambda item: item.name):
        actual_columns = actual.get(table.name)
        if actual_columns is None:
            yield SchemaIssue(table.name, "missing_table", "table is missing")
            continue
        for column in table.columns:
            info = actual_columns.get(column.name)
            if info is None:
                yield SchemaIssue(table.name, "missing_column", column.name)
                continue
            notnull = bool(info[3]) or bool(info[5])
            if not column.nullable and not notnull:
                yield SchemaIssue(table.name, "nullable_mismatch", column.name)


def _foreign_key_issues(connection: sqlite3.Connection) -> list[SchemaIssue]:
    issues: list[SchemaIssue] = []
    expected = {
        "actions": {"task_id": ("tasks", "id")},
        "approvals": {"task_id": ("tasks", "id"), "action_id": ("actions", "id")},
        "artifacts": {"task_id": ("tasks", "id")},
        "observations": {"action_id": ("actions", "id")},
        "task_steps": {"task_id": ("tasks", "id")},
        "undo_records": {"task_id": ("tasks", "id"), "action_id": ("actions", "id")},
    }
    for table, columns in expected.items():
        actual = {
            row[3]: (row[2], row[4])
            for row in connection.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
        }
        for column, target in columns.items():
            if actual.get(column) != target:
                issues.append(SchemaIssue(table, "missing_foreign_key", f"{column}->{target[0]}.{target[1]}"))
    return issues


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _column_details(connection: sqlite3.Connection, table: str) -> dict[str, tuple[object, ...]]:
    return {row[1]: row for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _current_revision(connection: sqlite3.Connection) -> str | None:
    if "alembic_version" not in _tables(connection):
        return None
    row = connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
    return str(row[0]) if row else None


def assert_database_ready(engine: Engine) -> None:
    diagnostics = collect_diagnostics()
    if diagnostics.current_revision != diagnostics.head_revision or diagnostics.issues:
        raise MigrationError("Database schema is not at Alembic head.")
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT id FROM tasks ORDER BY created_at DESC LIMIT 1").fetchall()
        connection.exec_driver_sql("SELECT id FROM undo_records ORDER BY created_at DESC LIMIT 1").fetchall()
