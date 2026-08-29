from __future__ import annotations

import platform
import subprocess
from typing import Any

from pydantic import BaseModel

from app.core.tool_sdk import ToolEvidence, ToolResult, now_utc


class RegisteredApp(BaseModel):
    app_id: str
    display_name: str
    executable: str
    args: list[str] = []


REGISTERED_APPS = {
    "notepad": RegisteredApp(app_id="notepad", display_name="Notepad", executable="notepad.exe"),
    "explorer": RegisteredApp(app_id="explorer", display_name="File Explorer", executable="explorer.exe"),
    "vscode": RegisteredApp(app_id="vscode", display_name="VS Code", executable="code.cmd"),
}


def result(summary: str, observation: dict[str, Any], *, side_effect: bool = False) -> ToolResult:
    now = now_utc()
    return ToolResult(
        success=True,
        status="COMPLETED",
        summary=summary,
        observation=observation,
        evidence=[ToolEvidence(kind="structured_observation", data=observation)],
        side_effect=side_effect,
        started_at=now,
        finished_at=now_utc(),
    )


def system_info() -> ToolResult:
    return result(
        "System information collected.",
        {
            "windows_version": platform.platform(),
            "architecture": platform.machine(),
            "hostname": platform.node(),
            "python_runtime_mode": "sidecar",
            "agent_runtime_version": "0.1.0",
        },
    )


def list_processes(limit: int = 50) -> ToolResult:
    completed = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    lines = completed.stdout.splitlines()[:limit]
    processes = []
    for line in lines:
        parts = [part.strip('"') for part in line.split('","')]
        if len(parts) >= 2:
            processes.append({"image_name": parts[0], "pid": parts[1]})
    return result("Process list collected.", {"processes": processes, "limit": limit})


def list_registered_apps() -> ToolResult:
    return result("Registered app whitelist collected.", {"apps": [app.model_dump(exclude={"executable"}) for app in REGISTERED_APPS.values()]})


def launch_registered_app(app_id: str) -> ToolResult:
    if app_id not in REGISTERED_APPS:
        raise ValueError("ARBITRARY_EXECUTABLE_REJECTED")
    app = REGISTERED_APPS[app_id]
    return result(
        "Registered app launch validated by mock adapter.",
        {"app_id": app.app_id, "display_name": app.display_name, "human_verification_required": True},
        side_effect=True,
    )
