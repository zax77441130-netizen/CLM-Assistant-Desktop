from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.audit import redact
from app.core.file_tools import sha256_file
from app.core.path_policy import PathPolicyError, WorkspacePathPolicy
from app.models import Approval, AuditEvent, TaskState, WorkspaceGrant
from app.services.structured_task_service import StructuredTaskService
from app.schemas import StructuredTaskRequest, WorkspaceGrantCreate
from app.db.session import Base


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session


def grant(db: Session, tmp_path: Path) -> WorkspaceGrant:
    return StructuredTaskService().create_workspace(db, WorkspaceGrantCreate(root_path=str(tmp_path)))


def run(db: Session, payload: StructuredTaskRequest):
    return StructuredTaskService().create_task(db, payload)


def test_workspace_grant(db: Session, tmp_path: Path) -> None:
    workspace = grant(db, tmp_path)
    assert workspace.enabled is True
    assert workspace.root_path == str(tmp_path.resolve())


@pytest.mark.parametrize("bad_path", ["..\\outside.txt", "C:\\Windows\\win.ini", "\\\\server\\share", "\\\\?\\C:\\x", "file.txt:ads", "CON.txt"])
def test_path_policy_rejects_unsafe_paths(tmp_path: Path, bad_path: str) -> None:
    with pytest.raises(PathPolicyError):
        WorkspacePathPolicy(str(tmp_path)).resolve_new_child(bad_path)


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation blocked by environment: {exc}")
    with pytest.raises(PathPolicyError):
        WorkspacePathPolicy(str(tmp_path)).resolve_existing("link\\secret.txt")


def test_list_stat_read_search_hash_duplicates(db: Session, tmp_path: Path) -> None:
    workspace = grant(db, tmp_path)
    (tmp_path / "a.txt").write_text("hello duplicate", encoding="utf-8")
    (tmp_path / "b.txt").write_text("hello duplicate", encoding="utf-8")
    (tmp_path / "bin.dat").write_bytes(b"\x00\x01")

    listed = run(db, StructuredTaskRequest(task_type="LIST_DIRECTORY", workspace_id=workspace.id, path="."))
    assert listed.state == TaskState.COMPLETED
    assert {item["path"] for item in listed.observation["entries"]} >= {"a.txt", "b.txt", "bin.dat"}

    stat = run(db, StructuredTaskRequest(task_type="STAT_PATH", workspace_id=workspace.id, path="a.txt"))
    assert stat.observation["type"] == "file"

    text = run(db, StructuredTaskRequest(task_type="READ_TEXT", workspace_id=workspace.id, path="a.txt"))
    assert text.observation["content"] == "hello duplicate"

    binary = run(db, StructuredTaskRequest(task_type="READ_TEXT", workspace_id=workspace.id, path="bin.dat"))
    assert binary.state == TaskState.BLOCKED

    found = run(db, StructuredTaskRequest(task_type="SEARCH_FILES", workspace_id=workspace.id, path=".", content="duplicate", search_content=True))
    assert len(found.observation["results"]) == 2

    hashed = run(db, StructuredTaskRequest(task_type="HASH_FILE", workspace_id=workspace.id, path="a.txt"))
    assert hashed.observation["sha256"] == sha256_file(tmp_path / "a.txt")

    dupes = run(db, StructuredTaskRequest(task_type="FIND_DUPLICATES", workspace_id=workspace.id, path="."))
    assert dupes.observation["duplicates"][0]["paths"] == ["a.txt", "b.txt"]


def test_write_copy_move_rename_and_undo(db: Session, tmp_path: Path) -> None:
    workspace = grant(db, tmp_path)
    made = run(db, StructuredTaskRequest(task_type="CREATE_DIRECTORY", workspace_id=workspace.id, path="work"))
    assert made.state == TaskState.COMPLETED
    assert (tmp_path / "work").is_dir()

    written = run(db, StructuredTaskRequest(task_type="WRITE_NEW_TEXT", workspace_id=workspace.id, path="work\\a.txt", content="hello"))
    assert written.state == TaskState.COMPLETED
    blocked = run(db, StructuredTaskRequest(task_type="WRITE_NEW_TEXT", workspace_id=workspace.id, path="work\\a.txt", content="again"))
    assert blocked.state == TaskState.BLOCKED

    copied = run(db, StructuredTaskRequest(task_type="COPY_FILE", workspace_id=workspace.id, path="work\\a.txt", destination="work\\b.txt"))
    assert copied.state == TaskState.COMPLETED
    moved = run(db, StructuredTaskRequest(task_type="MOVE_FILE", workspace_id=workspace.id, path="work\\b.txt", destination="work\\c.txt"))
    assert moved.state == TaskState.COMPLETED
    renamed = run(db, StructuredTaskRequest(task_type="RENAME_FILE", workspace_id=workspace.id, path="work\\c.txt", destination="work\\d.txt"))
    assert renamed.state == TaskState.COMPLETED

    undo = StructuredTaskService().undo(db, renamed.undo_record_id or "")
    assert undo.state == TaskState.COMPLETED
    assert (tmp_path / "work" / "c.txt").exists()

    duplicate = StructuredTaskService().undo(db, renamed.undo_record_id or "")
    assert duplicate.state == TaskState.BLOCKED


def test_overwrite_requires_exact_approval_and_undo(db: Session, tmp_path: Path) -> None:
    workspace = grant(db, tmp_path)
    target = tmp_path / "target.txt"
    target.write_text("before", encoding="utf-8")
    pending = run(db, StructuredTaskRequest(task_type="OVERWRITE_TEXT", workspace_id=workspace.id, path="target.txt", content="after"))
    assert pending.state == TaskState.WAITING_APPROVAL
    assert target.read_text(encoding="utf-8") == "before"

    rejected = StructuredTaskService().decide_approval(db, pending.approval_id or "", False)
    assert rejected.state == TaskState.BLOCKED
    assert target.read_text(encoding="utf-8") == "before"

    pending2 = run(db, StructuredTaskRequest(task_type="OVERWRITE_TEXT", workspace_id=workspace.id, path="target.txt", content="after"))
    approved = StructuredTaskService().decide_approval(db, pending2.approval_id or "", True)
    assert approved.state == TaskState.COMPLETED
    assert target.read_text(encoding="utf-8") == "after"
    undo = StructuredTaskService().undo(db, approved.undo_record_id or "")
    assert undo.state == TaskState.COMPLETED
    assert target.read_text(encoding="utf-8") == "before"


def test_approval_expiry_tampering_and_file_changed(db: Session, tmp_path: Path) -> None:
    workspace = grant(db, tmp_path)
    target = tmp_path / "target.txt"
    target.write_text("before", encoding="utf-8")
    pending = run(db, StructuredTaskRequest(task_type="OVERWRITE_TEXT", workspace_id=workspace.id, path="target.txt", content="after"))
    approval = db.get(Approval, pending.approval_id)
    assert approval is not None
    approval.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    expired = StructuredTaskService().decide_approval(db, approval.id, True)
    assert expired.state == TaskState.BLOCKED

    pending2 = run(db, StructuredTaskRequest(task_type="OVERWRITE_TEXT", workspace_id=workspace.id, path="target.txt", content="after"))
    approval2 = db.get(Approval, pending2.approval_id)
    assert approval2 is not None
    approval2.argument_hash = "tampered"
    tampered = StructuredTaskService().decide_approval(db, approval2.id, True)
    assert tampered.state == TaskState.BLOCKED

    pending3 = run(db, StructuredTaskRequest(task_type="OVERWRITE_TEXT", workspace_id=workspace.id, path="target.txt", content="after"))
    target.write_text("external", encoding="utf-8")
    changed = StructuredTaskService().decide_approval(db, pending3.approval_id or "", True)
    assert changed.state == TaskState.BLOCKED


def test_audit_redaction_and_persistence(db: Session, tmp_path: Path) -> None:
    assert redact({"token": "abc", "root_path": str(tmp_path)}) == {"token": "***REDACTED***", "root_path": "***LOCAL_PATH***"}
    workspace = grant(db, tmp_path)
    run(db, StructuredTaskRequest(task_type="SYSTEM_INFO"))
    assert db.scalar(select(WorkspaceGrant).where(WorkspaceGrant.id == workspace.id)) is not None
    assert db.scalar(select(AuditEvent)) is not None


def test_host_tools_and_arbitrary_executable_rejection(db: Session) -> None:
    apps = run(db, StructuredTaskRequest(task_type="LIST_REGISTERED_APPS"))
    assert apps.state == TaskState.COMPLETED
    launched = run(db, StructuredTaskRequest(task_type="LAUNCH_REGISTERED_APP", app_id="notepad"))
    assert launched.state == TaskState.COMPLETED
    rejected = run(db, StructuredTaskRequest(task_type="LAUNCH_REGISTERED_APP", app_id="cmd.exe"))
    assert rejected.state == TaskState.BLOCKED
