from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import pytest

from app.agent.capability_policy import CapabilityDecision, CapabilityPolicy
from app.agent.contracts import AgentPlan, PlanContext, PlanStepSpec
from app.agent.orchestrator import PlanValidator
from app.agent.planner import DeterministicPlannerProvider
from app.core import desktop_tools
from app.db.session import Base
from app.models import AutomationAction, TaskState
from app.schemas import StructuredTaskRequest
from app.services.structured_task_service import StructuredTaskService


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def fake_window(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    monkeypatch.setenv("CLM_DESKTOP_AUTOMATION_ADAPTER", "fake")
    listed = desktop_tools.list_windows("notepad")
    return listed.observation["windows"][0]


def run(db: Session, payload: StructuredTaskRequest):
    return StructuredTaskService().create_task(db, payload)


class TwoWindowAdapter(desktop_tools.FakeDesktopAutomationAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.second = desktop_tools._identity("notepad", "notepad.exe", 4243, 1002, "1.2.4", "Phase 6 Fixture 2")

    def list_windows(self, app_id: str | None = None) -> list[desktop_tools.WindowIdentity]:
        if app_id and app_id != "notepad":
            return []
        return [self.target, self.second]


def test_window_identity_binding_and_state_postcondition(db: Session, fake_window: dict[str, object]) -> None:
    state = run(db, StructuredTaskRequest(task_type="DESKTOP_SET_WINDOW_STATE", window=fake_window, window_state="maximize"))
    assert state.state == TaskState.COMPLETED
    assert state.observation["state"] == "maximize"
    assert state.observation["postcondition"]["verified"] is True
    assert db.query(AutomationAction).filter(AutomationAction.task_id == state.id).count() == 1


def test_stale_window_target_rejected(db: Session, fake_window: dict[str, object]) -> None:
    stale = dict(fake_window)
    stale["targetFingerprint"] = "changed"
    result = run(db, StructuredTaskRequest(task_type="DESKTOP_ACTIVATE_WINDOW", window=stale))
    assert result.state == TaskState.BLOCKED


def test_multiple_matching_windows_are_ambiguous() -> None:
    adapter = TwoWindowAdapter()
    resolver = desktop_tools.WindowTargetResolver()
    with pytest.raises(ValueError, match="WINDOW_TARGET_AMBIGUOUS"):
        resolver.resolve(adapter.list_windows("notepad"), None)


def test_handle_reuse_or_fingerprint_change_is_rejected(fake_window: dict[str, object]) -> None:
    adapter = desktop_tools.FakeDesktopAutomationAdapter()
    stale = dict(fake_window)
    stale["windowHandle"] = 9999
    with pytest.raises(ValueError, match="WINDOW_TARGET_CHANGED"):
        desktop_tools.activate_window(stale, adapter=adapter)


def test_control_resolver_rejects_password_ambiguity_and_coordinates(fake_window: dict[str, object]) -> None:
    adapter = desktop_tools.FakeDesktopAutomationAdapter()
    with pytest.raises(ValueError, match="PASSWORD_CONTROL_REJECTED"):
        desktop_tools.read_control_text(fake_window, {"name": "密碼", "controlType": "Edit"}, adapter=adapter)
    with pytest.raises(ValueError, match="UNSAFE_CONTROL_SELECTOR_REJECTED"):
        desktop_tools.invoke_control(fake_window, {"name": "執行", "controlType": "Button", "coordinates": [1, 1]}, adapter=adapter)
    adapter.controls.append({"name": "執行", "controlType": "Button", "automationId": "Other", "enabled": True, "offscreen": False, "isPassword": False, "patterns": ["InvokePattern"]})
    with pytest.raises(ValueError, match="CONTROL_TARGET_AMBIGUOUS"):
        desktop_tools.invoke_control(fake_window, {"name": "執行", "controlType": "Button"}, adapter=adapter)


def test_control_resolver_rejects_unsupported_disabled_and_offscreen(fake_window: dict[str, object]) -> None:
    adapter = desktop_tools.FakeDesktopAutomationAdapter()
    with pytest.raises(ValueError, match="UNSUPPORTED_UIA_PATTERN"):
        desktop_tools.invoke_control(fake_window, {"name": "內容", "controlType": "Edit"}, adapter=adapter)
    adapter.controls[0] = {**adapter.controls[0], "enabled": False}
    with pytest.raises(ValueError, match="CONTROL_NOT_INTERACTABLE"):
        desktop_tools.set_control_text(fake_window, {"name": "內容", "controlType": "Edit"}, "x", adapter=adapter)
    adapter.controls[0] = {**adapter.controls[0], "enabled": True, "offscreen": True}
    with pytest.raises(ValueError, match="CONTROL_NOT_INTERACTABLE"):
        desktop_tools.set_control_text(fake_window, {"name": "內容", "controlType": "Edit"}, "x", adapter=adapter)


def test_generic_profile_rejects_write_actions() -> None:
    generic = desktop_tools._window_observation(
        desktop_tools._identity("generic_readonly", "unknown.exe", 4242, 1001, "1.2.3", "Unknown")
    )
    with pytest.raises(ValueError, match="AUTOMATION_PROFILE_ACTION_REJECTED"):
        desktop_tools.set_control_text(generic, {"name": "內容", "controlType": "Edit"}, "x", adapter=desktop_tools.FakeDesktopAutomationAdapter())


def test_set_text_and_invoke_require_approval(db: Session, fake_window: dict[str, object]) -> None:
    pending = run(db, StructuredTaskRequest(task_type="DESKTOP_SET_CONTROL_TEXT", window=fake_window, control={"name": "內容", "controlType": "Edit"}, text="hello"))
    assert pending.state == TaskState.WAITING_APPROVAL
    approved = StructuredTaskService().decide_approval(db, pending.approval_id or "", True)
    assert approved.state == TaskState.COMPLETED
    assert approved.observation["characters"] == 5

    danger = run(db, StructuredTaskRequest(task_type="DESKTOP_INVOKE_CONTROL", window=fake_window, control={"name": "危險", "controlType": "Button"}))
    assert danger.state == TaskState.WAITING_APPROVAL


def test_read_scroll_close_and_capture_require_approval(db: Session, fake_window: dict[str, object]) -> None:
    read = run(db, StructuredTaskRequest(task_type="DESKTOP_READ_CONTROL_TEXT", window=fake_window, control={"name": "內容", "controlType": "Edit"}))
    scroll = run(db, StructuredTaskRequest(task_type="DESKTOP_SCROLL_CONTROL", window=fake_window, control={"name": "內容", "controlType": "Edit"}, direction="down"))
    close = run(db, StructuredTaskRequest(task_type="DESKTOP_CLOSE_WINDOW", window=fake_window))
    capture = run(db, StructuredTaskRequest(task_type="DESKTOP_CAPTURE_WINDOW", window=fake_window))
    assert read.state == TaskState.WAITING_APPROVAL
    assert scroll.state == TaskState.WAITING_APPROVAL
    assert close.state == TaskState.WAITING_APPROVAL
    assert capture.state == TaskState.WAITING_APPROVAL


def test_capture_window_uses_artifact_id_without_binary_in_observation(fake_window: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLM_SCREEN_ARTIFACT_DIR", str(tmp_path))
    captured = desktop_tools.capture_window(fake_window, adapter=desktop_tools.FakeDesktopAutomationAdapter())
    assert captured.observation["artifactId"]
    assert "artifactPath" not in captured.observation
    assert captured.observation["size"] > 0


def test_close_window_postcondition() -> None:
    adapter = desktop_tools.FakeDesktopAutomationAdapter()
    target = desktop_tools.list_windows("notepad", adapter=adapter).observation["windows"][0]
    closed = desktop_tools.close_window(target, adapter=adapter)
    assert closed.success is True
    assert closed.observation["closed"] is True


def test_capability_policy_and_planner_desktop_guards() -> None:
    policy = CapabilityPolicy()
    assert policy.decision_for("desktop.window.list").decision == CapabilityDecision.AUTO
    assert policy.decision_for("desktop.control.invoke").decision == CapabilityDecision.APPROVAL_REQUIRED
    assert policy.decision_for("execution.arbitrary").decision == CapabilityDecision.BLOCKED

    with pytest.raises(ValueError, match="UNSAFE_DESKTOP_TARGET_ARGUMENT"):
        PlanValidator().validate(
            AgentPlan(
                goal="bad",
                needsClarification=False,
                steps=[PlanStepSpec(tool="desktop.activate_window", arguments={"pid": 1}, reason="bad")],
            ),
            workspace_id=None,
        )

    planner = DeterministicPlannerProvider()
    plan = planner.create_plan(PlanContext(request="開啟記事本"))
    assert plan.steps[0].tool == "host.launch_registered_app"
    windows = planner.create_plan(PlanContext(request="列出目前視窗"))
    assert windows.steps[0].tool == "desktop.list_windows"


def test_production_adapter_is_not_fake_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLM_DESKTOP_AUTOMATION_ADAPTER", raising=False)
    adapter = desktop_tools.adapter_from_environment()
    assert not isinstance(adapter, desktop_tools.FakeDesktopAutomationAdapter)
