from __future__ import annotations

import hashlib
import importlib
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.core.tool_sdk import ToolEvidence, ToolResult, argument_hash, now_utc

WINDOW_STATES = {"restore", "minimize", "maximize"}
PASSWORD_CONTROL_TYPES = {"Edit"}
DANGEROUS_CONTROL_NAMES = {"儲存", "保存", "刪除", "送出", "發布", "購買", "安裝", "確認", "save", "delete", "submit", "publish", "buy", "install", "confirm"}
MAX_CONTROL_TEXT = 32 * 1024
MAX_CAPTURE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class WindowIdentity:
    app_id: str
    executable: str
    pid: int
    process_creation_time: str
    handle: int
    runtime_id: str
    window_session_id: str
    fingerprint: str
    title_preview: str


@dataclass(frozen=True)
class ControlTarget:
    name: str
    control_type: str
    automation_id: str | None = None


class DesktopAutomationAdapter(Protocol):
    def list_windows(self, app_id: str | None = None) -> list[WindowIdentity]: ...
    def wait_for_window(self, app_id: str, timeout_seconds: int) -> WindowIdentity: ...
    def activate_window(self, target: WindowIdentity) -> WindowIdentity: ...
    def get_window_state(self, target: WindowIdentity) -> str: ...
    def set_window_state(self, target: WindowIdentity, state: str) -> WindowIdentity: ...
    def inspect_controls(self, target: WindowIdentity) -> list[dict[str, Any]]: ...
    def read_control_text(self, target: WindowIdentity, control: ControlTarget) -> str: ...
    def invoke_control(self, target: WindowIdentity, control: ControlTarget) -> dict[str, Any]: ...
    def set_control_text(self, target: WindowIdentity, control: ControlTarget, text: str) -> dict[str, Any]: ...
    def select_item(self, target: WindowIdentity, control: ControlTarget, item_name: str) -> dict[str, Any]: ...
    def scroll_control(self, target: WindowIdentity, control: ControlTarget, direction: str) -> dict[str, Any]: ...
    def close_window(self, target: WindowIdentity) -> dict[str, Any]: ...
    def capture_window(self, target: WindowIdentity, artifact_dir: Path) -> dict[str, Any]: ...


class AutomationProfileRegistry:
    PROFILES: dict[str, dict[str, Any]] = {
        "notepad": {
            "display_name": "Windows Notepad",
            "executables": {"notepad.exe"},
            "allowed_actions": {"list", "wait", "activate", "state", "inspect", "read", "write", "invoke", "close", "capture"},
            "dangerous_actions": {"close", "dangerous_invoke"},
        },
        "explorer": {
            "display_name": "Windows File Explorer",
            "executables": {"explorer.exe"},
            "allowed_actions": {"list", "wait", "activate", "state", "inspect", "read", "select", "scroll", "capture"},
            "dangerous_actions": {"close"},
        },
        "generic_readonly": {
            "display_name": "Generic UIA Read-only",
            "executables": set(),
            "allowed_actions": {"list", "wait", "activate", "state", "inspect"},
            "dangerous_actions": set(),
        },
    }

    def profile_for(self, app_id: str) -> dict[str, Any]:
        if app_id not in self.PROFILES:
            raise ValueError("UNKNOWN_AUTOMATION_PROFILE")
        return self.PROFILES[app_id]

    def assert_action_allowed(self, app_id: str, action: str) -> None:
        profile = self.profile_for(app_id)
        if action not in profile["allowed_actions"]:
            raise ValueError("AUTOMATION_PROFILE_ACTION_REJECTED")


class WindowTargetResolver:
    def resolve(self, candidates: list[WindowIdentity], window_session_id: str | None) -> WindowIdentity:
        if window_session_id:
            matches = [item for item in candidates if item.window_session_id == window_session_id]
            if len(matches) == 1:
                return matches[0]
            raise ValueError("WINDOW_TARGET_NOT_FOUND")
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise ValueError("WINDOW_TARGET_AMBIGUOUS")
        raise ValueError("WINDOW_TARGET_NOT_FOUND")

    def revalidate(self, adapter: DesktopAutomationAdapter, target: WindowIdentity) -> WindowIdentity:
        current = self.resolve(adapter.list_windows(target.app_id), target.window_session_id)
        if current.fingerprint != target.fingerprint:
            raise ValueError("WINDOW_TARGET_CHANGED")
        return current


class ControlResolver:
    def resolve(self, controls: list[dict[str, Any]], control: ControlTarget, *, require_pattern: str | None = None) -> dict[str, Any]:
        matches = []
        for candidate in controls:
            if candidate.get("controlType") != control.control_type:
                continue
            if control.name and candidate.get("name") != control.name:
                continue
            if control.automation_id and candidate.get("automationId") != control.automation_id:
                continue
            if candidate.get("isPassword"):
                raise ValueError("PASSWORD_CONTROL_REJECTED")
            if not candidate.get("enabled", False) or candidate.get("offscreen", False):
                raise ValueError("CONTROL_NOT_INTERACTABLE")
            if require_pattern and require_pattern not in set(candidate.get("patterns") or []):
                raise ValueError("UNSUPPORTED_UIA_PATTERN")
            matches.append(candidate)
        if len(matches) != 1:
            raise ValueError("CONTROL_TARGET_AMBIGUOUS" if matches else "CONTROL_TARGET_NOT_FOUND")
        return matches[0]


class DesktopActionPolicy:
    def assert_control_action(self, action: str, control: ControlTarget, *, approved: bool = False) -> None:
        if control.control_type == "Password":
            raise ValueError("PASSWORD_CONTROL_REJECTED")
        if action == "invoke" and control.name.lower() in DANGEROUS_CONTROL_NAMES and not approved:
            raise ValueError("DESKTOP_APPROVAL_REQUIRED")


class DesktopObservationService:
    def observation(self, target: WindowIdentity, **items: Any) -> dict[str, Any]:
        return {
            "windowSessionId": target.window_session_id,
            "app": target.app_id,
            "titlePreview": target.title_preview,
            "postcondition": {"verified": True, "targetFingerprint": target.fingerprint},
            **items,
        }


class AutomationPostcondition:
    def require(self, condition: bool, code: str) -> None:
        if not condition:
            raise ValueError(code)


class ScreenArtifactService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(os.environ.get("CLM_SCREEN_ARTIFACT_DIR", Path(tempfile.gettempdir()) / "clm-screen-artifacts"))

    def path_for(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root / f"{uuid.uuid4()}.png"


class DesktopSessionService:
    def new_session_id(self) -> str:
        return str(uuid.uuid4())


class WindowDiscoveryService:
    def __init__(self, adapter: DesktopAutomationAdapter | None = None) -> None:
        self.adapter = adapter or adapter_from_environment()

    def list(self, app_id: str | None = None) -> list[WindowIdentity]:
        return self.adapter.list_windows(app_id)


class WindowsUIAutomationAdapter:
    def __init__(self) -> None:
        if os.environ.get("CLM_UIA_NONINTERACTIVE") == "1":
            raise ValueError("UIA_LIVE_DEFERRED_NONINTERACTIVE_SESSION")
        self._desktop_factory: Any | None = None

    def _desktop(self) -> Any:
        if self._desktop_factory is None:
            module = importlib.import_module("pywinauto")
            self._desktop_factory = getattr(module, "Desktop")
        return self._desktop_factory(backend="uia")

    def list_windows(self, app_id: str | None = None) -> list[WindowIdentity]:
        windows = []
        for window in self._desktop().windows():
            try:
                info = window.element_info
                pid = int(info.process_id)
                executable = _process_executable(pid)
                inferred_app = _app_id_for_executable(executable)
                if app_id and inferred_app != app_id:
                    continue
                windows.append(_identity(app_id or inferred_app, executable, pid, int(window.handle), _runtime_id(info), window.window_text()))
            except Exception:
                continue
        return windows

    def wait_for_window(self, app_id: str, timeout_seconds: int) -> WindowIdentity:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            windows = self.list_windows(app_id)
            if len(windows) == 1:
                return windows[0]
            if len(windows) > 1:
                raise ValueError("WINDOW_TARGET_AMBIGUOUS")
            time.sleep(0.25)
        raise ValueError("WINDOW_WAIT_TIMEOUT")

    def _wrapper(self, target: WindowIdentity) -> Any:
        resolver = WindowTargetResolver()
        current = resolver.revalidate(self, target)
        return self._desktop().window(handle=current.handle)

    def activate_window(self, target: WindowIdentity) -> WindowIdentity:
        window = self._wrapper(target)
        window.set_focus()
        return target

    def get_window_state(self, target: WindowIdentity) -> str:
        window = self._wrapper(target)
        if window.is_minimized():
            return "minimize"
        if window.is_maximized():
            return "maximize"
        return "restore"

    def set_window_state(self, target: WindowIdentity, state: str) -> WindowIdentity:
        window = self._wrapper(target)
        if state == "maximize":
            window.maximize()
        elif state == "minimize":
            window.minimize()
        elif state == "restore":
            window.restore()
        else:
            raise ValueError("WINDOW_STATE_UNSUPPORTED")
        return target

    def inspect_controls(self, target: WindowIdentity) -> list[dict[str, Any]]:
        window = self._wrapper(target)
        controls = []
        for child in window.descendants():
            info = child.element_info
            controls.append(_control_metadata(child, info))
            if len(controls) >= 200:
                break
        return controls

    def read_control_text(self, target: WindowIdentity, control: ControlTarget) -> str:
        wrapper = self._control_wrapper(target, control, "ValuePattern")
        text = str(wrapper.get_value())
        return text[:MAX_CONTROL_TEXT]

    def invoke_control(self, target: WindowIdentity, control: ControlTarget) -> dict[str, Any]:
        wrapper = self._control_wrapper(target, control, "InvokePattern")
        wrapper.invoke()
        return {"invoked": True}

    def set_control_text(self, target: WindowIdentity, control: ControlTarget, text: str) -> dict[str, Any]:
        wrapper = self._control_wrapper(target, control, "ValuePattern")
        wrapper.set_edit_text(text)
        observed = str(wrapper.get_value())
        return {"characters": len(text), "verifiedText": observed == text}

    def select_item(self, target: WindowIdentity, control: ControlTarget, item_name: str) -> dict[str, Any]:
        wrapper = self._control_wrapper(target, control, "SelectionItemPattern")
        wrapper.select()
        return {"selected": item_name}

    def scroll_control(self, target: WindowIdentity, control: ControlTarget, direction: str) -> dict[str, Any]:
        wrapper = self._control_wrapper(target, control, "ScrollPattern")
        if direction == "down":
            wrapper.scroll("down", "line")
        elif direction == "up":
            wrapper.scroll("up", "line")
        else:
            raise ValueError("SCROLL_DIRECTION_UNSUPPORTED")
        return {"direction": direction}

    def close_window(self, target: WindowIdentity) -> dict[str, Any]:
        window = self._wrapper(target)
        window.close()
        return {"closed": True}

    def capture_window(self, target: WindowIdentity, artifact_dir: Path) -> dict[str, Any]:
        path = artifact_dir / f"{uuid.uuid4()}.png"
        window = self._wrapper(target)
        image = window.capture_as_image()
        image.save(path)
        size = path.stat().st_size
        if size > MAX_CAPTURE_BYTES:
            path.unlink(missing_ok=True)
            raise ValueError("SCREEN_ARTIFACT_TOO_LARGE")
        return {"artifactPath": str(path), "size": size}

    def _control_wrapper(self, target: WindowIdentity, control: ControlTarget, pattern: str) -> Any:
        controls = self.inspect_controls(target)
        resolved = ControlResolver().resolve(controls, control, require_pattern=pattern)
        window = self._wrapper(target)
        return window.child_window(auto_id=resolved.get("automationId") or None, title=resolved.get("name") or None, control_type=resolved.get("controlType"))


class FakeDesktopAutomationAdapter:
    def __init__(self) -> None:
        self.state = "restore"
        self.text = ""
        self.closed = False
        self.target = _identity("notepad", "notepad.exe", 4242, 1001, "1.2.3", "Phase 6 Fixture")
        self.controls = [
            {"name": "內容", "controlType": "Edit", "automationId": "TextBox", "enabled": True, "offscreen": False, "isPassword": False, "patterns": ["ValuePattern"]},
            {"name": "執行", "controlType": "Button", "automationId": "RunButton", "enabled": True, "offscreen": False, "isPassword": False, "patterns": ["InvokePattern"]},
            {"name": "危險", "controlType": "Button", "automationId": "DangerButton", "enabled": True, "offscreen": False, "isPassword": False, "patterns": ["InvokePattern"]},
            {"name": "密碼", "controlType": "Edit", "automationId": "PasswordBox", "enabled": True, "offscreen": False, "isPassword": True, "patterns": ["ValuePattern"]},
        ]

    def list_windows(self, app_id: str | None = None) -> list[WindowIdentity]:
        if self.closed:
            return []
        if app_id and app_id != self.target.app_id:
            return []
        return [self.target]

    def wait_for_window(self, app_id: str, timeout_seconds: int) -> WindowIdentity:
        del timeout_seconds
        windows = self.list_windows(app_id)
        if len(windows) != 1:
            raise ValueError("WINDOW_TARGET_NOT_FOUND")
        return windows[0]

    def activate_window(self, target: WindowIdentity) -> WindowIdentity:
        return self._same(target)

    def get_window_state(self, target: WindowIdentity) -> str:
        self._same(target)
        return self.state

    def set_window_state(self, target: WindowIdentity, state: str) -> WindowIdentity:
        self._same(target)
        self.state = state
        return target

    def inspect_controls(self, target: WindowIdentity) -> list[dict[str, Any]]:
        self._same(target)
        return list(self.controls)

    def read_control_text(self, target: WindowIdentity, control: ControlTarget) -> str:
        ControlResolver().resolve(self.inspect_controls(target), control, require_pattern="ValuePattern")
        return self.text

    def invoke_control(self, target: WindowIdentity, control: ControlTarget) -> dict[str, Any]:
        ControlResolver().resolve(self.inspect_controls(target), control, require_pattern="InvokePattern")
        return {"invoked": True, "statusText": "safe invoked"}

    def set_control_text(self, target: WindowIdentity, control: ControlTarget, text: str) -> dict[str, Any]:
        ControlResolver().resolve(self.inspect_controls(target), control, require_pattern="ValuePattern")
        self.text = text
        return {"characters": len(text), "verifiedText": self.text == text}

    def select_item(self, target: WindowIdentity, control: ControlTarget, item_name: str) -> dict[str, Any]:
        ControlResolver().resolve(self.inspect_controls(target), control)
        return {"selected": item_name}

    def scroll_control(self, target: WindowIdentity, control: ControlTarget, direction: str) -> dict[str, Any]:
        ControlResolver().resolve(self.inspect_controls(target), control)
        return {"direction": direction}

    def close_window(self, target: WindowIdentity) -> dict[str, Any]:
        self._same(target)
        self.closed = True
        return {"closed": True}

    def capture_window(self, target: WindowIdentity, artifact_dir: Path) -> dict[str, Any]:
        self._same(target)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / f"{uuid.uuid4()}.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        return {"artifactPath": str(path), "size": path.stat().st_size}

    def _same(self, target: WindowIdentity) -> WindowIdentity:
        if target.fingerprint != self.target.fingerprint:
            raise ValueError("WINDOW_TARGET_CHANGED")
        return self.target


_FAKE_ADAPTER: FakeDesktopAutomationAdapter | None = None


def adapter_from_environment() -> DesktopAutomationAdapter:
    global _FAKE_ADAPTER
    if os.environ.get("CLM_DESKTOP_AUTOMATION_ADAPTER") == "fake":
        if _FAKE_ADAPTER is None or _FAKE_ADAPTER.closed:
            _FAKE_ADAPTER = FakeDesktopAutomationAdapter()
        return _FAKE_ADAPTER
    return WindowsUIAutomationAdapter()


def ok(summary: str, observation: dict[str, Any], *, side_effect: bool = False) -> ToolResult:
    started = now_utc()
    return ToolResult(
        success=True,
        status="COMPLETED",
        summary=summary,
        observation=observation,
        evidence=[ToolEvidence(kind="structured_observation", data=observation)],
        side_effect=side_effect,
        started_at=started,
        finished_at=now_utc(),
    )


def list_windows(app_id: str | None = None, *, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    active = adapter or adapter_from_environment()
    windows = [_window_observation(item) for item in active.list_windows(app_id)]
    return ok("Desktop windows listed.", {"windows": windows, "count": len(windows), "postcondition": {"verified": True}})


def wait_for_window(app_id: str, timeout_seconds: int = 10, *, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    active = adapter or adapter_from_environment()
    target = active.wait_for_window(app_id, timeout_seconds)
    return ok("Desktop window found.", DesktopObservationService().observation(target, window=_window_observation(target)))


def activate_window(target: dict[str, Any], *, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    active = adapter or adapter_from_environment()
    identity = _target_from_args(target)
    AutomationProfileRegistry().assert_action_allowed(identity.app_id, "activate")
    verified = active.activate_window(identity)
    return ok("Desktop window activated.", DesktopObservationService().observation(verified), side_effect=True)


def get_window_state(target: dict[str, Any], *, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    active = adapter or adapter_from_environment()
    identity = _target_from_args(target)
    state = active.get_window_state(identity)
    return ok("Desktop window state collected.", DesktopObservationService().observation(identity, state=state))


def set_window_state(target: dict[str, Any], state: str, *, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    if state not in WINDOW_STATES:
        raise ValueError("WINDOW_STATE_UNSUPPORTED")
    active = adapter or adapter_from_environment()
    identity = _target_from_args(target)
    AutomationProfileRegistry().assert_action_allowed(identity.app_id, "state")
    active.set_window_state(identity, state)
    observed = active.get_window_state(identity)
    AutomationPostcondition().require(observed == state, "POSTCONDITION_WINDOW_STATE_FAILED")
    return ok("Desktop window state changed.", DesktopObservationService().observation(identity, state=observed), side_effect=True)


def inspect_controls(target: dict[str, Any], *, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    active = adapter or adapter_from_environment()
    identity = _target_from_args(target)
    AutomationProfileRegistry().assert_action_allowed(identity.app_id, "inspect")
    controls = [_safe_control(item) for item in active.inspect_controls(identity)]
    return ok("Desktop controls inspected.", DesktopObservationService().observation(identity, controls=controls, count=len(controls)))


def read_control_text(target: dict[str, Any], control: dict[str, Any], *, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    active = adapter or adapter_from_environment()
    identity = _target_from_args(target)
    AutomationProfileRegistry().assert_action_allowed(identity.app_id, "read")
    control_target = _control_from_args(control)
    text = active.read_control_text(identity, control_target)
    return ok("Desktop control text read.", DesktopObservationService().observation(identity, text=text[:MAX_CONTROL_TEXT], characters=len(text)))


def invoke_control(target: dict[str, Any], control: dict[str, Any], *, approved: bool = False, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    active = adapter or adapter_from_environment()
    identity = _target_from_args(target)
    AutomationProfileRegistry().assert_action_allowed(identity.app_id, "invoke")
    control_target = _control_from_args(control)
    DesktopActionPolicy().assert_control_action("invoke", control_target, approved=approved)
    result = active.invoke_control(identity, control_target)
    return ok("Desktop control invoked.", DesktopObservationService().observation(identity, **result), side_effect=True)


def set_control_text(target: dict[str, Any], control: dict[str, Any], text: str, *, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    if len(text.encode("utf-8")) > MAX_CONTROL_TEXT:
        raise ValueError("CONTROL_TEXT_TOO_LARGE")
    active = adapter or adapter_from_environment()
    identity = _target_from_args(target)
    AutomationProfileRegistry().assert_action_allowed(identity.app_id, "write")
    control_target = _control_from_args(control)
    result = active.set_control_text(identity, control_target, text)
    AutomationPostcondition().require(bool(result.get("verifiedText")), "POSTCONDITION_SET_TEXT_FAILED")
    return ok("Desktop control text set.", DesktopObservationService().observation(identity, characters=len(text)), side_effect=True)


def select_item(target: dict[str, Any], control: dict[str, Any], item_name: str, *, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    active = adapter or adapter_from_environment()
    identity = _target_from_args(target)
    AutomationProfileRegistry().assert_action_allowed(identity.app_id, "select")
    result = active.select_item(identity, _control_from_args(control), item_name)
    return ok("Desktop item selected.", DesktopObservationService().observation(identity, **result), side_effect=True)


def scroll_control(target: dict[str, Any], control: dict[str, Any], direction: str, *, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    active = adapter or adapter_from_environment()
    identity = _target_from_args(target)
    AutomationProfileRegistry().assert_action_allowed(identity.app_id, "scroll")
    result = active.scroll_control(identity, _control_from_args(control), direction)
    return ok("Desktop control scrolled.", DesktopObservationService().observation(identity, **result), side_effect=True)


def close_window(target: dict[str, Any], *, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    active = adapter or adapter_from_environment()
    identity = _target_from_args(target)
    AutomationProfileRegistry().assert_action_allowed(identity.app_id, "close")
    result = active.close_window(identity)
    AutomationPostcondition().require(not active.list_windows(identity.app_id), "POSTCONDITION_CLOSE_FAILED")
    return ok("Desktop window closed.", DesktopObservationService().observation(identity, **result), side_effect=True)


def capture_window(target: dict[str, Any], *, adapter: DesktopAutomationAdapter | None = None) -> ToolResult:
    active = adapter or adapter_from_environment()
    identity = _target_from_args(target)
    AutomationProfileRegistry().assert_action_allowed(identity.app_id, "capture")
    artifact_dir = ScreenArtifactService().path_for().parent
    result = active.capture_window(identity, artifact_dir)
    return ok("Desktop window captured.", DesktopObservationService().observation(identity, artifactId=Path(str(result["artifactPath"])).stem, size=result["size"]), side_effect=True)


def _identity(app_id: str, executable: str, pid: int, handle: int, runtime_id: str, title: str) -> WindowIdentity:
    creation_time = _process_creation_time(pid)
    session_id = str(uuid.uuid4())
    fingerprint = argument_hash({"app": app_id, "exe": executable.lower(), "pid": pid, "created": creation_time, "handle": handle, "runtime": runtime_id})
    return WindowIdentity(app_id, executable.lower(), pid, creation_time, handle, runtime_id, session_id, fingerprint, _title_preview(title))


def _target_from_args(target: dict[str, Any]) -> WindowIdentity:
    required = ["app", "executable", "pid", "processCreationTime", "windowHandle", "runtimeId", "windowSessionId", "targetFingerprint"]
    if any(key not in target for key in required):
        raise ValueError("WINDOW_TARGET_BINDING_REQUIRED")
    identity = WindowIdentity(
        app_id=str(target["app"]),
        executable=str(target["executable"]).lower(),
        pid=int(target["pid"]),
        process_creation_time=str(target["processCreationTime"]),
        handle=int(target["windowHandle"]),
        runtime_id=str(target["runtimeId"]),
        window_session_id=str(target["windowSessionId"]),
        fingerprint=str(target["targetFingerprint"]),
        title_preview=str(target.get("titlePreview") or ""),
    )
    expected = argument_hash(
        {
            "app": identity.app_id,
            "exe": identity.executable,
            "pid": identity.pid,
            "created": identity.process_creation_time,
            "handle": identity.handle,
            "runtime": identity.runtime_id,
        }
    )
    if expected != identity.fingerprint:
        raise ValueError("WINDOW_TARGET_CHANGED")
    return identity


def _control_from_args(control: dict[str, Any]) -> ControlTarget:
    if "coordinates" in control or "selector" in control or "xpath" in control:
        raise ValueError("UNSAFE_CONTROL_SELECTOR_REJECTED")
    return ControlTarget(name=str(control.get("name") or ""), control_type=str(control.get("controlType") or ""), automation_id=control.get("automationId"))


def _window_observation(item: WindowIdentity) -> dict[str, Any]:
    return {
        "app": item.app_id,
        "executable": item.executable,
        "pid": item.pid,
        "processCreationTime": item.process_creation_time,
        "windowHandle": item.handle,
        "runtimeId": item.runtime_id,
        "windowSessionId": item.window_session_id,
        "targetFingerprint": item.fingerprint,
        "titlePreview": item.title_preview,
    }


def _safe_control(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(item.get("name") or "")[:120],
        "controlType": str(item.get("controlType") or ""),
        "automationId": str(item.get("automationId") or "")[:120],
        "enabled": bool(item.get("enabled")),
        "offscreen": bool(item.get("offscreen")),
        "patterns": list(item.get("patterns") or [])[:10],
        "isPassword": bool(item.get("isPassword")),
    }


def _control_metadata(wrapper: Any, info: Any) -> dict[str, Any]:
    patterns = []
    for pattern_name in ("ValuePattern", "InvokePattern", "SelectionItemPattern", "ScrollPattern"):
        try:
            if wrapper.iface_value.CurrentIsReadOnly is not None and pattern_name == "ValuePattern":
                patterns.append(pattern_name)
        except Exception:
            pass
    if hasattr(wrapper, "invoke"):
        patterns.append("InvokePattern")
    return {
        "name": str(info.name or "")[:120],
        "controlType": str(info.control_type or ""),
        "automationId": str(info.automation_id or "")[:120],
        "enabled": bool(info.enabled),
        "offscreen": bool(getattr(info, "offscreen", False)),
        "patterns": sorted(set(patterns)),
        "isPassword": bool(getattr(info, "is_password", False)),
    }


def _runtime_id(info: Any) -> str:
    try:
        return ".".join(str(part) for part in info.runtime_id)
    except Exception:
        return "unknown"


def _process_executable(pid: int) -> str:
    try:
        module = importlib.import_module("psutil")
        process = module.Process(pid)
        return str(Path(process.exe()).name or "unknown.exe")
    except Exception:
        return "unknown.exe"


def _process_creation_time(pid: int) -> str:
    try:
        module = importlib.import_module("psutil")
        process = module.Process(pid)
        return f"{float(process.create_time()):.6f}"
    except Exception:
        return hashlib.sha256(str(pid).encode("utf-8")).hexdigest()[:16]


def _app_id_for_executable(executable: str) -> str:
    name = Path(executable).name.lower()
    if name == "notepad.exe":
        return "notepad"
    if name == "explorer.exe":
        return "explorer"
    return "generic_readonly"


def _title_preview(title: str) -> str:
    cleaned = " ".join(title.split())
    return cleaned[:80]
