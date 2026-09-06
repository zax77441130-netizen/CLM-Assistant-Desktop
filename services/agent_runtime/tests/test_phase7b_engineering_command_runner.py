from __future__ import annotations

import io
import subprocess
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.session import Base
from app.engineering.command_runner import (
    EngineeringCommandError,
    EngineeringCommandRunner,
    MAX_OUTPUT_BYTES,
)
from app.models import Approval, TaskState, WorkspaceGrant
from app.schemas import StructuredTaskRequest
from app.services.structured_task_service import StructuredTaskService


class FakeProcess:
    def __init__(
        self,
        output: bytes = b"ok",
        *,
        returncode: int = 0,
        timeout: bool = False,
    ) -> None:
        self.stdout = io.BytesIO(output)
        self.returncode = returncode
        self.timeout = timeout
        self.killed = False
        self.wait_calls = 0

    def wait(self, timeout: int) -> int:
        self.wait_calls += 1
        if self.timeout and not self.killed:
            raise subprocess.TimeoutExpired(cmd="powershell.exe", timeout=timeout)
        return self.returncode

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session


def make_workspace(root: Path) -> WorkspaceGrant:
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / "test_windows.ps1").write_text("Write-Output 'tests ok'\n", encoding="utf-8")
    (scripts / "build_desktop.ps1").write_text("Write-Output 'build ok'\n", encoding="utf-8")
    return WorkspaceGrant(
        id="workspace-1",
        display_name="Engineering",
        root_path=str(root),
        enabled=True,
        permission_profile="standard",
    )


def test_prepare_allows_only_fixed_repository_scripts(tmp_path: Path) -> None:
    make_workspace(tmp_path)
    runner = EngineeringCommandRunner()

    prepared = runner.prepare(str(tmp_path), "test")

    assert prepared.displayCommand == r".\scripts\test_windows.ps1"
    assert prepared.scriptRelativePath == "scripts/test_windows.ps1"
    assert len(prepared.scriptSha256) == 64
    assert len(prepared.fingerprint) == 64
    with pytest.raises(EngineeringCommandError, match="ENGINEERING_COMMAND_NOT_ALLOWED"):
        runner.prepare(str(tmp_path), "npm install")


def test_run_uses_argument_array_no_shell_and_redacts_output(tmp_path: Path) -> None:
    make_workspace(tmp_path)
    calls: list[tuple[list[str], dict[str, Any]]] = []
    output = f"workspace={tmp_path}\nAPI_KEY=abc123\n".encode()

    def factory(argv: list[str], **kwargs: Any) -> FakeProcess:
        calls.append((argv, kwargs))
        return FakeProcess(output)

    runner = EngineeringCommandRunner(process_factory=factory)
    prepared = runner.prepare(str(tmp_path), "test")
    result = runner.run(
        str(tmp_path),
        "test",
        prepared.fingerprint,
        timeout_seconds=10,
    )

    assert result.success is True
    assert result.observation["exitCode"] == 0
    assert "<WORKSPACE>" in result.observation["output"]
    assert str(tmp_path) not in result.observation["output"]
    assert "abc123" not in result.observation["output"]
    assert calls[0][0][0] == "powershell.exe"
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["cwd"] == str(tmp_path.resolve())
    assert calls[0][1]["stdin"] is subprocess.DEVNULL


def test_run_caps_output_and_marks_truncation(tmp_path: Path) -> None:
    make_workspace(tmp_path)
    runner = EngineeringCommandRunner(
        process_factory=lambda argv, **kwargs: FakeProcess(b"x" * (MAX_OUTPUT_BYTES + 50))
    )
    prepared = runner.prepare(str(tmp_path), "build")

    result = runner.run(str(tmp_path), "build", prepared.fingerprint)

    assert result.success is True
    assert result.observation["outputTruncated"] is True
    assert len(result.observation["output"].encode()) == MAX_OUTPUT_BYTES


def test_run_kills_process_after_timeout(tmp_path: Path) -> None:
    make_workspace(tmp_path)
    process = FakeProcess(timeout=True)
    runner = EngineeringCommandRunner(
        process_factory=lambda argv, **kwargs: process
    )
    prepared = runner.prepare(str(tmp_path), "test")

    result = runner.run(
        str(tmp_path),
        "test",
        prepared.fingerprint,
        timeout_seconds=1,
    )

    assert result.success is False
    assert result.error_code == "ENGINEERING_COMMAND_TIMEOUT"
    assert process.killed is True


def test_script_change_invalidates_exact_approval(
    tmp_path: Path,
    db: Session,
) -> None:
    workspace = make_workspace(tmp_path)
    db.add(workspace)
    db.commit()
    service = StructuredTaskService()

    requested = service.create_task(
        db,
        StructuredTaskRequest(
            task_type="ENGINEERING_RUN",
            workspace_id=workspace.id,
            command_id="test",
            timeout_seconds=10,
        ),
    )

    assert requested.state == TaskState.WAITING_APPROVAL
    assert requested.approval_id is not None
    approval = db.get(Approval, requested.approval_id)
    assert approval is not None
    assert approval.exact_arguments["command_id"] == "test"
    assert approval.exact_arguments["command_display"] == r".\scripts\test_windows.ps1"
    assert approval.exact_arguments["command_fingerprint"]

    (tmp_path / "scripts" / "test_windows.ps1").write_text(
        "Write-Output 'changed after approval'\n",
        encoding="utf-8",
    )
    decided = service.decide_approval(db, approval.id, True)

    assert decided.state == TaskState.BLOCKED
    db.refresh(approval)
    assert approval.status == "INVALIDATED"


def test_request_rejects_unknown_engineering_command(
    tmp_path: Path,
    db: Session,
) -> None:
    workspace = make_workspace(tmp_path)
    db.add(workspace)
    db.commit()

    result = StructuredTaskService().create_task(
        db,
        StructuredTaskRequest.model_construct(
            task_type="ENGINEERING_RUN",
            workspace_id=workspace.id,
            command_id="arbitrary",
            timeout_seconds=10,
        ),
    )

    assert result.state == TaskState.BLOCKED
