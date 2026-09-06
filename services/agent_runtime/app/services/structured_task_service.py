from __future__ import annotations

import json
import shutil
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.agent.capability_policy import CapabilityDecision, CapabilityPolicy
from app.core import desktop_tools, file_tools, host_tools
from app.core.audit import redact
from app.core.file_tools import sha256_file
from app.core.path_policy import WorkspacePathPolicy
from app.core.tool_sdk import RiskLevel, ToolResult, argument_hash
from app.engineering.command_runner import EngineeringCommandRunner
from app.models import Action, Approval, Artifact, AuditEvent, AutomationAction, BatchManifest, BatchManifestItem, Observation, RecoveryItem, Task, TaskState, TaskStep, UndoRecord, WorkspaceGrant
from app.schemas import StructuredTaskRequest, TaskResponse, WorkspaceGrantCreate


WORKSPACE_READ_TASKS = {"LIST_DIRECTORY", "WALK", "DIRECTORY_SUMMARY", "FIND_LARGE_FILES", "LIST_BY_EXTENSION", "COMPARE_FILES", "PREVIEW_BATCH", "STAT_PATH", "READ_TEXT", "SEARCH_FILES", "HASH_FILE", "FIND_DUPLICATES"}
HOST_READ_TASKS = {"SYSTEM_INFO", "LIST_PROCESSES", "LIST_REGISTERED_APPS"}
DESKTOP_AUTO_TASKS = {"DESKTOP_LIST_WINDOWS", "DESKTOP_WAIT_FOR_WINDOW", "DESKTOP_ACTIVATE_WINDOW", "DESKTOP_GET_WINDOW_STATE", "DESKTOP_SET_WINDOW_STATE", "DESKTOP_INSPECT_CONTROLS"}
DESKTOP_APPROVAL_TASKS = {"DESKTOP_READ_CONTROL_TEXT", "DESKTOP_INVOKE_CONTROL", "DESKTOP_SET_CONTROL_TEXT", "DESKTOP_SELECT_ITEM", "DESKTOP_SCROLL_CONTROL", "DESKTOP_CLOSE_WINDOW", "DESKTOP_CAPTURE_WINDOW"}
READ_TASKS = WORKSPACE_READ_TASKS | HOST_READ_TASKS
WRITE_TASKS = {"CREATE_DIRECTORY", "WRITE_NEW_TEXT", "APPEND_TEXT", "COPY_FILE", "MOVE_FILE", "RENAME_FILE", "BATCH_COPY", "BATCH_MOVE", "BATCH_RENAME", "CREATE_ZIP", "EXTRACT_ZIP", "MOVE_TO_RECOVERY_BIN", "RESTORE_FROM_RECOVERY_BIN", "OPEN_WORKSPACE_FILE", "OPEN_WORKSPACE_FOLDER", "CLIPBOARD_WRITE_TEXT"} | DESKTOP_AUTO_TASKS
HIGH_RISK_TASKS = {"OVERWRITE_TEXT", "EXTRACT_ZIP", "MOVE_TO_RECOVERY_BIN", "CLIPBOARD_READ_TEXT", "TERMINATE_PROCESS", "LAUNCH_REGISTERED_APP", "ENGINEERING_RUN"} | DESKTOP_APPROVAL_TASKS
BATCH_TASKS = {"BATCH_COPY", "BATCH_MOVE", "BATCH_RENAME"}
BATCH_APPROVAL_ITEM_THRESHOLD = 10
WORKSPACE_BOUND_TASKS = WORKSPACE_READ_TASKS | {
    "CREATE_DIRECTORY",
    "WRITE_NEW_TEXT",
    "APPEND_TEXT",
    "COPY_FILE",
    "MOVE_FILE",
    "RENAME_FILE",
    "BATCH_COPY",
    "BATCH_MOVE",
    "BATCH_RENAME",
    "CREATE_ZIP",
    "EXTRACT_ZIP",
    "MOVE_TO_RECOVERY_BIN",
    "RESTORE_FROM_RECOVERY_BIN",
    "OPEN_WORKSPACE_FILE",
    "OPEN_WORKSPACE_FOLDER",
    "OVERWRITE_TEXT",
    "ENGINEERING_RUN",
}


class StructuredTaskService:
    def create_workspace(self, db: Session, payload: WorkspaceGrantCreate) -> WorkspaceGrant:
        root = Path(payload.root_path).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("WORKSPACE_NOT_DIRECTORY")
        grant = WorkspaceGrant(
            display_name=payload.display_name or root.name,
            root_path=str(root),
            enabled=True,
            permission_profile=payload.permission_profile,
        )
        db.add(grant)
        self.audit(db, "workspace.created", {"workspace_id": grant.id, "root_path": grant.root_path})
        db.commit()
        db.refresh(grant)
        return grant

    def list_workspaces(self, db: Session) -> list[WorkspaceGrant]:
        grants = list(db.scalars(select(WorkspaceGrant).order_by(WorkspaceGrant.created_at.desc())))
        changed = False
        active: list[WorkspaceGrant] = []
        for grant in grants:
            if not grant.enabled:
                continue
            try:
                root = Path(grant.root_path).resolve(strict=True)
            except OSError:
                grant.enabled = False
                changed = True
                continue
            if not root.is_dir():
                grant.enabled = False
                changed = True
                continue
            grant.root_path = str(root)
            active.append(grant)
        if changed:
            db.commit()
        return active

    def create_task(self, db: Session, request: StructuredTaskRequest) -> TaskResponse:
        task = Task(title=request.task_type, state=TaskState.ANALYZING)
        db.add(task)
        db.flush()
        step = TaskStep(task_id=task.id, title=request.task_type, state=TaskState.RUNNING, sort_order=1)
        db.add(step)
        action: Action | None = None
        try:
            normalized = self.normalize_arguments(db, request)
            tool_name = self.tool_name_for(request.task_type)
            task.workspace_id = normalized.get("workspace_id")
            action = Action(
                task_id=task.id,
                tool_name=tool_name,
                arguments_hash=argument_hash(normalized),
                risk_level=self.risk_for(request.task_type),
                status="PLANNED",
                workspace_id=normalized.get("workspace_id"),
                target_path=normalized.get("destination") or normalized.get("path"),
            )
            db.add(action)
            db.flush()
            self.audit(db, "task.created", {"task_id": task.id, "tool_name": tool_name, "arguments": normalized})

            self.enforce_capability(request.task_type)
            if request.task_type in BATCH_TASKS and len(normalized.get("items") or []) > BATCH_APPROVAL_ITEM_THRESHOLD:
                manifest = self.create_batch_manifest(db, task, normalized, request.task_type, list(normalized.get("items") or []))
                normalized["manifest_id"] = manifest.id
                action.arguments_hash = argument_hash(normalized)
                action.risk_level = RiskLevel.HIGH_RISK.value
                return self.require_overwrite_approval(db, task, step, action, normalized)
            if request.task_type in HIGH_RISK_TASKS:
                return self.require_overwrite_approval(db, task, step, action, normalized)
            result = self.execute_normalized(db, task, action, request.task_type, normalized)
            return self.complete_from_result(db, task, step, action, result)
        except Exception as exc:
            task.state = self.failure_state(exc)
            if action is not None:
                action.status = task.state.value
            step.state = task.state
            self.audit(db, "task.failed" if task.state == TaskState.FAILED else "task.blocked", {"task_id": task.id, "error": str(exc)})
            db.commit()
            return TaskResponse(id=task.id, title=task.title, state=task.state, summary=self.safe_failure_message(exc))

    def decide_approval(self, db: Session, approval_id: str, approve: bool) -> TaskResponse:
        approval = db.get(Approval, approval_id)
        if approval is None:
            raise ValueError("APPROVAL_NOT_FOUND")
        if approval.status != "PENDING":
            raise ValueError("APPROVAL_ALREADY_DECIDED")
        task = db.get(Task, approval.task_id)
        action = db.get(Action, approval.action_id)
        if task is None or action is None or task.state in {TaskState.CANCELLED, TaskState.FAILED}:
            raise ValueError("TASK_NOT_ACTIVE")
        approval.decided_at = datetime.now(UTC)
        if not approve:
            approval.status = "REJECTED"
            action.status = "REJECTED"
            task.state = TaskState.BLOCKED
            self.audit(db, "approval.rejected", {"approval_id": approval.id, "task_id": task.id})
            db.commit()
            return TaskResponse(id=task.id, title=task.title, state=task.state, approval_id=approval.id, summary="Approval rejected.")
        if approval.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            approval.status = "EXPIRED"
            action.status = "BLOCKED"
            task.state = TaskState.BLOCKED
            db.commit()
            return TaskResponse(id=task.id, title=task.title, state=task.state, approval_id=approval.id, summary="Approval expired.")
        if approval.argument_hash != action.arguments_hash:
            approval.status = "TAMPERED"
            action.status = "BLOCKED"
            task.state = TaskState.BLOCKED
            db.commit()
            return TaskResponse(id=task.id, title=task.title, state=task.state, approval_id=approval.id, summary="Approval arguments changed.")
        approval.approved = True
        approval.status = "APPROVED"
        task.state = TaskState.RUNNING
        try:
            task_type = str(approval.normalized_arguments.get("task_type") or "OVERWRITE_TEXT")
            result = self.execute_overwrite(db, task, action, approval.normalized_arguments) if task_type == "OVERWRITE_TEXT" else self.execute_normalized(db, task, action, task_type, approval.normalized_arguments)
        except Exception as exc:
            approval.status = "INVALIDATED"
            action.status = "BLOCKED"
            task.state = TaskState.BLOCKED
            self.audit(db, "approval.invalidated", {"approval_id": approval.id, "error": str(exc)})
            db.commit()
            return TaskResponse(id=task.id, title=task.title, state=task.state, approval_id=approval.id, summary=str(exc))
        step = db.scalar(select(TaskStep).where(TaskStep.task_id == task.id).limit(1))
        if step is None:
            step = TaskStep(task_id=task.id, title="OVERWRITE_TEXT", state=TaskState.RUNNING, sort_order=1)
            db.add(step)
        return self.complete_from_result(db, task, step, action, result, approval_id=approval.id)

    def undo(self, db: Session, undo_record_id: str) -> TaskResponse:
        undo = db.get(UndoRecord, undo_record_id)
        if undo is None:
            raise ValueError("UNDO_NOT_FOUND")
        task = Task(title="UNDO_ACTION", state=TaskState.RUNNING)
        db.add(task)
        db.flush()
        action = Action(task_id=task.id, tool_name="undo.apply", arguments_hash=argument_hash({"undo_record_id": undo_record_id}), risk_level="WRITE", status="RUNNING")
        db.add(action)
        if undo.status == "APPLIED" or undo.applied:
            task.state = TaskState.BLOCKED
            action.status = "BLOCKED"
            self.audit(db, "undo.duplicate_blocked", {"undo_record_id": undo.id})
            db.commit()
            return TaskResponse(id=task.id, title=task.title, state=task.state, summary="Undo already applied.")
        try:
            self.apply_undo(undo)
        except Exception as exc:
            task.state = TaskState.BLOCKED
            action.status = "BLOCKED"
            self.audit(db, "undo.conflict", {"undo_record_id": undo.id, "error": str(exc)})
            db.commit()
            return TaskResponse(id=task.id, title=task.title, state=task.state, summary=str(exc))
        undo.status = "APPLIED"
        undo.applied = True
        undo.applied_at = datetime.now(UTC)
        task.state = TaskState.COMPLETED
        action.status = "COMPLETED"
        self.audit(db, "undo.applied", {"undo_record_id": undo.id, "task_id": task.id})
        db.commit()
        return TaskResponse(id=task.id, title=task.title, state=task.state, summary="Undo applied.")

    def normalize_arguments(self, db: Session, request: StructuredTaskRequest) -> dict[str, Any]:
        data = request.model_dump(exclude_none=True)
        if request.task_type in WORKSPACE_BOUND_TASKS:
            grant = self.get_workspace(db, request.workspace_id)
            data["workspace_root"] = grant.root_path
            data["workspace_id"] = grant.id
        return data

    def get_workspace(self, db: Session, workspace_id: str | None) -> WorkspaceGrant:
        if not workspace_id:
            raise ValueError("WORKSPACE_REQUIRED")
        grant = db.get(WorkspaceGrant, workspace_id)
        if grant is None or not grant.enabled:
            raise ValueError("WORKSPACE_NOT_FOUND")
        try:
            root = Path(grant.root_path).resolve(strict=True)
        except OSError as exc:
            raise ValueError("WORKSPACE_GRANT_INVALID") from exc
        if not root.is_dir():
            raise ValueError("WORKSPACE_GRANT_INVALID")
        grant.root_path = str(root)
        grant.last_used_at = datetime.now(UTC)
        return grant

    def tool_name_for(self, task_type: str) -> str:
        return {
            "LIST_DIRECTORY": "filesystem.list_directory",
            "WALK": "filesystem.walk",
            "DIRECTORY_SUMMARY": "filesystem.directory_summary",
            "FIND_LARGE_FILES": "filesystem.find_large_files",
            "LIST_BY_EXTENSION": "filesystem.list_by_extension",
            "COMPARE_FILES": "filesystem.compare_files",
            "PREVIEW_BATCH": "filesystem.preview_batch",
            "STAT_PATH": "filesystem.stat",
            "READ_TEXT": "filesystem.read_text",
            "SEARCH_FILES": "filesystem.search",
            "HASH_FILE": "filesystem.hash_file",
            "FIND_DUPLICATES": "filesystem.find_duplicates",
            "CREATE_DIRECTORY": "filesystem.create_directory",
            "WRITE_NEW_TEXT": "filesystem.write_new_text",
            "APPEND_TEXT": "filesystem.append_text",
            "COPY_FILE": "filesystem.copy",
            "MOVE_FILE": "filesystem.move",
            "RENAME_FILE": "filesystem.rename",
            "BATCH_COPY": "filesystem.batch_copy",
            "BATCH_MOVE": "filesystem.batch_move",
            "BATCH_RENAME": "filesystem.batch_rename",
            "CREATE_ZIP": "filesystem.create_zip",
            "EXTRACT_ZIP": "filesystem.extract_zip",
            "MOVE_TO_RECOVERY_BIN": "filesystem.move_to_recovery_bin",
            "RESTORE_FROM_RECOVERY_BIN": "filesystem.restore_from_recovery_bin",
            "OVERWRITE_TEXT": "filesystem.overwrite_text",
            "SYSTEM_INFO": "host.system_info",
            "LIST_PROCESSES": "host.list_processes",
            "LIST_REGISTERED_APPS": "host.list_registered_apps",
            "LAUNCH_REGISTERED_APP": "host.launch_registered_app",
            "OPEN_WORKSPACE_FILE": "host.open_workspace_file",
            "OPEN_WORKSPACE_FOLDER": "host.open_workspace_folder",
            "CLIPBOARD_READ_TEXT": "host.clipboard_read_text",
            "CLIPBOARD_WRITE_TEXT": "host.clipboard_write_text",
            "TERMINATE_PROCESS": "host.terminate_process",
            "DESKTOP_LIST_WINDOWS": "desktop.list_windows",
            "DESKTOP_WAIT_FOR_WINDOW": "desktop.wait_for_window",
            "DESKTOP_ACTIVATE_WINDOW": "desktop.activate_window",
            "DESKTOP_GET_WINDOW_STATE": "desktop.get_window_state",
            "DESKTOP_SET_WINDOW_STATE": "desktop.set_window_state",
            "DESKTOP_INSPECT_CONTROLS": "desktop.inspect_controls",
            "DESKTOP_READ_CONTROL_TEXT": "desktop.read_control_text",
            "DESKTOP_INVOKE_CONTROL": "desktop.invoke_control",
            "DESKTOP_SET_CONTROL_TEXT": "desktop.set_control_text",
            "DESKTOP_SELECT_ITEM": "desktop.select_item",
            "DESKTOP_SCROLL_CONTROL": "desktop.scroll_control",
            "DESKTOP_CLOSE_WINDOW": "desktop.close_window",
            "DESKTOP_CAPTURE_WINDOW": "desktop.capture_window",
            "ENGINEERING_RUN": "engineering.command.run",
            "UNDO_ACTION": "undo.apply",
        }[task_type]

    def risk_for(self, task_type: str) -> str:
        if task_type in HIGH_RISK_TASKS:
            return RiskLevel.HIGH_RISK.value
        if task_type in WRITE_TASKS or task_type in {"LAUNCH_REGISTERED_APP", "UNDO_ACTION"}:
            return RiskLevel.WRITE.value
        return RiskLevel.READ.value

    def capability_for(self, task_type: str) -> str:
        if task_type in WORKSPACE_READ_TASKS:
            return "workspace.read"
        if task_type in {"CREATE_ZIP"}:
            return "archive.create"
        if task_type == "EXTRACT_ZIP":
            return "archive.extract"
        if task_type == "MOVE_TO_RECOVERY_BIN":
            return "recovery_bin.write"
        if task_type == "RESTORE_FROM_RECOVERY_BIN":
            return "recovery_bin.restore"
        if task_type == "OPEN_WORKSPACE_FILE":
            return "host.open_file"
        if task_type == "OPEN_WORKSPACE_FOLDER":
            return "host.open_folder"
        if task_type == "CLIPBOARD_READ_TEXT":
            return "clipboard.read"
        if task_type == "CLIPBOARD_WRITE_TEXT":
            return "clipboard.write"
        if task_type == "TERMINATE_PROCESS":
            return "process.terminate"
        if task_type == "DESKTOP_LIST_WINDOWS":
            return "desktop.window.list"
        if task_type in {"DESKTOP_WAIT_FOR_WINDOW", "DESKTOP_ACTIVATE_WINDOW"}:
            return "desktop.window.activate"
        if task_type in {"DESKTOP_GET_WINDOW_STATE", "DESKTOP_SET_WINDOW_STATE"}:
            return "desktop.window.state"
        if task_type == "DESKTOP_INSPECT_CONTROLS":
            return "desktop.control.inspect"
        if task_type == "DESKTOP_READ_CONTROL_TEXT":
            return "desktop.control.read"
        if task_type == "DESKTOP_INVOKE_CONTROL":
            return "desktop.control.invoke"
        if task_type in {"DESKTOP_SET_CONTROL_TEXT", "DESKTOP_SELECT_ITEM", "DESKTOP_SCROLL_CONTROL"}:
            return "desktop.control.write"
        if task_type == "DESKTOP_CLOSE_WINDOW":
            return "desktop.window.close"
        if task_type == "DESKTOP_CAPTURE_WINDOW":
            return "desktop.screen.capture"
        if task_type == "ENGINEERING_RUN":
            return "engineering.command.run"
        if task_type in WRITE_TASKS:
            return "workspace.write"
        return "workspace.read"

    def enforce_capability(self, task_type: str) -> None:
        rule = CapabilityPolicy().decision_for(self.capability_for(task_type))
        if rule.decision == CapabilityDecision.BLOCKED:
            raise ValueError("CAPABILITY_BLOCKED")

    def execute_normalized(self, db: Session, task: Task, action: Action, task_type: str, args: dict[str, Any]) -> ToolResult:
        root = args.get("workspace_root", "")
        path = args.get("path") or "."
        destination = args.get("destination")
        content = args.get("content") or ""
        text = args.get("text") or content
        if task_type == "LIST_DIRECTORY":
            return file_tools.list_directory(root, path)
        if task_type == "WALK":
            return file_tools.walk(root, path, max_depth=int(args.get("max_depth") or 5), limit=int(args.get("limit") or 100))
        if task_type == "DIRECTORY_SUMMARY":
            return file_tools.directory_summary(root, path, max_depth=int(args.get("max_depth") or 5), limit=int(args.get("limit") or 1000))
        if task_type == "FIND_LARGE_FILES":
            return file_tools.find_large_files(root, path, min_size_bytes=int(args.get("min_size_bytes") or 100 * 1024 * 1024), max_depth=int(args.get("max_depth") or 5), limit=int(args.get("limit") or 100))
        if task_type == "LIST_BY_EXTENSION":
            return file_tools.list_by_extension(root, path, extension=args.get("extension") or "", max_depth=int(args.get("max_depth") or 5), limit=int(args.get("limit") or 100))
        if task_type == "COMPARE_FILES":
            return file_tools.compare_files(root, path, args.get("other_path") or args.get("destination") or "")
        if task_type == "PREVIEW_BATCH":
            return file_tools.preview_batch(root, list(args.get("items") or []), operation=args.get("operation") or "batch")
        if task_type == "STAT_PATH":
            return file_tools.stat_path(root, path)
        if task_type == "READ_TEXT":
            return file_tools.read_text(root, path)
        if task_type == "SEARCH_FILES":
            return file_tools.search(root, path, args.get("query") or args.get("content") or "", search_content=bool(args.get("search_content")), max_results=50, max_file_bytes=file_tools.MAX_READ_BYTES, max_depth=5)
        if task_type == "HASH_FILE":
            return file_tools.hash_file(root, path)
        if task_type == "FIND_DUPLICATES":
            return file_tools.find_duplicates(root, path)
        if task_type == "CREATE_DIRECTORY":
            result = file_tools.create_directory(root, path)
            if result.side_effect and self.postcondition_verified(result, action.tool_name):
                target = WorkspacePathPolicy(root).resolve_existing(path).absolute_path
                self.create_undo(db, task, action, "CREATE_DIRECTORY", None, str(target), {}, result.observation)
            return result
        if task_type == "WRITE_NEW_TEXT":
            result = file_tools.write_new_text(root, path, content)
            if self.postcondition_verified(result, action.tool_name):
                target = WorkspacePathPolicy(root).resolve_existing(path).absolute_path
                self.create_undo(db, task, action, "WRITE_NEW_TEXT", None, str(target), {}, result.observation)
            return result
        if task_type == "APPEND_TEXT":
            result = file_tools.append_text(root, path, text)
            if self.postcondition_verified(result, action.tool_name):
                target = WorkspacePathPolicy(root).resolve_existing(path).absolute_path
                self.create_undo(db, task, action, "APPEND_TEXT", str(target), str(target), {"sha256": result.observation.get("previous_sha256"), "size": result.observation.get("previous_size")}, {"sha256": result.observation.get("sha256")})
            return result
        if task_type in {"COPY_FILE", "MOVE_FILE", "RENAME_FILE"}:
            if not destination:
                raise ValueError("DESTINATION_REQUIRED")
            result = file_tools.copy_file(root, path, destination) if task_type == "COPY_FILE" else file_tools.move_file(root, path, destination)
            if self.postcondition_verified(result, action.tool_name):
                policy = WorkspacePathPolicy(root)
                source_abs = policy.resolve_new_child(path).absolute_path if task_type != "COPY_FILE" else policy.resolve_existing(path).absolute_path
                dest_abs = policy.resolve_existing(destination).absolute_path
                self.create_undo(db, task, action, task_type, str(source_abs), str(dest_abs), {}, result.observation)
            return result
        if task_type in {"BATCH_COPY", "BATCH_MOVE", "BATCH_RENAME"}:
            items = list(args.get("items") or [])
            manifest = db.get(BatchManifest, args["manifest_id"]) if args.get("manifest_id") else None
            if manifest is None:
                manifest = self.create_batch_manifest(db, task, args, task_type, items)
            self.validate_batch_manifest(db, manifest, args)
            if task_type == "BATCH_COPY":
                result = file_tools.batch_copy(root, items)
                operation = "COPY_FILE"
            elif task_type == "BATCH_MOVE":
                result = file_tools.batch_move(root, items)
                operation = "MOVE_FILE"
            else:
                result = file_tools.batch_rename(root, items)
                operation = "RENAME_FILE"
            for item in result.observation.get("successes", []):
                if isinstance(item, dict):
                    item_action = self.create_batch_item_action(db, task, action, item)
                    policy = WorkspacePathPolicy(root)
                    source_abs = policy.root / str(item.get("source"))
                    destination_abs = policy.resolve_existing(str(item.get("destination"))).absolute_path
                    self.create_undo(db, task, item_action, operation, str(source_abs), str(destination_abs), {}, {"sha256": item.get("sha256")})
            manifest.status = "COMPLETED" if not result.observation.get("failures") else "PARTIAL"
            self.update_batch_manifest_items(db, manifest, result.observation)
            result.observation["manifest_id"] = manifest.id
            result.observation["manifest_hash"] = manifest.manifest_hash
            return result
        if task_type == "CREATE_ZIP":
            result = file_tools.create_zip(root, path, [str(item.get("source") or item.get("path") or item) for item in list(args.get("items") or [])])
            if self.postcondition_verified(result, action.tool_name):
                target = WorkspacePathPolicy(root).resolve_existing(path).absolute_path
                self.create_undo(db, task, action, "WRITE_NEW_TEXT", None, str(target), {}, {"sha256": result.observation.get("postcondition", {}).get("sha256")})
            return result
        if task_type == "EXTRACT_ZIP":
            result = file_tools.extract_zip(root, path, destination or "")
            for item in result.observation.get("files", []):
                if isinstance(item, dict):
                    self.create_undo(db, task, action, "WRITE_NEW_TEXT", None, str(WorkspacePathPolicy(root).resolve_existing(str(item.get("path"))).absolute_path), {}, {"sha256": item.get("sha256")})
            return result
        if task_type == "MOVE_TO_RECOVERY_BIN":
            recovery_id = args.get("recovery_item_id") or str(uuid.uuid4())
            recovery_root = str(get_settings().data_dir / "recovery_bin" / args["workspace_id"])
            result = file_tools.move_to_recovery_bin(root, path, recovery_root, recovery_id)
            self.create_recovery_item(db, args["workspace_id"], path, recovery_root, recovery_id, result.observation)
            original = str(WorkspacePathPolicy(root).root / path)
            recovery_path = str(Path(recovery_root) / recovery_id)
            self.create_undo(db, task, action, "MOVE_FILE", original, recovery_path, {}, {"sha256": result.observation.get("sha256")})
            return result
        if task_type == "RESTORE_FROM_RECOVERY_BIN":
            recovery_id = args.get("recovery_item_id") or ""
            recovery_root = str(get_settings().data_dir / "recovery_bin" / args["workspace_id"])
            result = file_tools.restore_from_recovery_bin(root, path, recovery_root, recovery_id)
            item = db.get(RecoveryItem, recovery_id)
            if item:
                item.status = "RESTORED"
                item.restored_at = datetime.now(UTC)
            restored = str(WorkspacePathPolicy(root).resolve_existing(path).absolute_path)
            recovery_path = str(Path(recovery_root) / recovery_id)
            self.create_undo(db, task, action, "MOVE_FILE", recovery_path, restored, {}, {"sha256": result.observation.get("sha256")})
            return result
        if task_type == "SYSTEM_INFO":
            return host_tools.system_info()
        if task_type == "LIST_PROCESSES":
            return host_tools.list_processes()
        if task_type == "LIST_REGISTERED_APPS":
            return host_tools.list_registered_apps()
        if task_type == "LAUNCH_REGISTERED_APP":
            return host_tools.launch_registered_app(args.get("app_id") or "")
        if task_type == "OPEN_WORKSPACE_FILE":
            return host_tools.open_workspace_file(root, path)
        if task_type == "OPEN_WORKSPACE_FOLDER":
            return host_tools.open_workspace_folder(root, path)
        if task_type == "CLIPBOARD_READ_TEXT":
            return host_tools.clipboard_read_text()
        if task_type == "CLIPBOARD_WRITE_TEXT":
            return host_tools.clipboard_write_text(text)
        if task_type == "TERMINATE_PROCESS":
            return host_tools.terminate_process(int(args.get("process_id") or 0), expected_name=args.get("process_name"))
        if task_type == "ENGINEERING_RUN":
            return EngineeringCommandRunner().run(
                root,
                str(args.get("command_id") or ""),
                str(args.get("command_fingerprint") or ""),
                timeout_seconds=int(args.get("timeout_seconds") or 60),
            )
        if task_type.startswith("DESKTOP_"):
            result = self.execute_desktop_task(task_type, args)
            self.record_automation_action(db, task, action, task_type, result)
            if task_type == "DESKTOP_SET_WINDOW_STATE" and self.postcondition_verified(result, action.tool_name):
                self.create_undo(db, task, action, "DESKTOP_WINDOW_STATE", None, None, {"state": "restore"}, {"state": args.get("window_state")})
            return result
        raise ValueError("TASK_TYPE_NOT_IMPLEMENTED")

    def execute_desktop_task(self, task_type: str, args: dict[str, Any]) -> ToolResult:
        target = dict(args.get("window") or {})
        control = dict(args.get("control") or {})
        if task_type == "DESKTOP_LIST_WINDOWS":
            return desktop_tools.list_windows(args.get("app"))
        if task_type == "DESKTOP_WAIT_FOR_WINDOW":
            return desktop_tools.wait_for_window(args.get("app") or "", timeout_seconds=int(args.get("timeout_seconds") or 10))
        if task_type == "DESKTOP_ACTIVATE_WINDOW":
            return desktop_tools.activate_window(target)
        if task_type == "DESKTOP_GET_WINDOW_STATE":
            return desktop_tools.get_window_state(target)
        if task_type == "DESKTOP_SET_WINDOW_STATE":
            return desktop_tools.set_window_state(target, args.get("window_state") or "restore")
        if task_type == "DESKTOP_INSPECT_CONTROLS":
            return desktop_tools.inspect_controls(target)
        if task_type == "DESKTOP_READ_CONTROL_TEXT":
            return desktop_tools.read_control_text(target, control)
        if task_type == "DESKTOP_INVOKE_CONTROL":
            return desktop_tools.invoke_control(target, control, approved=True)
        if task_type == "DESKTOP_SET_CONTROL_TEXT":
            return desktop_tools.set_control_text(target, control, args.get("text") or "")
        if task_type == "DESKTOP_SELECT_ITEM":
            return desktop_tools.select_item(target, control, args.get("item_name") or "")
        if task_type == "DESKTOP_SCROLL_CONTROL":
            return desktop_tools.scroll_control(target, control, args.get("direction") or "down")
        if task_type == "DESKTOP_CLOSE_WINDOW":
            return desktop_tools.close_window(target)
        if task_type == "DESKTOP_CAPTURE_WINDOW":
            return desktop_tools.capture_window(target)
        raise ValueError("TASK_TYPE_NOT_IMPLEMENTED")

    def require_overwrite_approval(self, db: Session, task: Task, step: TaskStep, action: Action, args: dict[str, Any]) -> TaskResponse:
        if args.get("task_type") == "OVERWRITE_TEXT":
            root = args["workspace_root"]
            path = args.get("path") or ""
            target = WorkspacePathPolicy(root).resolve_existing(path).absolute_path
            args["expected_sha256"] = sha256_file(target)
        elif args.get("task_type") == "ENGINEERING_RUN":
            prepared = EngineeringCommandRunner().prepare(
                args["workspace_root"],
                str(args.get("command_id") or ""),
            )
            args["command_fingerprint"] = prepared.fingerprint
            args["command_display"] = prepared.displayCommand
        action.arguments_hash = argument_hash(args)
        approval = Approval(
            task_id=task.id,
            action_id=action.id,
            tool_name=action.tool_name,
            normalized_arguments=args,
            exact_tool=action.tool_name,
            exact_arguments=args,
            argument_hash=action.arguments_hash,
            risk_level=RiskLevel.HIGH_RISK.value,
            working_directory=args.get("workspace_id") or "host",
            risk_reason=f"{action.tool_name} requires exact approval.",
            status="PENDING",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        task.state = TaskState.WAITING_APPROVAL
        step.state = TaskState.WAITING_APPROVAL
        action.status = "WAITING_APPROVAL"
        db.add(approval)
        self.audit(db, "approval.required", {"approval_id": approval.id, "arguments": args})
        db.commit()
        return TaskResponse(id=task.id, title=task.title, state=task.state, approval_id=approval.id, summary="Approval required.")

    def execute_overwrite(self, db: Session, task: Task, action: Action, args: dict[str, Any]) -> ToolResult:
        backup_dir = get_settings().data_dir / "backups" / task.id
        result, backup, new_hash = file_tools.overwrite_text_with_backup(args["workspace_root"], args["path"], args.get("content") or "", args["expected_sha256"], backup_dir)
        target = WorkspacePathPolicy(args["workspace_root"]).resolve_existing(args["path"]).absolute_path
        if self.postcondition_verified(result, action.tool_name):
            self.create_undo(db, task, action, "OVERWRITE_TEXT", str(target), str(target), {"sha256": args["expected_sha256"]}, {"sha256": new_hash}, backup_path=str(backup))
        return result

    def complete_from_result(self, db: Session, task: Task, step: TaskStep, action: Action, result: ToolResult, approval_id: str | None = None) -> TaskResponse:
        verifier_ok = result.success and bool(result.evidence) and self.postcondition_verified(result, action.tool_name)
        task.state = TaskState.COMPLETED if verifier_ok else TaskState.FAILED
        step.state = task.state
        action.status = task.state.value
        db.add(
            Observation(
                action_id=action.id,
                task_id=task.id,
                workspace_id=action.workspace_id,
                summary=result.summary,
                evidence=result.model_dump(mode="json"),
            )
        )
        self.audit(db, "task.completed" if verifier_ok else "task.failed", {"task_id": task.id, "result": result.model_dump(mode="json")})
        db.commit()
        undo = db.scalar(select(UndoRecord).where(UndoRecord.action_id == action.id).order_by(UndoRecord.created_at.desc()).limit(1))
        return TaskResponse(
            id=task.id,
            title=task.title,
            state=task.state,
            summary=result.summary,
            observation=result.observation,
            approval_id=approval_id,
            undo_record_id=undo.id if undo else None,
        )

    def postcondition_verified(self, result: ToolResult, tool_name: str | None = None) -> bool:
        if tool_name not in {
            "filesystem.create_directory",
            "filesystem.write_new_text",
            "filesystem.append_text",
            "filesystem.copy",
            "filesystem.move",
            "filesystem.rename",
            "filesystem.batch_copy",
            "filesystem.batch_move",
            "filesystem.batch_rename",
            "filesystem.create_zip",
            "filesystem.extract_zip",
            "filesystem.move_to_recovery_bin",
            "filesystem.restore_from_recovery_bin",
            "filesystem.overwrite_text",
            "desktop.activate_window",
            "desktop.set_window_state",
            "desktop.invoke_control",
            "desktop.set_control_text",
            "desktop.select_item",
            "desktop.scroll_control",
            "desktop.close_window",
            "desktop.capture_window",
        }:
            return True
        if not result.side_effect:
            return True
        postcondition = result.observation.get("postcondition")
        return isinstance(postcondition, dict) and postcondition.get("verified") is True

    def failure_state(self, exc: Exception) -> TaskState:
        code = str(exc)
        if code in {"WORKSPACE_NOT_FOUND", "WORKSPACE_GRANT_INVALID", "WORKSPACE_REQUIRED", "WORKSPACE_NOT_DIRECTORY"}:
            return TaskState.FAILED
        if code.startswith("POSTCONDITION_"):
            return TaskState.FAILED
        return TaskState.BLOCKED

    def safe_failure_message(self, exc: Exception) -> str:
        code = str(exc)
        if code in {"WORKSPACE_NOT_FOUND", "WORKSPACE_GRANT_INVALID", "WORKSPACE_REQUIRED", "WORKSPACE_NOT_DIRECTORY"}:
            return "目前工作區授權已失效，請重新選擇工作資料夾。"
        if code.startswith("POSTCONDITION_"):
            return "檔案系統變更未通過完成驗證，任務已停止。"
        return "任務未完成，請確認工作區與檔案狀態後再試。"

    def create_undo(self, db: Session, task: Task, action: Action, operation: str, source: str | None, destination: str | None, precondition: dict[str, Any], postcondition: dict[str, Any], backup_path: str | None = None) -> UndoRecord:
        undo = UndoRecord(
            task_id=task.id,
            action_id=action.id,
            operation=operation,
            undo_type=operation,
            source=source,
            destination=destination,
            precondition=precondition,
            postcondition=postcondition,
            payload={"source": source, "destination": destination},
            backup_path=backup_path,
            status="PENDING",
            applied=False,
        )
        db.add(undo)
        return undo

    def create_batch_manifest(self, db: Session, task: Task, args: dict[str, Any], operation: str, items: list[dict[str, Any]]) -> BatchManifest:
        policy = WorkspacePathPolicy(args["workspace_root"])
        prepared = []
        for item in items:
            source_text = str(item.get("source") or item.get("path") or "")
            destination_text = str(item.get("destination") or "")
            try:
                source = policy.resolve_existing(source_text).absolute_path
                prepared.append(
                    {
                        "source": source_text,
                        "destination": destination_text,
                        "sourceHash": sha256_file(source) if source.is_file() else None,
                        "size": source.stat().st_size,
                        "status": "PENDING",
                        "error": None,
                    }
                )
            except Exception as exc:
                prepared.append(
                    {
                        "source": source_text,
                        "destination": destination_text,
                        "sourceHash": None,
                        "size": 0,
                        "status": "FAILED",
                        "error": str(exc),
                    }
                )
        manifest_hash = argument_hash({"workspaceId": args["workspace_id"], "operation": operation, "items": prepared})
        manifest = BatchManifest(
            task_id=task.id,
            workspace_id=args["workspace_id"],
            operation=operation,
            arguments_hash=argument_hash(args),
            manifest_hash=manifest_hash,
            status="CREATED",
        )
        db.add(manifest)
        db.flush()
        for item in prepared:
            db.add(
                BatchManifestItem(
                    manifest_id=manifest.id,
                    source=item["source"],
                    destination=item["destination"],
                    source_hash=item["sourceHash"],
                    size=item["size"],
                    status=item["status"],
                    error=item["error"],
                )
            )
        artifact_dir = get_settings().data_dir / "artifacts" / "batch_manifests"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / f"{manifest.id}.json"
        artifact_path.write_text(
            json.dumps(
                {"workspaceId": args["workspace_id"], "operation": operation, "items": prepared, "manifestHash": manifest_hash},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        manifest.artifact_path = str(artifact_path)
        db.add(Artifact(task_id=task.id, path=str(artifact_path), kind="batch_manifest"))
        return manifest

    def validate_batch_manifest(self, db: Session, manifest: BatchManifest, args: dict[str, Any]) -> None:
        if manifest.workspace_id != args.get("workspace_id"):
            raise ValueError("BATCH_MANIFEST_WORKSPACE_MISMATCH")
        if manifest.operation != args.get("task_type"):
            raise ValueError("BATCH_MANIFEST_OPERATION_MISMATCH")
        if manifest.arguments_hash != argument_hash({key: value for key, value in args.items() if key != "manifest_id"}):
            raise ValueError("BATCH_MANIFEST_ARGUMENTS_CHANGED")
        policy = WorkspacePathPolicy(args["workspace_root"])
        rows = list(db.scalars(select(BatchManifestItem).where(BatchManifestItem.manifest_id == manifest.id)))
        for row in rows:
            if row.status == "FAILED":
                continue
            source = policy.resolve_existing(row.source).absolute_path
            if not source.is_file():
                raise ValueError("BATCH_SOURCE_NOT_FILE")
            if row.source_hash and sha256_file(source) != row.source_hash:
                raise ValueError("FILE_CHANGED_WHILE_WAITING")
            if source.stat().st_size != row.size:
                raise ValueError("FILE_CHANGED_WHILE_WAITING")

    def update_batch_manifest_items(self, db: Session, manifest: BatchManifest, observation: dict[str, Any]) -> None:
        rows = {
            (row.source, row.destination): row
            for row in db.scalars(select(BatchManifestItem).where(BatchManifestItem.manifest_id == manifest.id))
        }
        for item in observation.get("successes", []):
            if isinstance(item, dict):
                row = rows.get((str(item.get("source")), str(item.get("destination"))))
                if row is not None:
                    row.status = "COMPLETED"
                    row.error = None
        for item in observation.get("failures", []):
            if isinstance(item, dict):
                row = rows.get((str(item.get("source")), str(item.get("destination"))))
                if row is not None:
                    row.status = "FAILED"
                    row.error = str(item.get("error") or "")

    def create_batch_item_action(self, db: Session, task: Task, parent_action: Action, item: dict[str, Any]) -> Action:
        item_action = Action(
            task_id=task.id,
            tool_name=f"{parent_action.tool_name}.item",
            arguments_hash=argument_hash(item),
            risk_level=parent_action.risk_level,
            status="COMPLETED",
            workspace_id=parent_action.workspace_id,
            target_path=str(item.get("destination") or ""),
        )
        db.add(item_action)
        db.flush()
        db.add(
            Observation(
                action_id=item_action.id,
                task_id=task.id,
                workspace_id=item_action.workspace_id,
                summary="Batch item completed.",
                evidence={"item": item, "parent_action_id": parent_action.id},
            )
        )
        return item_action

    def create_recovery_item(self, db: Session, workspace_id: str, original_path: str, recovery_root: str, recovery_item_id: str, observation: dict[str, Any]) -> RecoveryItem:
        item = RecoveryItem(
            id=recovery_item_id,
            workspace_id=workspace_id,
            original_path=original_path,
            recovery_path=str(Path(recovery_root) / recovery_item_id),
            sha256=str(observation.get("sha256") or ""),
            size=int(observation.get("size") or 0),
            status="STORED",
        )
        db.add(item)
        return item

    def record_automation_action(self, db: Session, task: Task, action: Action, operation: str, result: ToolResult) -> None:
        postcondition = result.observation.get("postcondition")
        db.add(
            AutomationAction(
                task_id=task.id,
                action_id=action.id,
                window_target_id=None,
                operation=operation,
                status=result.status,
                postcondition=postcondition if isinstance(postcondition, dict) else {},
            )
        )

    def apply_undo(self, undo: UndoRecord) -> None:
        if undo.operation == "CREATE_DIRECTORY" and undo.destination:
            target = Path(undo.destination)
            if target.exists() and not any(target.iterdir()):
                target.rmdir()
                if target.exists():
                    raise ValueError("UNDO_POSTCONDITION_DIRECTORY_STILL_EXISTS")
            elif target.exists():
                raise ValueError("UNDO_CONFLICT_DIRECTORY_NOT_EMPTY")
            return
        if undo.operation in {"WRITE_NEW_TEXT", "COPY_FILE"} and undo.destination:
            target = Path(undo.destination)
            expected = undo.postcondition.get("sha256")
            if target.exists() and expected and sha256_file(target) == expected:
                target.unlink()
                if target.exists():
                    raise ValueError("UNDO_POSTCONDITION_FILE_STILL_EXISTS")
                return
            raise ValueError("UNDO_CONFLICT_FILE_CHANGED")
        if undo.operation in {"MOVE_FILE", "RENAME_FILE"} and undo.source and undo.destination:
            source = Path(undo.source)
            destination = Path(undo.destination)
            expected = undo.postcondition.get("sha256")
            if source.exists():
                raise ValueError("UNDO_CONFLICT_SOURCE_EXISTS")
            if not destination.exists() or (expected and sha256_file(destination) != expected):
                raise ValueError("UNDO_CONFLICT_DESTINATION_CHANGED")
            shutil.move(str(destination), str(source))
            if not source.exists() or destination.exists():
                raise ValueError("UNDO_POSTCONDITION_MOVE_FAILED")
            return
        if undo.operation == "OVERWRITE_TEXT" and undo.source and undo.backup_path:
            target = Path(undo.source)
            backup = Path(undo.backup_path)
            expected = undo.postcondition.get("sha256")
            if not backup.exists():
                raise ValueError("UNDO_BACKUP_MISSING")
            if expected and sha256_file(target) != expected:
                raise ValueError("UNDO_CONFLICT_FILE_CHANGED")
            shutil.copyfile(backup, target)
            if sha256_file(target) != undo.precondition.get("sha256"):
                raise ValueError("UNDO_POSTCONDITION_RESTORE_FAILED")
            return
        if undo.operation == "APPEND_TEXT" and undo.destination:
            target = Path(undo.destination)
            expected = undo.postcondition.get("sha256")
            original_size = undo.precondition.get("size")
            original_hash = undo.precondition.get("sha256")
            if not target.exists() or not isinstance(original_size, int):
                raise ValueError("UNDO_CONFLICT_FILE_CHANGED")
            if expected and sha256_file(target) != expected:
                raise ValueError("UNDO_CONFLICT_FILE_CHANGED")
            with target.open("r+b") as handle:
                handle.truncate(original_size)
            if original_hash and sha256_file(target) != original_hash:
                raise ValueError("UNDO_POSTCONDITION_APPEND_RESTORE_FAILED")
            return
        if undo.operation == "DESKTOP_WINDOW_STATE":
            raise ValueError("UNDO_REQUIRES_ACTIVE_DESKTOP_SESSION")
        raise ValueError("UNDO_OPERATION_UNSUPPORTED")

    def audit(self, db: Session, event_type: str, payload: dict[str, Any]) -> None:
        db.add(AuditEvent(event_type=event_type, payload=redact(payload)))
