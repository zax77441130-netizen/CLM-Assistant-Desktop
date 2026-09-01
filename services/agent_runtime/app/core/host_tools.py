from __future__ import annotations

import platform
import ctypes
import os
import subprocess
import sys
from typing import Any

from pydantic import BaseModel

from app.core.path_policy import WorkspacePathPolicy
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

BLOCKED_OPEN_EXTENSIONS = {".exe", ".com", ".bat", ".cmd", ".ps1", ".msi", ".scr", ".lnk", ".url"}
PROTECTED_PROCESSES = {"system", "system idle process", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe", "explorer.exe", "agent-runtime.exe", "clm assistant desktop.exe"}
MAX_CLIPBOARD_TEXT = 64 * 1024


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


def open_workspace_file(workspace_root: str, path: str) -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    target = policy.resolve_existing(path).absolute_path
    if not target.is_file():
        raise ValueError("NOT_FILE")
    if target.suffix.lower() in BLOCKED_OPEN_EXTENSIONS:
        raise ValueError("EXECUTABLE_OPEN_REJECTED")
    if os.environ.get("CLM_HOST_TEST_MODE") == "1":
        return result("Workspace file open validated by test adapter.", {"path": path, "adapter": "test"})
    _shell_open(str(target))
    return result("Workspace file opened.", {"path": path}, side_effect=True)


def open_workspace_folder(workspace_root: str, path: str = ".") -> ToolResult:
    policy = WorkspacePathPolicy(workspace_root)
    target = policy.resolve_directory(path).absolute_path
    if os.environ.get("CLM_HOST_TEST_MODE") == "1":
        return result("Workspace folder open validated by test adapter.", {"path": path, "adapter": "test"})
    _shell_open(str(target))
    return result("Workspace folder opened.", {"path": path}, side_effect=True)


def _shell_open(path: str) -> None:
    if sys.platform != "win32":
        raise ValueError("WINDOWS_ONLY")
    rc = ctypes.windll.shell32.ShellExecuteW(None, "open", path, None, None, 1)
    if rc <= 32:
        raise ValueError("SHELL_OPEN_FAILED")


def clipboard_read_text() -> ToolResult:
    text = _clipboard_get_text()
    masked = _mask_secret_like(text[:MAX_CLIPBOARD_TEXT])
    return result("Clipboard text read.", {"text": masked, "characters": len(text), "masked": masked != text})


def clipboard_write_text(text: str) -> ToolResult:
    if len(text.encode("utf-8")) > MAX_CLIPBOARD_TEXT:
        raise ValueError("CLIPBOARD_TEXT_TOO_LARGE")
    _clipboard_set_text(text)
    return result("Clipboard text written.", {"characters": len(text)}, side_effect=True)


def terminate_process(pid: int, expected_name: str | None = None) -> ToolResult:
    if pid == os.getpid():
        raise ValueError("SELF_TERMINATION_REJECTED")
    info = _process_info(pid)
    name = str(info.get("image_name", "")).lower()
    if not name or name in PROTECTED_PROCESSES:
        raise ValueError("PROTECTED_PROCESS_REJECTED")
    if expected_name and name != expected_name.lower():
        raise ValueError("PID_REUSE_REJECTED")
    if os.environ.get("CLM_HOST_TEST_MODE") == "1":
        return result("Process termination validated by test adapter.", {"pid": pid, "image_name": info.get("image_name"), "adapter": "test"}, side_effect=True)
    handle = ctypes.windll.kernel32.OpenProcess(0x0001, False, pid)
    if not handle:
        raise ValueError("PROCESS_OPEN_FAILED")
    try:
        if not ctypes.windll.kernel32.TerminateProcess(handle, 1):
            raise ValueError("PROCESS_TERMINATE_FAILED")
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)
    return result("Process terminated.", {"pid": pid, "image_name": info.get("image_name")}, side_effect=True)


def _process_info(pid: int) -> dict[str, Any]:
    completed = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], check=False, capture_output=True, text=True, timeout=10)
    for line in completed.stdout.splitlines():
        parts = [part.strip('"') for part in line.split('","')]
        if len(parts) >= 2 and parts[1] == str(pid):
            return {"image_name": parts[0], "pid": pid}
    return {"pid": pid}


def _clipboard_get_text() -> str:
    if os.environ.get("CLM_HOST_TEST_MODE") == "1":
        return os.environ.get("CLM_TEST_CLIPBOARD_TEXT", "")
    if sys.platform != "win32":
        raise ValueError("WINDOWS_ONLY")
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.OpenClipboard(None):
        raise ValueError("CLIPBOARD_OPEN_FAILED")
    try:
        handle = user32.GetClipboardData(13)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _clipboard_set_text(text: str) -> None:
    if os.environ.get("CLM_HOST_TEST_MODE") == "1":
        os.environ["CLM_TEST_CLIPBOARD_TEXT"] = text
        return
    if sys.platform != "win32":
        raise ValueError("WINDOWS_ONLY")
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    data = text + "\0"
    size = len(data) * ctypes.sizeof(ctypes.c_wchar)
    if not user32.OpenClipboard(None):
        raise ValueError("CLIPBOARD_OPEN_FAILED")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(0x0002, size)
        pointer = kernel32.GlobalLock(handle)
        ctypes.memmove(pointer, ctypes.create_unicode_buffer(data), size)
        kernel32.GlobalUnlock(handle)
        user32.SetClipboardData(13, handle)
    finally:
        user32.CloseClipboard()


def _mask_secret_like(text: str) -> str:
    import re

    return re.sub(r"(sk-[A-Za-z0-9_-]{12,}|[A-Za-z0-9_]*TOKEN[A-Za-z0-9_]*\s*=\s*)[^\s]+", "[已遮罩]", text)
