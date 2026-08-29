# Product Spec

## Product

CLM Assistant Desktop is a Windows local-first AI work assistant. It receives natural language tasks, inspects allowed host context, builds a plan, evaluates risk, executes approved local actions, observes results, replans when needed, verifies completion, and reports evidence and recovery options.

## Phase 1 Scope

Implemented in this phase:

- Electron desktop foundation.
- React renderer with four primary navigation pages: Assistant, Tasks, Automations, Settings.
- Secure Electron Main / Preload / Renderer boundary.
- Single Python Agent Runtime sidecar.
- Runtime health and status endpoints.
- SQLite schema foundation.
- Alembic migration foundation.
- Mock task service for real end-to-end data flow.
- Approval, audit, observation, artifact, undo, and schedule data models.

Not implemented in this phase:

- Production OpenAI integration.
- Real Windows UI Automation.
- Broad tool execution.
- Full observation/replan loop.
- Production installer and updater.

## Completion Rules

A task cannot be marked completed solely because a process exits with code `0`. Completion requires all required actions to finish, verifier success, inspectable evidence, target state confirmation, and no unresolved high-risk operation.
