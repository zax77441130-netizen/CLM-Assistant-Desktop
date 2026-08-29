# Architecture

## Decision

CLM Assistant Desktop uses a local-first desktop agent architecture.

Electron Main owns desktop lifecycle, single instance, tray, notifications, startup preferences, runtime process startup, runtime shutdown, process cleanup, and the desktop session token.

Renderer is a restricted UI surface. It cannot access Node APIs and cannot read the desktop session token.

Agent Runtime is a single Python FastAPI sidecar process. It owns the local API, durable task queue foundation, worker/scheduler boundaries, recovery model, audit trail, and notification event foundation.

## Runtime Boundary

- Runtime binds only to `127.0.0.1`.
- Electron Main generates a high-entropy desktop session token for each launch.
- Token is passed to Agent Runtime through environment variables.
- Renderer communicates through explicit preload APIs only.
- Generic IPC channels are not allowed.

## Desktop Build Outputs

The desktop build pipeline emits:

- Electron Main: `apps/desktop/dist/main/main.js`
- Electron Preload: `apps/desktop/dist/preload/preload.cjs`
- Renderer: `apps/desktop/dist/renderer/index.html`

TypeScript emits Electron Main and shared contract modules. Vite builds the Renderer and bundles Preload as CommonJS so Electron can load it under sandboxed preload rules.

## Phase 2.1 Desktop Wiring

The desktop API has one shared IPC contract source: `apps/desktop/src/shared/ipcContract.ts`.

Renderer calls `desktopApiClient`, Preload exposes the same explicit methods through `contextBridge`, Electron Main registers matching `ipcMain.handle` handlers, and Runtime API calls are made only by Electron Main with the desktop session token.

Development diagnostics write local logs under `.runtime/logs/`:

- `electron.log`
- `preload.log`
- `renderer.log`
- `runtime-api.log`

Request IDs are logged for Runtime API correlation. The desktop session token is not logged and is not exposed to Renderer.

## Phase 2.2 Runtime Database Migration

Agent Runtime uses Alembic `upgrade head` during startup. `Base.metadata.create_all()` is not used as a schema upgrade path because it cannot safely reconcile existing SQLite tables.

Startup migration is guarded by a filesystem lock in the Runtime data directory so only one Runtime process can migrate a database at a time on Windows. Existing non-empty SQLite databases are copied to a timestamped `.bak` file before migration, and the copy is verified by size and SHA-256 before schema changes continue.

Legacy databases without `alembic_version` are identified from SQLite metadata before baselining:

- empty database: upgrade from base
- Phase 1 create_all schema: stamp `0001_initial`, then upgrade
- Phase 2 / Phase 2.1 legacy schema: stamp `0002_workspace_tool`, then run reconciliation
- unknown or inconsistent schema: fail closed and keep the backup

The `0003_reconcile_legacy` migration backfills and rebuilds legacy SQLite tables so `approvals` and `undo_records` match the current ORM shape, including `undo_records.created_at` and `task_id` foreign keys.

Runtime API errors are converted to structured safe payloads with a correlation ID. Raw SQL, SQL parameters, stack traces, local SQLite paths, SQLAlchemy URLs, and tokens are kept out of Renderer-visible errors.

## Phase 3 Natural Language Assistant

The main Assistant page is now the user-facing workflow. Users enter Chinese natural language, select a workspace, review the task plan, watch progress, approve dangerous operations, cancel waiting/running tasks, and undo the last undoable operation. The old structured file task UI is retained only under Settings, Advanced Settings, Developer Tools.

Renderer never executes tools directly. It calls explicit preload methods, Electron Main forwards token-protected requests to Agent Runtime, and Runtime owns the orchestration flow:

natural language request -> TaskIntakeService -> PlannerProvider -> PlanValidator -> ExecutionPolicy -> ToolExecutor -> Phase 2 StructuredTaskService -> Observation -> ResultPresenter.

The Agent Orchestrator is intentionally layered:

- `TaskIntakeService` creates the durable task and conversation message.
- `PlannerProvider` produces a strict structured plan. `DeterministicPlannerProvider` is the default local command mode; `OpenAIPlannerProvider` is configurable.
- `PlanValidator` rejects unknown tools, absolute paths, path traversal, missing workspace IDs, empty plans, and plans over 10 steps.
- `ExecutionPolicy` auto-runs low-risk read and undoable workspace operations and requires approval for overwrites and external side-effect tools.
- `ToolExecutor` converts validated plan steps into existing Phase 2 structured tasks.
- `CancellationService` moves cancellable tasks to `CANCELLED` and prevents further planned work.
- `ResultPresenter` converts tool observations into Chinese user-facing summaries.

The allowed planner tool surface is the existing Tool Registry only: workspace file read/search/hash/duplicate/create/copy/move/rename/write-new/overwrite plus host read-only diagnostics and registered app launch. No shell, PowerShell, `cmd.exe`, arbitrary executable path, Windows UI Automation, automatic deletion, or workspace escape tool is introduced.

The `0004_agent_orchestration` migration adds durable conversation, message, plan, plan step, clarification, and provider setting tables. Runtime continues to migrate through Alembic head on startup, including fresh databases and AppData databases already upgraded through `0003_reconcile_legacy`.

## Planner Providers

Local command mode requires no API key and supports deterministic Chinese commands for common file and host tasks. OpenAI mode uses the official Responses API with strict structured JSON output. Model ID is configured in the desktop settings and defaults to a configurable value, not a credential.

OpenAI API keys are stored only through Windows Credential Manager by the Python sidecar. The key is never written to SQLite, `.env`, logs, IPC state, or Renderer-accessible status. Renderer can save, delete, test, and check whether a key exists, but it cannot read the full key back.

Workspace file content is untrusted. Prompt injection text cannot alter policy; model output must still pass validation and execution policy. The provider prompt forbids shell commands, absolute paths, unknown tools, secret exfiltration, and policy changes based on file contents.

## Agent Core Boundaries

Phase 1 defines interfaces and data models for:

- Task Intake
- Context Builder
- Clarification Manager
- Reasoning Service
- Planner
- Plan Validator
- Policy Engine
- Approval Manager
- Executor
- Observation Sanitizer
- Replanner
- Completion Verifier
- Result Composer
- Memory Service
- Artifact Service

Production LLM reasoning is intentionally not wired in Phase 1.
