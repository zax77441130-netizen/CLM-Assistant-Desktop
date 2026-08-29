from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.contracts import (
    APPROVAL_REQUIRED_TOOLS,
    READ_ONLY_TOOLS,
    TOOL_TO_TASK_TYPE,
    WORKSPACE_TOOLS,
    AgentPlan,
    PlanContext,
    PlanStepSpec,
)
from app.agent.planner import CLARIFY, DeterministicPlannerProvider, OpenAIPlannerProvider, PlannerProvider
from app.agent.provider_settings import ProviderSettingsService
from app.agent.security import contains_prompt_injection
from app.models import Action, Clarification, Conversation, Message, Plan, PlanStep, Task, TaskState
from app.schemas import AssistantTaskRequest, AssistantTaskResponse, StructuredTaskRequest
from app.services.structured_task_service import StructuredTaskService

MAX_REPLANS = 2


class TaskIntakeService:
    def create(self, db: Session, request: AssistantTaskRequest) -> Task:
        task = Task(title=request.message[:240], state=TaskState.CREATED)
        db.add(task)
        conversation = Conversation(title=request.message[:240])
        db.add(conversation)
        db.flush()
        db.add(Message(conversation_id=conversation.id, task_id=task.id, role="user", content=request.message))
        db.commit()
        db.refresh(task)
        return task


class PlanValidator:
    def validate(self, plan: AgentPlan, workspace_id: str | None) -> AgentPlan:
        if len(plan.steps) > 10:
            raise ValueError("PLAN_TOO_MANY_STEPS")
        if plan.needsClarification:
            if plan.steps:
                raise ValueError("CLARIFICATION_PLAN_HAS_STEPS")
            return plan
        if not plan.steps:
            raise ValueError("PLAN_EMPTY")
        for step in plan.steps:
            self._validate_step(step, workspace_id)
        return plan

    def _validate_step(self, step: PlanStepSpec, workspace_id: str | None) -> None:
        if step.tool not in TOOL_TO_TASK_TYPE:
            raise ValueError("UNKNOWN_TOOL")
        if step.tool in WORKSPACE_TOOLS and not workspace_id:
            raise ValueError("WORKSPACE_REQUIRED")
        for key in ("path", "destination"):
            value = step.arguments.get(key)
            if isinstance(value, str) and self._looks_absolute_or_escape(value):
                raise ValueError("UNSAFE_PATH_ARGUMENT")

    def _looks_absolute_or_escape(self, value: str) -> bool:
        normalized = value.strip().replace("/", "\\")
        return (
            normalized.startswith("\\")
            or normalized.startswith("\\\\")
            or ":" in normalized
            or any(part == ".." for part in normalized.split("\\"))
        )


class ExecutionPolicy:
    def decision_for(self, step: PlanStepSpec) -> str:
        if step.tool in APPROVAL_REQUIRED_TOOLS:
            return "APPROVAL_REQUIRED"
        if step.tool in READ_ONLY_TOOLS:
            return "AUTO"
        if step.tool.startswith("filesystem."):
            return "AUTO"
        return "BLOCK"


class ToolExecutor:
    def __init__(self, service: StructuredTaskService | None = None) -> None:
        self.service = service or StructuredTaskService()

    def execute(self, db: Session, step: PlanStepSpec, workspace_id: str | None) -> object:
        task_type = TOOL_TO_TASK_TYPE[step.tool]
        request = StructuredTaskRequest(
            task_type=task_type,  # type: ignore[arg-type]
            workspace_id=workspace_id,
            path=step.arguments.get("path"),
            destination=step.arguments.get("destination"),
            content=step.arguments.get("content"),
            query=step.arguments.get("query"),
            search_content=bool(step.arguments.get("search_content", False)),
            app_id=step.arguments.get("app_id"),
        )
        return self.service.create_task(db, request)


class ObservationService:
    def latest_for_task(self, db: Session, task_id: str) -> dict[str, Any] | None:
        actions = list(db.scalars(select(Action.id).where(Action.task_id == task_id)))
        if not actions:
            return None
        observation = self.service_observation(db, actions)
        return observation

    def service_observation(self, db: Session, action_ids: list[str]) -> dict[str, Any] | None:
        from app.models import Observation

        observation = (
            db.query(Observation)
            .filter(Observation.action_id.in_(action_ids))
            .order_by(Observation.created_at.desc())
            .first()
        )
        return observation.evidence if observation else None


class ReplanPolicy:
    def should_replan(self, attempts: int) -> bool:
        return attempts < MAX_REPLANS


class CancellationService:
    def cancel(self, db: Session, task_id: str) -> AssistantTaskResponse:
        task = db.get(Task, task_id)
        if task is None:
            raise ValueError("TASK_NOT_FOUND")
        if task.state in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}:
            summary = "任務已結束，沒有需要取消的步驟。"
        else:
            task.state = TaskState.CANCELLING
            db.flush()
            task.state = TaskState.CANCELLED
            summary = "已取消任務，尚未開始的步驟不會執行。"
        db.commit()
        return AssistantTaskResponse.from_task(task, summary=summary)


class ResultPresenter:
    def present(self, response: object) -> tuple[str, dict[str, Any] | None]:
        raw = response.model_dump(mode="json") if isinstance(response, BaseModel) else {}
        observation = raw.get("observation") if isinstance(raw.get("observation"), dict) else None
        title = str(raw.get("title") or "")
        if observation and "entries" in observation:
            entries = observation.get("entries", [])
            names = [str(item.get("path")) for item in entries[:20] if isinstance(item, dict)]
            lines = "\n".join(f"• {name}" for name in names)
            return f"已找到 {len(entries)} 個項目：\n{lines}", observation
        if observation and "content" in observation:
            path = observation.get("path", "檔案")
            return f"已讀取 {path}。", observation
        if observation and "duplicates" in observation:
            duplicates = observation.get("duplicates", [])
            if not duplicates:
                return "沒有找到重複檔案。", observation
            groups = len(duplicates)
            return f"找到 {groups} 組重複檔案。", observation
        if title == "OVERWRITE_TEXT" and raw.get("state") == "WAITING_APPROVAL":
            return "這會覆寫既有檔案，需要你先核准。", observation
        if raw.get("state") == "WAITING_APPROVAL":
            return "這個動作需要你先核准。", observation
        if raw.get("state") == "COMPLETED":
            return "任務已完成。", observation
        return str(raw.get("summary") or "任務已處理。"), observation


class AgentOrchestrator:
    def __init__(
        self,
        planner: PlannerProvider | None = None,
        validator: PlanValidator | None = None,
        policy: ExecutionPolicy | None = None,
        executor: ToolExecutor | None = None,
        presenter: ResultPresenter | None = None,
        settings: ProviderSettingsService | None = None,
    ) -> None:
        self.settings = settings or ProviderSettingsService()
        mode = self.settings.get_mode()
        self.planner = planner or (OpenAIPlannerProvider(self.settings) if mode == "openai" else DeterministicPlannerProvider())
        self.validator = validator or PlanValidator()
        self.policy = policy or ExecutionPolicy()
        self.executor = executor or ToolExecutor()
        self.presenter = presenter or ResultPresenter()

    def run(self, db: Session, request: AssistantTaskRequest) -> AssistantTaskResponse:
        task = TaskIntakeService().create(db, request)
        task.state = TaskState.PLANNING
        db.commit()
        plan = self.planner.create_plan(PlanContext(request=request.message, workspace_id=request.workspace_id, provider_mode=self.settings.get_mode()))
        self.validator.validate(plan, request.workspace_id)
        saved_plan = self._save_plan(db, task, plan)
        if plan.needsClarification:
            task.state = TaskState.WAITING_CLARIFICATION
            db.add(Clarification(task_id=task.id, question=plan.clarificationQuestion or CLARIFY))
            db.commit()
            return AssistantTaskResponse.from_task(task, plan=plan, summary=plan.clarificationQuestion or CLARIFY, providerMode=self.settings.get_mode())
        if contains_prompt_injection(request.message):
            db.add(Message(conversation_id=self._conversation_id(db, task.id), task_id=task.id, role="system", content="偵測到可能的提示注入文字，已依原安全政策處理。"))
        task.state = TaskState.RUNNING
        db.commit()
        progress: list[str] = []
        result_summary = ""
        observation: dict[str, Any] | None = None
        approval_id: str | None = None
        undo_record_id: str | None = None
        for index, step in enumerate(plan.steps, start=1):
            if self.policy.decision_for(step) == "BLOCK":
                task.state = TaskState.FAILED
                result_summary = "這個操作不在目前允許範圍內。"
                break
            plan_step = PlanStep(plan_id=saved_plan.id, task_id=task.id, sort_order=index, tool_name=step.tool, arguments=step.arguments, reason=step.reason, status="RUNNING", started_at=datetime.now(UTC))
            db.add(plan_step)
            db.commit()
            step_response = self.executor.execute(db, step, request.workspace_id)
            result_summary, observation = self.presenter.present(step_response)
            raw = step_response.model_dump(mode="json") if isinstance(step_response, BaseModel) else {}
            approval_id = raw.get("approval_id") or approval_id
            undo_record_id = raw.get("undo_record_id") or undo_record_id
            plan_step.status = str(raw.get("state") or "COMPLETED")
            plan_step.finished_at = datetime.now(UTC)
            progress.append(f"完成：{step.reason}")
            if raw.get("state") == "WAITING_APPROVAL":
                task.state = TaskState.WAITING_APPROVAL
                break
            if raw.get("state") not in {"COMPLETED", "WAITING_APPROVAL"}:
                task.state = TaskState.FAILED
                break
        else:
            task.state = TaskState.COMPLETED
        db.commit()
        return AssistantTaskResponse.from_task(
            task,
            plan=plan,
            progress=progress,
            summary=result_summary,
            observation=observation,
            approval_id=approval_id,
            undo_record_id=undo_record_id,
            providerMode=self.settings.get_mode(),
        )

    def _save_plan(self, db: Session, task: Task, plan: AgentPlan) -> Plan:
        saved = Plan(
            task_id=task.id,
            goal=plan.goal,
            provider=self.settings.get_mode(),
            status="CREATED",
            needs_clarification=plan.needsClarification,
            clarification_question=plan.clarificationQuestion,
        )
        db.add(saved)
        db.commit()
        db.refresh(saved)
        return saved

    def _conversation_id(self, db: Session, task_id: str) -> str:
        message = db.scalar(select(Message).where(Message.task_id == task_id).limit(1))
        if message is None:
            conversation = Conversation(title="系統訊息")
            db.add(conversation)
            db.commit()
            return conversation.id
        return message.conversation_id
