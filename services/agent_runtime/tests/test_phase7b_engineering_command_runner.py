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


def test_prepare_prefers_fixed_repository_scripts(tmp_path: Path) -> None:
    make_workspace(tmp_path)
    runner = EngineeringCommandRunner()

    prepared = runner.prepare(str(tmp_path), "test")

    assert prepared.displayCommand == r".\scripts\test_windows.ps1"
    assert prepared.runnerKind == "powershell"
    assert prepared.sourceRelativePath == "scripts/test_windows.ps1"
    assert len(prepared.scriptSha256) == 64
    assert len(prepared.fingerprint) == 64
    with pytest.raises(EngineeringCommandError, match="ENGINEERING_COMMAND_NOT_ALLOWED"):
        runner.prepare(str(tmp_path), "npm install")


def test_prepare_detects_fixed_node_manifest_actions(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest","build":"vite build"}}',
        encoding="utf-8",
    )

    runner = EngineeringCommandRunner()
    test_command = runner.prepare(str(tmp_path), "test")
    build_command = runner.prepare(str(tmp_path), "build")

    assert test_command.runnerKind == "npm"
    assert test_command.displayCommand == "npm test"
    assert build_command.displayCommand == "npm run build"
    assert test_command.sourceRelativePath == "package.json"


def test_prepare_detects_python_pytest_and_fails_closed_without_markers(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    runner = EngineeringCommandRunner()

    prepared = runner.prepare(str(tmp_path), "test")

    assert prepared.runnerKind == "python"
    assert prepared.displayCommand == "python -m pytest"
    with pytest.raises(EngineeringCommandError, match="ENGINEERING_COMMAND_UNAVAILABLE"):
        runner.prepare(str(tmp_path), "build")


def test_prepare_detects_nested_python_marker_within_bounded_scan(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "backend" / "service"
    nested.mkdir(parents=True)
    (nested / "requirements.txt").write_text("pytest==8.3.2\n", encoding="utf-8")

    prepared = EngineeringCommandRunner().prepare(str(tmp_path), "test")

    assert prepared.runnerKind == "python"
    assert prepared.sourceRelativePath == "backend/service/requirements.txt"


def test_prepare_ignores_python_marker_beyond_bounded_scan(tmp_path: Path) -> None:
    nested = tmp_path.joinpath("one", "two", "three", "four", "five")
    nested.mkdir(parents=True)
    (nested / "requirements.txt").write_text("pytest==8.3.2\n", encoding="utf-8")

    with pytest.raises(EngineeringCommandError, match="ENGINEERING_COMMAND_UNAVAILABLE"):
        EngineeringCommandRunner().prepare(str(tmp_path), "test")


def test_run_uses_argument_array_no_shell_and_redacts_output(tmp_path: Path) -> None:
    make_workspace(tmp_path)
    calls: list[tuple[list[str], dict[str, Any]]] = []
    output = f"workspace={tmp_path}\nAPI_KEY=abc123\nAuthorization: Bearer hidden-token\n".encode()

    def factory(argv: list[str], **kwargs: Any) -> FakeProcess:
        calls.append((argv, kwargs))
        return FakeProcess(output)

    runner = EngineeringCommandRunner(process_factory=factory, powershell_executable="powershell.exe")
    prepared = runner.prepare(str(tmp_path), "test")
    result = runner.run(
        str(tmp_path),
        "test",
        prepared.fingerprint,
        timeout_seconds=10,
    )

    assert result.success is True
    assert result.observation["exitCode"] == 0
    assert isinstance(result.observation["durationSeconds"], float)
    assert "<WORKSPACE>" in result.observation["output"]
    assert str(tmp_path) not in result.observation["output"]
    assert "abc123" not in result.observation["output"]
    assert "hidden-token" not in result.observation["output"]
    assert calls[0][0][0] == "powershell.exe"
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["cwd"] == str(tmp_path.resolve())
    assert calls[0][1]["stdin"] is subprocess.DEVNULL


def test_node_manifest_run_uses_fixed_argv_without_shell(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest"}}', encoding="utf-8"
    )
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def factory(argv: list[str], **kwargs: Any) -> FakeProcess:
        calls.append((argv, kwargs))
        return FakeProcess(b"passed")

    runner = EngineeringCommandRunner(process_factory=factory)
    runner._resolve_executable = lambda name: "C:\\Tools\\" + name  # type: ignore[method-assign]
    prepared = runner.prepare(str(tmp_path), "test")

    result = runner.run(str(tmp_path), "test", prepared.fingerprint)

    assert result.success is True
    assert calls[0][0] == [r"C:\Tools\npm.cmd", "test"]
    assert calls[0][1]["shell"] is False


def test_manifest_change_invalidates_exact_approval(tmp_path: Path) -> None:
    package_json = tmp_path / "package.json"
    package_json.write_text('{"scripts":{"test":"vitest"}}', encoding="utf-8")
    runner = EngineeringCommandRunner()
    prepared = runner.prepare(str(tmp_path), "test")

    package_json.write_text('{"scripts":{"test":"vitest run"}}', encoding="utf-8")

    with pytest.raises(EngineeringCommandError, match="ENGINEERING_APPROVAL_INVALIDATED"):
        runner.run(str(tmp_path), "test", prepared.fingerprint)


def test_run_caps_output_and_marks_truncation(tmp_path: Path) -> None:
    make_workspace(tmp_path)
    runner = EngineeringCommandRunner(
        process_factory=lambda argv, **kwargs: FakeProcess(b"x" * (MAX_OUTPUT_BYTES + 50)),
        powershell_executable="powershell.exe",
    )
    prepared = runner.prepare(str(tmp_path), "build")

    result = runner.run(str(tmp_path), "build", prepared.fingerprint)

    assert result.success is True
    assert result.observation["outputTruncated"] is True
    assert len(result.observation["output"].encode()) == MAX_OUTPUT_BYTES


def test_output_removes_ansi_and_decodes_windows_traditional_chinese(
    tmp_path: Path,
) -> None:
    make_workspace(tmp_path)
    output = "\x1b[32m通過測試\x1b[0m\n存取被拒。\n".encode("cp950")
    runner = EngineeringCommandRunner(
        process_factory=lambda argv, **kwargs: FakeProcess(output),
        powershell_executable="powershell.exe",
    )
    prepared = runner.prepare(str(tmp_path), "test")

    result = runner.run(str(tmp_path), "test", prepared.fingerprint)

    assert result.observation["output"] == "通過測試\n存取被拒。\n"
    assert "\x1b[" not in result.observation["output"]


def test_run_kills_process_after_timeout(tmp_path: Path) -> None:
    make_workspace(tmp_path)
    process = FakeProcess(timeout=True)
    runner = EngineeringCommandRunner(
        process_factory=lambda argv, **kwargs: process,
        powershell_executable="powershell.exe",
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
    assert approval.exact_arguments["command_script_sha256"]
    assert r".\scripts\test_windows.ps1" in approval.risk_reason

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
