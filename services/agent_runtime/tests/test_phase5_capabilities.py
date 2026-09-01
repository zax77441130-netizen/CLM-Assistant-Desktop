from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agent.capability_policy import CapabilityDecision, CapabilityPolicy
from app.agent.contracts import AgentPlan, PlanContext, PlanStepSpec
from app.agent.orchestrator import PlanValidator
from app.agent.planner import DeterministicPlannerProvider
from app.core import host_tools
from app.db.session import Base
from app.models import BatchManifest, BatchManifestItem, RecoveryItem, TaskState, UndoRecord
from app.schemas import StructuredTaskRequest, WorkspaceGrantCreate
from app.services.structured_task_service import StructuredTaskService


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def workspace(db: Session, tmp_path: Path) -> str:
    (tmp_path / "small.txt").write_text("small", encoding="utf-8")
    (tmp_path / "large.bin").write_bytes(b"x" * 1024)
    (tmp_path / "same-a.txt").write_text("same", encoding="utf-8")
    (tmp_path / "same-b.txt").write_text("same", encoding="utf-8")
    (tmp_path / "photo.jpg").write_bytes(b"jpg")
    (tmp_path / "script.ps1").write_text("Write-Host nope", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "deep.txt").write_text("deep", encoding="utf-8")
    return StructuredTaskService().create_workspace(db, WorkspaceGrantCreate(root_path=str(tmp_path))).id


def run(db: Session, payload: StructuredTaskRequest):
    return StructuredTaskService().create_task(db, payload)


def test_recursive_walk_large_files_and_directory_summary(db: Session, workspace: str) -> None:
    walked = run(db, StructuredTaskRequest(task_type="WALK", workspace_id=workspace, path=".", max_depth=1, limit=20))
    assert walked.state == TaskState.COMPLETED
    assert "nested/deep.txt" not in {item["path"] for item in walked.observation["entries"]}

    large = run(db, StructuredTaskRequest(task_type="FIND_LARGE_FILES", workspace_id=workspace, path=".", min_size_bytes=1000))
    assert large.state == TaskState.COMPLETED
    assert large.observation["files"][0]["path"] == "large.bin"

    summary = run(db, StructuredTaskRequest(task_type="DIRECTORY_SUMMARY", workspace_id=workspace, path="."))
    assert summary.state == TaskState.COMPLETED
    assert summary.observation["file_count"] >= 6
    assert summary.observation["extensions"][".txt"] >= 4


def test_list_by_extension_compare_and_preview_batch(db: Session, workspace: str) -> None:
    by_ext = run(db, StructuredTaskRequest(task_type="LIST_BY_EXTENSION", workspace_id=workspace, extension="jpg"))
    assert by_ext.state == TaskState.COMPLETED
    assert by_ext.observation["files"][0]["path"] == "photo.jpg"

    same = run(db, StructuredTaskRequest(task_type="COMPARE_FILES", workspace_id=workspace, path="same-a.txt", other_path="same-b.txt"))
    assert same.observation["same"] is True

    preview = run(db, StructuredTaskRequest(task_type="PREVIEW_BATCH", workspace_id=workspace, items=[{"source": "small.txt", "destination": "copy/small.txt"}]))
    assert preview.state == TaskState.COMPLETED
    assert preview.observation["items"][0]["sourceHash"]


def test_append_text_and_undo_postcondition(db: Session, workspace: str, tmp_path: Path) -> None:
    appended = run(db, StructuredTaskRequest(task_type="APPEND_TEXT", workspace_id=workspace, path="small.txt", text=" plus"))
    assert appended.state == TaskState.COMPLETED
    assert (tmp_path / "small.txt").read_text(encoding="utf-8") == "small plus"
    undone = StructuredTaskService().undo(db, appended.undo_record_id or "")
    assert undone.state == TaskState.COMPLETED
    assert (tmp_path / "small.txt").read_text(encoding="utf-8") == "small"


def test_batch_copy_move_rename_manifest_partial_failure_and_undo(db: Session, workspace: str, tmp_path: Path) -> None:
    copied = run(
        db,
        StructuredTaskRequest(
            task_type="BATCH_COPY",
            workspace_id=workspace,
            items=[
                {"source": "small.txt", "destination": "copies/small.txt"},
                {"source": "missing.txt", "destination": "copies/missing.txt"},
            ],
        ),
    )
    assert copied.state == TaskState.COMPLETED
    assert (tmp_path / "copies" / "small.txt").exists()
    assert copied.observation["postcondition"]["success_count"] == 1
    assert copied.observation["postcondition"]["failure_count"] == 1
    manifest = db.query(BatchManifest).filter(BatchManifest.task_id == copied.id).one()
    assert manifest.manifest_hash
    assert db.query(BatchManifestItem).filter(BatchManifestItem.manifest_id == manifest.id).count() == 2
    statuses = {item.source: item.status for item in db.query(BatchManifestItem).filter(BatchManifestItem.manifest_id == manifest.id)}
    assert statuses == {"small.txt": "COMPLETED", "missing.txt": "FAILED"}
    undo_records = db.query(UndoRecord).filter(UndoRecord.task_id == copied.id).all()
    assert len(undo_records) == 1
    assert StructuredTaskService().undo(db, undo_records[0].id).state == TaskState.COMPLETED
    assert not (tmp_path / "copies" / "small.txt").exists()

    moved = run(db, StructuredTaskRequest(task_type="BATCH_MOVE", workspace_id=workspace, items=[{"source": "same-a.txt", "destination": "moved/same-a.txt"}]))
    assert moved.state == TaskState.COMPLETED
    assert not (tmp_path / "same-a.txt").exists()
    assert (tmp_path / "moved" / "same-a.txt").exists()

    renamed = run(db, StructuredTaskRequest(task_type="BATCH_RENAME", workspace_id=workspace, items=[{"source": "same-b.txt", "destination": "renamed.txt"}]))
    assert renamed.state == TaskState.COMPLETED
    assert (tmp_path / "renamed.txt").exists()


def test_create_zip_extract_zip_and_zip_slip_rejection(db: Session, workspace: str, tmp_path: Path) -> None:
    zipped = run(db, StructuredTaskRequest(task_type="CREATE_ZIP", workspace_id=workspace, path="reports.zip", items=[{"source": "small.txt"}, {"source": "nested"}]))
    assert zipped.state == TaskState.COMPLETED
    assert (tmp_path / "reports.zip").is_file()
    assert zipped.observation["postcondition"]["verified"] is True

    pending_extract = run(db, StructuredTaskRequest(task_type="EXTRACT_ZIP", workspace_id=workspace, path="reports.zip", destination="reports"))
    assert pending_extract.state == TaskState.WAITING_APPROVAL
    approved = StructuredTaskService().decide_approval(db, pending_extract.approval_id or "", True)
    assert approved.state == TaskState.COMPLETED
    assert (tmp_path / "reports" / "small.txt").exists()

    malicious = tmp_path / "bad.zip"
    with zipfile.ZipFile(malicious, "w") as handle:
        handle.writestr("../escape.txt", "bad")
    bad = run(db, StructuredTaskRequest(task_type="EXTRACT_ZIP", workspace_id=workspace, path="bad.zip", destination="bad"))
    blocked = StructuredTaskService().decide_approval(db, bad.approval_id or "", True)
    assert blocked.state == TaskState.BLOCKED
    assert not (tmp_path.parent / "escape.txt").exists()


def test_large_batch_requires_approval_and_file_change_invalidates_manifest(db: Session, workspace: str, tmp_path: Path) -> None:
    items = []
    for index in range(11):
        source = tmp_path / f"batch-{index}.txt"
        source.write_text(f"before {index}", encoding="utf-8")
        items.append({"source": source.name, "destination": f"copies/{source.name}"})
    pending = run(db, StructuredTaskRequest(task_type="BATCH_COPY", workspace_id=workspace, items=items))
    assert pending.state == TaskState.WAITING_APPROVAL
    (tmp_path / "batch-0.txt").write_text("changed", encoding="utf-8")
    invalidated = StructuredTaskService().decide_approval(db, pending.approval_id or "", True)
    assert invalidated.state == TaskState.BLOCKED
    assert invalidated.summary == "FILE_CHANGED_WHILE_WAITING"
    assert not (tmp_path / "copies" / "batch-1.txt").exists()


def test_recovery_bin_move_restore_conflict_and_quota_metadata(db: Session, workspace: str, tmp_path: Path) -> None:
    pending = run(db, StructuredTaskRequest(task_type="MOVE_TO_RECOVERY_BIN", workspace_id=workspace, path="small.txt", recovery_item_id="recover-small"))
    assert pending.state == TaskState.WAITING_APPROVAL
    moved = StructuredTaskService().decide_approval(db, pending.approval_id or "", True)
    assert moved.state == TaskState.COMPLETED
    assert not (tmp_path / "small.txt").exists()
    item = db.get(RecoveryItem, "recover-small")
    assert item is not None
    assert item.status == "STORED"
    assert Path(item.recovery_path).is_file()

    (tmp_path / "small.txt").write_text("conflict", encoding="utf-8")
    conflict = run(db, StructuredTaskRequest(task_type="RESTORE_FROM_RECOVERY_BIN", workspace_id=workspace, path="small.txt", recovery_item_id="recover-small"))
    assert conflict.state == TaskState.BLOCKED
    (tmp_path / "small.txt").unlink()
    restored = run(db, StructuredTaskRequest(task_type="RESTORE_FROM_RECOVERY_BIN", workspace_id=workspace, path="small.txt", recovery_item_id="recover-small"))
    assert restored.state == TaskState.COMPLETED
    assert (tmp_path / "small.txt").exists()


def test_open_workspace_file_rejects_executables_and_uses_test_adapter(db: Session, workspace: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLM_HOST_TEST_MODE", "1")
    opened = run(db, StructuredTaskRequest(task_type="OPEN_WORKSPACE_FILE", workspace_id=workspace, path="small.txt"))
    assert opened.state == TaskState.COMPLETED
    assert opened.observation["adapter"] == "test"
    blocked = run(db, StructuredTaskRequest(task_type="OPEN_WORKSPACE_FILE", workspace_id=workspace, path="script.ps1"))
    assert blocked.state == TaskState.BLOCKED
    folder = run(db, StructuredTaskRequest(task_type="OPEN_WORKSPACE_FOLDER", workspace_id=workspace, path="nested"))
    assert folder.state == TaskState.COMPLETED


def test_clipboard_does_not_persist_secret_text(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLM_HOST_TEST_MODE", "1")
    written = run(db, StructuredTaskRequest(task_type="CLIPBOARD_WRITE_TEXT", text="hello secret"))
    assert written.state == TaskState.COMPLETED
    assert written.observation == {"characters": 12}
    monkeypatch.setenv("CLM_TEST_CLIPBOARD_TEXT", "OPENAI_TOKEN=secret-value")
    pending = run(db, StructuredTaskRequest(task_type="CLIPBOARD_READ_TEXT"))
    assert pending.state == TaskState.WAITING_APPROVAL
    read = StructuredTaskService().decide_approval(db, pending.approval_id or "", True)
    assert read.state == TaskState.COMPLETED
    assert "secret-value" not in read.observation["text"]
    assert read.observation["masked"] is True


def test_terminate_process_requires_approval_and_rejects_protected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLM_HOST_TEST_MODE", "1")
    with pytest.raises(ValueError, match="PROTECTED_PROCESS_REJECTED"):
        host_tools.terminate_process(4, expected_name="System")


def test_capability_policy_and_planner_cannot_bypass_policy() -> None:
    policy = CapabilityPolicy()
    assert policy.decision_for("workspace.read").decision == CapabilityDecision.AUTO
    assert policy.decision_for("process.terminate").decision == CapabilityDecision.APPROVAL_REQUIRED
    assert policy.decision_for("file.delete_permanent").decision == CapabilityDecision.BLOCKED
    with pytest.raises(ValueError, match="UNKNOWN_TOOL"):
        PlanStepSpec(tool="filesystem.delete_permanent", arguments={"path": "x"}, reason="bad")
    with pytest.raises(ValueError, match="UNSAFE_PATH_ARGUMENT"):
        PlanValidator().validate(
            AgentPlan(goal="bad", needsClarification=False, steps=[PlanStepSpec(tool="filesystem.create_zip", arguments={"path": "..\\bad.zip", "items": []}, reason="bad")]),
            workspace_id="workspace",
        )


def test_deterministic_planner_phase5_commands() -> None:
    planner = DeterministicPlannerProvider()
    large = planner.create_plan(PlanContext(request="找出工作區內超過 100 MB 的檔案", workspace_id="workspace"))
    assert large.steps[0].tool == "filesystem.find_large_files"
    assert large.steps[0].arguments["min_size_bytes"] == 100 * 1024 * 1024
    archive = planner.create_plan(PlanContext(request="把 small.txt 壓縮成 reports.zip", workspace_id="workspace"))
    assert archive.steps[0].tool == "filesystem.create_zip"
    clipboard = planner.create_plan(PlanContext(request="把這段文字複製到剪貼簿：hello", workspace_id="workspace"))
    assert clipboard.steps[0].tool == "host.clipboard_write_text"


def test_no_permanent_delete_tool_registered() -> None:
    from app.agent.contracts import ALLOWED_TOOLS, TOOL_TO_TASK_TYPE

    joined = " ".join(sorted(ALLOWED_TOOLS | set(TOOL_TO_TASK_TYPE)))
    assert "delete_permanent" not in joined
    assert "REMOVE_FILE" not in joined
