from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.core.path_policy import PathPolicyError, WorkspacePathPolicy
from app.core.tool_sdk import ToolEvidence, ToolResult, now_utc


MAX_OUTPUT_BYTES = 128 * 1024
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 120
SECRET_ASSIGNMENT = re.compile(
    r"(?im)\b(token|api[_-]?key|secret|password|authorization|cookie)\b(\s*[:=]\s*)[^\r\n]*"
)
ANSI_ESCAPE = re.compile(
    r"(?:\x1B\[[0-?]*[ -/]*[@-~]|\x1B\][^\x07]*(?:\x07|\x1B\\))"
)


class EngineeringCommandError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PreparedEngineeringCommand(BaseModel):
    commandId: str
    displayCommand: str
    runnerKind: str
    sourceRelativePath: str
    scriptSha256: str
    fingerprint: str


class EngineeringCommandRunner:
    """Resolve a fixed test/build action from trusted project markers and run it."""

    COMMANDS = {
        "test": ("scripts/test_windows.ps1", r".\scripts\test_windows.ps1"),
        "build": ("scripts/build_desktop.ps1", r".\scripts\build_desktop.ps1"),
    }

    def __init__(
        self,
        process_factory: Callable[..., Any] | None = None,
        powershell_executable: str | None = None,
    ) -> None:
        self._process_factory = process_factory or subprocess.Popen
        self._powershell_override = powershell_executable

    def prepare(
        self,
        workspace_root: str,
        command_id: str,
    ) -> PreparedEngineeringCommand:
        if command_id not in {"test", "build"}:
            raise EngineeringCommandError("ENGINEERING_COMMAND_NOT_ALLOWED")
        try:
            policy = WorkspacePathPolicy(workspace_root)
            root = policy.resolve_directory(".").absolute_path
        except (OSError, RuntimeError, PathPolicyError) as exc:
            raise EngineeringCommandError("ENGINEERING_WORKSPACE_UNAVAILABLE") from exc

        relative_path, display_command = self.COMMANDS[command_id]
        source = root / relative_path
        runner_kind = "powershell"
        if not self._is_regular_file(source) or source.suffix.lower() != ".ps1":
            detected = self._detect_manifest_command(root, command_id)
            if detected is None:
                raise EngineeringCommandError("ENGINEERING_COMMAND_UNAVAILABLE")
            runner_kind, relative_path, display_command = detected
            try:
                source = policy.resolve_existing(relative_path).absolute_path
            except (OSError, RuntimeError, PathPolicyError) as exc:
                raise EngineeringCommandError("ENGINEERING_COMMAND_UNAVAILABLE") from exc
        if not self._is_regular_file(source):
            raise EngineeringCommandError("ENGINEERING_COMMAND_SOURCE_INVALID")
        try:
            script_sha256 = self._sha256(source)
        except OSError as exc:
            raise EngineeringCommandError("ENGINEERING_COMMAND_UNAVAILABLE") from exc
        fingerprint_payload = {
            "command_id": command_id,
            "display_command": display_command,
            "runner_kind": runner_kind,
            "source_relative_path": relative_path,
            "source_sha256": script_sha256,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return PreparedEngineeringCommand(
            commandId=command_id,
            displayCommand=display_command,
            runnerKind=runner_kind,
            sourceRelativePath=relative_path,
            scriptSha256=script_sha256,
            fingerprint=fingerprint,
        )

    def run(
        self,
        workspace_root: str,
        command_id: str,
        expected_fingerprint: str,
        *,
        timeout_seconds: int = 60,
    ) -> ToolResult:
        started_at = now_utc()
        if not MIN_TIMEOUT_SECONDS <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise EngineeringCommandError("ENGINEERING_TIMEOUT_INVALID")
        prepared = self.prepare(workspace_root, command_id)
        if not expected_fingerprint or prepared.fingerprint != expected_fingerprint:
            raise EngineeringCommandError("ENGINEERING_APPROVAL_INVALIDATED")
        policy = WorkspacePathPolicy(workspace_root)
        root = policy.resolve_directory(".").absolute_path
        argv = self._argv(prepared, policy)
        process: Any | None = None
        output_parts: list[bytes] = []
        captured_bytes = 0
        output_truncated = False

        def drain_output() -> None:
            nonlocal captured_bytes, output_truncated
            if process is None or process.stdout is None:
                return
            while True:
                chunk = process.stdout.read(8192)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8", errors="replace")
                remaining = MAX_OUTPUT_BYTES - captured_bytes
                if remaining > 0:
                    kept = chunk[:remaining]
                    output_parts.append(kept)
                    captured_bytes += len(kept)
                if len(chunk) > max(remaining, 0):
                    output_truncated = True

        try:
            process = self._process_factory(
                argv,
                cwd=str(root),
                env=self._safe_environment(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            reader = threading.Thread(
                target=drain_output,
                name="engineering-command-output",
                daemon=True,
            )
            reader.start()
            try:
                process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                self._terminate_process_tree(process)
                process.wait(timeout=5)
                reader.join(timeout=5)
                output = self._sanitize_output(b"".join(output_parts), root)
                return self._result(
                    started_at=started_at,
                    success=False,
                    summary="Engineering command timed out.",
                    command=prepared,
                    output=output,
                    output_truncated=output_truncated,
                    exit_code=None,
                    error_code="ENGINEERING_COMMAND_TIMEOUT",
                )
            reader.join(timeout=5)
            output = self._sanitize_output(b"".join(output_parts), root)
            exit_code = int(process.returncode)
            success = exit_code == 0
            return self._result(
                started_at=started_at,
                success=success,
                summary=(
                    "Engineering command completed."
                    if success
                    else "Engineering command failed."
                ),
                command=prepared,
                output=output,
                output_truncated=output_truncated,
                exit_code=exit_code,
                error_code=None if success else "ENGINEERING_COMMAND_FAILED",
            )
        except OSError:
            return self._result(
                started_at=started_at,
                success=False,
                summary="Engineering command executable is unavailable.",
                command=prepared,
                output="",
                output_truncated=False,
                exit_code=None,
                error_code="ENGINEERING_EXECUTABLE_UNAVAILABLE",
            )

    def _result(
        self,
        *,
        started_at: Any,
        success: bool,
        summary: str,
        command: PreparedEngineeringCommand,
        output: str,
        output_truncated: bool,
        exit_code: int | None,
        error_code: str | None,
    ) -> ToolResult:
        finished_at = now_utc()
        duration_seconds = max(0.0, (finished_at - started_at).total_seconds())
        evidence_data = {
            "command_id": command.commandId,
            "command_source_sha256": command.scriptSha256,
            "exit_code": exit_code,
            "output_truncated": output_truncated,
        }
        return ToolResult(
            success=success,
            status="COMPLETED" if success else "FAILED",
            summary=summary,
            observation={
                "commandId": command.commandId,
                "displayCommand": command.displayCommand,
                "exitCode": exit_code,
                "output": output,
                "outputTruncated": output_truncated,
                "durationSeconds": round(duration_seconds, 2),
            },
            evidence=[ToolEvidence(kind="engineering_command_exit", data=evidence_data)],
            error_code=error_code,
            retryable=False,
            side_effect=True,
            started_at=started_at,
            finished_at=finished_at,
        )

    def _safe_environment(self) -> dict[str, str]:
        allowed = {
            "APPDATA",
            "COMSPEC",
            "LOCALAPPDATA",
            "NUMBER_OF_PROCESSORS",
            "OS",
            "PATH",
            "PATHEXT",
            "PROCESSOR_ARCHITECTURE",
            "SYSTEMDRIVE",
            "SYSTEMROOT",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "WINDIR",
        }
        environment = {
            key: value for key, value in os.environ.items() if key.upper() in allowed
        }
        environment.update(
            {
                "CI": "1",
                "FORCE_COLOR": "0",
                "NO_COLOR": "1",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUTF8": "1",
                "TERM": "dumb",
            }
        )
        return environment

    def _sanitize_output(self, output: bytes, root: Path) -> str:
        try:
            text = output.decode("utf-8")
        except UnicodeDecodeError:
            text = output.decode("cp950", errors="replace")
        text = ANSI_ESCAPE.sub("", text)
        text = re.sub(re.escape(str(root)), "<WORKSPACE>", text, flags=re.IGNORECASE)
        return SECRET_ASSIGNMENT.sub(
            lambda match: f"{match.group(1)}{match.group(2)}***REDACTED***",
            text,
        )

    def _detect_manifest_command(
        self, root: Path, command_id: str
    ) -> tuple[str, str, str] | None:
        package_json = root / "package.json"
        scripts = self._package_scripts(package_json)
        if command_id in scripts:
            package_manager = self._package_manager(root)
            if package_manager == "npm":
                display = "npm test" if command_id == "test" else "npm run build"
            else:
                display = f"{package_manager} {command_id}"
            return package_manager, "package.json", display
        if command_id == "test":
            for marker in ("pyproject.toml", "requirements.txt", "Pipfile"):
                if self._is_regular_file(root / marker):
                    return "python", marker, "python -m pytest"
        return None

    def _package_scripts(self, path: Path) -> set[str]:
        if not self._is_regular_file(path) or path.stat().st_size > 1024 * 1024:
            return set()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return set()
        scripts = payload.get("scripts") if isinstance(payload, dict) else None
        return {str(name) for name in scripts} if isinstance(scripts, dict) else set()

    def _package_manager(self, root: Path) -> str:
        if self._is_regular_file(root / "pnpm-lock.yaml"):
            return "pnpm"
        if self._is_regular_file(root / "yarn.lock"):
            return "yarn"
        return "npm"

    def _argv(
        self, command: PreparedEngineeringCommand, policy: WorkspacePathPolicy
    ) -> list[str]:
        if command.runnerKind == "powershell":
            script = policy.resolve_existing(command.sourceRelativePath).absolute_path
            return [
                self._powershell_executable(),
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ]
        if command.runnerKind in {"npm", "pnpm", "yarn"}:
            executable = self._resolve_executable(f"{command.runnerKind}.cmd")
            if command.runnerKind == "npm" and command.commandId == "build":
                return [executable, "run", "build"]
            return [executable, command.commandId]
        if command.runnerKind == "python" and command.commandId == "test":
            return [self._python_executable(policy), "-m", "pytest"]
        raise EngineeringCommandError("ENGINEERING_COMMAND_NOT_ALLOWED")

    def _python_executable(self, policy: WorkspacePathPolicy) -> str:
        for relative_path in (
            ".venv-win/Scripts/python.exe",
            ".venv/Scripts/python.exe",
            "venv/Scripts/python.exe",
        ):
            try:
                candidate = policy.resolve_existing(relative_path).absolute_path
            except (OSError, RuntimeError, PathPolicyError):
                continue
            if self._is_regular_file(candidate) and candidate.name.lower() == "python.exe":
                return str(candidate)
        return self._resolve_executable("python.exe")

    def _resolve_executable(self, name: str) -> str:
        executable = shutil.which(name, path=os.environ.get("PATH"))
        if not executable:
            raise EngineeringCommandError("ENGINEERING_EXECUTABLE_UNAVAILABLE")
        resolved = Path(executable).resolve(strict=True)
        if not resolved.is_file() or resolved.name.lower() != name.lower():
            raise EngineeringCommandError("ENGINEERING_EXECUTABLE_UNAVAILABLE")
        return str(resolved)

    def _is_regular_file(self, path: Path) -> bool:
        try:
            is_junction = getattr(path, "is_junction", None)
            return (
                path.is_file()
                and not path.is_symlink()
                and not bool(is_junction and is_junction())
            )
        except OSError:
            return False

    def _powershell_executable(self) -> str:
        if self._powershell_override is not None:
            return self._powershell_override
        system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
        if not system_root:
            raise EngineeringCommandError("ENGINEERING_EXECUTABLE_UNAVAILABLE")
        executable = (
            Path(system_root)
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        try:
            executable = executable.resolve(strict=True)
        except OSError as exc:
            raise EngineeringCommandError("ENGINEERING_EXECUTABLE_UNAVAILABLE") from exc
        if not executable.is_file() or executable.name.lower() != "powershell.exe":
            raise EngineeringCommandError("ENGINEERING_EXECUTABLE_UNAVAILABLE")
        return str(executable)

    def _terminate_process_tree(self, process: Any) -> None:
        pid = getattr(process, "pid", None)
        if isinstance(pid, int) and pid > 0:
            try:
                module = importlib.import_module("psutil")
                parent = getattr(module, "Process")(pid)
                children = parent.children(recursive=True)
                for child in reversed(children):
                    child.kill()
                getattr(module, "wait_procs")(children, timeout=3)
            except Exception:
                pass
        process.kill()

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
