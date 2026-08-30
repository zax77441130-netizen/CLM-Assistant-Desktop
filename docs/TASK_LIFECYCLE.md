# Task Lifecycle

Phase 4 task execution is driven by a centralized state machine in `TaskStateService`.

## States

- `CREATED`: Task row exists.
- `PLANNING`: Planner is producing a strict plan.
- `WAITING_CLARIFICATION`: Runtime needs more user information before execution.
- `QUEUED`: Plan is valid and ready to run.
- `RUNNING`: Runtime is executing one dependency-satisfied step.
- `WAITING_APPROVAL`: A high-risk step is paused for exact approval.
- `RETRYING`: A retryable failure is being retried within policy limits.
- `CANCELLING`: Cancellation has been requested.
- `CANCELLED`: No further unstarted steps will run.
- `COMPLETED`: All required steps completed and write postconditions passed.
- `FAILED`: The task cannot continue safely.
- `NEEDS_REVIEW`: Runtime cannot prove whether a prior side effect completed.

Older Phase 1/2 states remain readable for compatibility.

## Rules

- Illegal state transitions are rejected.
- Every orchestrator transition writes a `task_events` record.
- Each `PlanStep` stores its own status, dependency pointer, workspace id, retry counters, output size, and timestamps.
- Renderer resubmits use idempotency keys so duplicate IPC/API requests do not create duplicate tasks.
- Write steps must acquire workspace/path leases before execution.
- Write steps complete only after a real Phase 2 tool observation includes `postcondition.verified=true`.

