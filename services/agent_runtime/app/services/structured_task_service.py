from __future__ import annotations

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import file_tools, host_tools
from app.core.audit import redact
from app.core.file_tools import sha256_file
from app.core.path_policy import WorkspacePathPolicy
from app.core.tool_sdk import RiskLevel, ToolResult, argument_hash
from app.models import Action, Approval, AuditEvent, Observation, Task, TaskState, TaskStep, UndoRecord, WorkspaceGrant
from app.schemas import StructuredTaskRequest, TaskResponse, WorkspaceGrantCreate


WORKSPACE_READ_TASKS = {"LIST_DIRECTORY", "STAT_PATH", "READ_TEXT", "SEARCH_FILES", "HASH_FILE", "FIND_DUPLICATES"}
HOST_READ_TASKS = {"SYSTEM_INFO", "LIST_PROCESSES", "LIST_REGISTERED_APPS"}
READ_TASKS = WORKSPACE_READ_TASKS | HOST_READ_TASKS
WRITE_TASKS = {"CREATE_DIRECTORY", "WRITE_NEW_TEXT", "COPY_FILE", "MOVE_FILE", "RENAME_FILE"}


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

            if request.task_type == "OVERWRITE_TEXT":
                return self.require_overwrite_approval(db, task, step, action, normalized)
            if request.task_type == "LAUNCH_REGISTERED_APP":
                action.status = "HUMAN_VERIFICATION_REQUIRED"
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
            result = self.execute_overwrite(db, task, action, approval.normalized_arguments)
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
        if request.task_type in WORKSPACE_READ_TASKS | WRITE_TASKS | {"OVERWRITE_TEXT"}:
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
            "STAT_PATH": "filesystem.stat",
            "READ_TEXT": "filesystem.read_text",
            "SEARCH_FILES": "filesystem.search",
            "HASH_FILE": "filesystem.hash_file",
            "FIND_DUPLICATES": "filesystem.find_duplicates",
            "CREATE_DIRECTORY": "filesystem.create_directory",
            "WRITE_NEW_TEXT": "filesystem.write_new_text",
            "COPY_FILE": "filesystem.copy",
            "MOVE_FILE": "filesystem.move",
            "RENAME_FILE": "filesystem.rename",
            "OVERWRITE_TEXT": "filesystem.overwrite_text",
            "SYSTEM_INFO": "host.system_info",
            "LIST_PROCESSES": "host.list_processes",
            "LIST_REGISTERED_APPS": "host.list_registered_apps",
            "LAUNCH_REGISTERED_APP": "host.launch_registered_app",
            "UNDO_ACTION": "undo.apply",
        }[task_type]

    def risk_for(self, task_type: str) -> str:
        if task_type == "OVERWRITE_TEXT":
            return RiskLevel.HIGH_RISK.value
        if task_type in WRITE_TASKS or task_type in {"LAUNCH_REGISTERED_APP", "UNDO_ACTION"}:
            return RiskLevel.WRITE.value
        return RiskLevel.READ.value

    def execute_normalized(self, db: Session, task: Task, action: Action, task_type: str, args: dict[str, Any]) -> ToolResult:
        root = args.get("workspace_root", "")
        path = args.get("path") or "."
        destination = args.get("destination")
        content = args.get("content") or ""
        if task_type == "LIST_DIRECTORY":
            return file_tools.list_directory(root, path)
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
        if task_type == "SYSTEM_INFO":
            return host_tools.system_info()
        if task_type == "LIST_PROCESSES":
            return host_tools.list_processes()
        if task_type == "LIST_REGISTERED_APPS":
            return host_tools.list_registered_apps()
        if task_type == "LAUNCH_REGISTERED_APP":
            return host_tools.launch_registered_app(args.get("app_id") or "")
        raise ValueError("TASK_TYPE_NOT_IMPLEMENTED")

    def require_overwrite_approval(self, db: Session, task: Task, step: TaskStep, action: Action, args: dict[str, Any]) -> TaskResponse:
        root = args["workspace_root"]
        path = args.get("path") or ""
        target = WorkspacePathPolicy(root).resolve_existing(path).absolute_path
        args["expected_sha256"] = sha256_file(target)
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
            working_directory=args["workspace_id"],
            risk_reason="Overwrite existing file requires exact approval.",
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
        if tool_name not in {"filesystem.create_directory", "filesystem.write_new_text", "filesystem.copy", "filesystem.move", "filesystem.rename", "filesystem.overwrite_text"}:
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
        raise ValueError("UNDO_OPERATION_UNSUPPORTED")

    def audit(self, db: Session, event_type: str, payload: dict[str, Any]) -> None:
        db.add(AuditEvent(event_type=event_type, payload=redact(payload)))
