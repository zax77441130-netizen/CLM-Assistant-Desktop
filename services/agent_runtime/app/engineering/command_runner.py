from __future__ import annotations

import hashlib
import json
import os
import re
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
MAX_TIMEOUT_SECONDS = 60
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\\b(token|api[_-]?key|secret|password|authorization|cookie)\\b(\\s*[:=]\\s*)([^\\s]+)"
)


class EngineeringCommandError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PreparedEngineeringCommand(BaseModel):
    commandId: str
    displayCommand: str
    scriptRelativePath: str
    scriptSha256: str
    fingerprint: str


class EngineeringCommandRunner:
    """Run only repository-owned Windows validation scripts after exact approval."""

    COMMANDS = {
        "test": ("scripts/test_windows.ps1", r".\\scripts\\test_windows.ps1"),
        "build": ("scripts/build_desktop.ps1", r".\\scripts\\build_desktop.ps1"),
    }

    def __init__(self, process_factory: Callable[..., Any] = subprocess.Popen) -> None:
        self._process_factory = process_factory

    def prepare(
        self,
        workspace_root: str,
        command_id: str,
    ) -> PreparedEngineeringCommand:
        if command_id not in self.COMMANDS:
            raise EngineeringCommandError("ENGINEERING_COMMAND_NOT_ALLOWED")
        try:
            policy = WorkspacePathPolicy(workspace_root)
            relative_path, display_command = self.COMMANDS[command_id]
            script = policy.resolve_existing(relative_path).absolute_path
        except (OSError, RuntimeError, PathPolicyError) as exc:
            raise EngineeringCommandError("ENGINEERING_SCRIPT_UNAVAILABLE") from exc
        if not script.is_file() or script.suffix.lower() != ".ps1":
            raise EngineeringCommandError("ENGINEERING_SCRIPT_INVALID")
        script_sha256 = self._sha256(script)
        fingerprint_payload = {
            "command_id": command_id,
            "script_relative_path": relative_path,
            "script_sha256": script_sha256,
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
            scriptRelativePath=relative_path,
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
        script = policy.resolve_existing(prepared.scriptRelativePath).absolute_path
        argv = [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ]
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
                process.kill()
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
        evidence_data = {
            "command_id": command.commandId,
            "script_sha256": command.scriptSha256,
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
            },
            evidence=[ToolEvidence(kind="engineering_command_exit", data=evidence_data)],
            error_code=error_code,
            retryable=False,
            side_effect=True,
            started_at=started_at,
            finished_at=now_utc(),
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
        return {key: value for key, value in os.environ.items() if key.upper() in allowed}

    def _sanitize_output(self, output: bytes, root: Path) -> str:
        text = output.decode("utf-8", errors="replace")
        text = text.replace(str(root), "<WORKSPACE>")
        return SECRET_ASSIGNMENT.sub(
            lambda match: f"{match.group(1)}{match.group(2)}***REDACTED***",
            text,
        )

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
