# Data Model

Core entities:

- WorkspaceGrant
- Task
- TaskStep
- Action
- Approval
- Observation
- Artifact
- UndoRecord
- AuditEvent
- ScheduledTask

Task states:

- RECEIVED
- ANALYZING
- NEEDS_INPUT
- PLANNED
- RUNNING
- WAITING_APPROVAL
- VERIFYING
- COMPLETED
- FAILED
- CANCELLED
- BLOCKED

Phase 1 persists the schema and mock task records. It does not implement production LLM reasoning or unrestricted tool execution.

Phase 2 adds workspace grants, approval metadata, undo preconditions/postconditions, and audit events for structured file and host tasks.
