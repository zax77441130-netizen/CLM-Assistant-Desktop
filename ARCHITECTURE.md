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

Filesystem write tools must prove their side effects before completion. `create_directory`, `write_new_text`, `copy`, `move`, `rename`, and `overwrite_text` all re-resolve the affected path through `WorkspacePathPolicy`, verify the expected Windows filesystem state, and attach a `postcondition.verified=true` observation. Structured tasks and assistant tasks are not marked `COMPLETED` unless that postcondition is present for write operations.

Workspace grants are never allowed to fall back to the current directory, AppData, project root, or a temp folder. Runtime revalidates each grant root before use and hides/marks stale deleted grants as disabled when workspaces are listed. Renderer persists the user's selected workspace id locally and restores it only if Runtime still returns that grant.

The `0004_agent_orchestration` migration adds durable conversation, message, plan, plan step, clarification, and provider setting tables. Runtime continues to migrate through Alembic head on startup, including fresh databases and AppData databases already upgraded through `0003_reconcile_legacy`.

## Planner Providers

Local command mode requires no API key and supports deterministic Chinese commands for common file and host tasks. OpenAI mode uses the official Responses API with strict structured JSON output. Model ID is configured in the desktop settings and defaults to a configurable value, not a credential.

OpenAI API keys are stored only through Windows Credential Manager by the Python sidecar. The key is never written to SQLite, `.env`, logs, IPC state, or Renderer-accessible status. Renderer can save, delete, test, and check whether a key exists, but it cannot read the full key back.

Workspace file content is untrusted. Prompt injection text cannot alter policy; model output must still pass validation and execution policy. The provider prompt forbids shell commands, absolute paths, unknown tools, secret exfiltration, and policy changes based on file contents.

## Phase 4 Reliable Multi-step Execution

Phase 4 extends the assistant loop from a single safe step to a durable multi-step execution core:

task intake -> planning -> plan validation -> policy evaluation -> queued execution -> per-step execution -> filesystem postcondition -> observation -> continue, clarification, approval, retry, cancellation, or final result.

Plans now carry a version and each plan step stores its own status, dependency pointer, workspace id, retry counters, output size, start time, and finish time. The Runtime executes one dependency-satisfied step at a time and never marks a write step complete unless the real Phase 2 tool result contains a verified filesystem postcondition.

Task state transitions are centralized in `TaskStateService`. Legal Phase 4 states are `CREATED`, `PLANNING`, `WAITING_CLARIFICATION`, `QUEUED`, `RUNNING`, `WAITING_APPROVAL`, `RETRYING`, `CANCELLING`, `CANCELLED`, `COMPLETED`, `FAILED`, and `NEEDS_REVIEW`, while older Phase 1/2 compatibility states remain readable. Every orchestrator transition writes a `task_events` row so the Task Center and Assistant home read the same persisted state.

The execution layer adds idempotency records and short-lived execution leases. Renderer resubmits with the same idempotency key return the original task response instead of creating duplicate tasks. Write steps acquire workspace/path leases before execution; conflicting writes fail closed with a Chinese user-facing message and no filesystem side effect. Read-only tasks remain parallel-safe.

Workspace identity is stored on tasks, actions, observations, and plan steps. Runtime revalidates workspace grants before each Phase 2 tool call and never falls back to the project directory, AppData, current working directory, or smoke-test temp folders.

Clarification, approval, cancellation, retry, continue, and restart recovery are exposed through explicit Runtime APIs and IPC methods. Waiting approval tasks persist across Runtime restart. Completed side-effect steps are not blindly replayed; uncertain future recovery cases are represented by `NEEDS_REVIEW`.

The Task Center UI is a Chinese persisted task view with filtering, status, workspace, step timeline, observation preview, actions, and collapsed technical details. General UI surfaces do not show tool ids, raw JSON, SQL, stack traces, IPC channels, ports, or tokens.

The `0005_reliable_task_execution` migration adds task workspace/idempotency columns, action and observation workspace binding, plan versioning, plan step dependency/retry/output metadata, `task_events`, `execution_leases`, and `idempotency_records`. Fresh databases and databases at `0004_agent_orchestration` migrate to the new head through Alembic.

## Phase 5 Secure Windows File And Host Capabilities

Phase 5 expands the allowed tool surface without introducing arbitrary shell, PowerShell, `cmd.exe`, scripts, or executable path execution. New tools still flow through Planner, PlanValidator, ExecutionPolicy, WorkspacePathPolicy, the Tool SDK, approval, postcondition verification, observations, undo records, and audit events.

Read-only workspace tools now include recursive walking, directory summaries, large-file search, extension listing, file comparison, and batch previews. They enforce workspace-relative paths, recursion depth limits, item limits, output limits, symlink/junction escape checks, and avoid file content reads except where an existing read/search tool explicitly requires it.

Write tools now include append text, batch copy/move/rename, ZIP create/extract, move to assistant recovery bin, and restore from assistant recovery bin. Permanent deletion remains intentionally absent. Low-risk undoable workspace writes can run automatically; high-risk or privacy-sensitive operations require approval.

`CapabilityPolicy` is the centralized capability decision map. Providers and planner output cannot change it. Current capabilities are `workspace.read`, `workspace.write`, `archive.create`, `archive.extract`, `recovery_bin.write`, `recovery_bin.restore`, `host.open_file`, `host.open_folder`, `clipboard.read`, `clipboard.write`, and `process.terminate`, plus permanently blocked `execution.arbitrary` and `file.delete_permanent`.

Batch operations create an immutable `BatchManifest` before execution. The manifest binds task, workspace, operation, arguments hash, per-item source/destination, source hash, size, status, and a manifest hash. Large batches wait for exact approval. Before execution the Runtime revalidates source hashes and sizes, so a file change invalidates the approval. Each successful item receives its own action, observation, and undo record; partial failures are reported as partial results, not as atomic success.

ZIP tools reject absolute paths, drive-qualified paths, `..` traversal, symlink entries, excessive item counts, excessive expanded size, and existing destination conflicts. Extract defaults to no overwrite and requires approval. Every extracted file is resolved through WorkspacePathPolicy and must remain inside the selected workspace.

The assistant recovery bin is app-managed storage under the Runtime data directory, partitioned by workspace id. Recovery items store original workspace path, recovery item id, recovery path, SHA-256, size, status, and timestamps. Moving to the recovery bin requires approval, verifies that the original path is gone and the recovery file exists, and records undo. Restore refuses to overwrite existing workspace files. Automatic permanent cleanup is not implemented.

Host tools are workspace-bound or privacy-gated. `host.open_workspace_file` and `host.open_workspace_folder` use the Windows Shell default handler only for selected workspace paths and reject executable/script extensions plus `.lnk` and `.url`. Clipboard read requires explicit approval, masks secret-like text, does not keep history, and writes no clipboard content to SQLite/logs. Clipboard write reports only character count. Process termination is modeled as high risk and rejects protected process names; production termination must revalidate identity before acting.

The `0006_capabilities_recovery` migration adds `capability_grants`, `batch_manifests`, `batch_manifest_items`, and `recovery_items`. Fresh databases and databases upgraded through `0005_reliable_task_execution` migrate to the new head through Alembic.

## Phase 6 Secure Windows Desktop Automation

Phase 6 adds a bounded desktop automation layer for Windows UI Automation. It is not a coordinate mouse/keyboard controller and it does not execute arbitrary shell, PowerShell, command prompt, scripts, UAC prompts, secure desktop actions, browser web automation, login/payment flows, shutdown/restart/lock operations, or arbitrary executable paths.

The runtime layer is split into `DesktopAutomationAdapter`, `WindowsUIAutomationAdapter`, `DesktopSessionService`, `WindowDiscoveryService`, `WindowTargetResolver`, `ControlResolver`, `DesktopActionPolicy`, `DesktopObservationService`, `ScreenArtifactService`, `AutomationPostcondition`, and `AutomationProfileRegistry`. Production composition uses the real `WindowsUIAutomationAdapter`, backed by pywinauto UIA and psutil process identity metadata. Tests and smoke scripts can select the fake adapter only through explicit isolated test environment variables.

Desktop tools are registered through the same Planner, PlanValidator, ExecutionPolicy, CapabilityPolicy, Tool SDK, approval, observation, postcondition, undo journal, and audit path as file and host tools. Supported tools are `desktop.list_windows`, `desktop.wait_for_window`, `desktop.activate_window`, `desktop.get_window_state`, `desktop.set_window_state`, `desktop.inspect_controls`, `desktop.read_control_text`, `desktop.invoke_control`, `desktop.set_control_text`, `desktop.select_item`, `desktop.scroll_control`, `desktop.close_window`, and `desktop.capture_window`.

Window operations are bound to registered app identity, executable identity, PID, process creation time, window handle, UIA runtime identity, runtime session id, and target fingerprint. Each operation revalidates the current window before acting to reduce PID reuse, handle reuse, window switching, title collision, and impersonation risks. Planner output may describe semantic targets only; it cannot provide PIDs, HWNDs, executable paths, raw selectors, XPath, COM objects, or coordinates.

Control resolution happens inside Runtime. `ControlResolver` matches by semantic name, control type, optional AutomationId, enabled/visible state, supported UIA pattern, and target-window ancestry metadata exposed by the adapter. Password or security controls are rejected, ambiguous controls block safely, and unsupported patterns never fall back to coordinates.

`CapabilityPolicy` now includes desktop capabilities for window listing, activation, state changes, control inspection/read/invoke/write, window close, and screen capture. Read-only discovery and safe window state changes can auto-run for approved app profiles; reading text, writing text, invoking controls, selecting items, scrolling, closing windows, and capturing screenshots require explicit approval or explicit user request depending on their risk class. LLM output cannot reduce the policy decision.

Automation profiles define the supported surface for Windows Notepad, Windows File Explorer, and Generic UIA Read-only. The generic profile can discover, inspect, activate, and change window state only; it cannot click, type, select, scroll, close, or capture without a more specific trusted profile.

Desktop observations treat UI text and UIA trees as untrusted data. General UI shows Chinese task progress and sanitized window/app state. Raw identifiers and technical details are collapsed and masked. Full UI trees and screenshots are not automatically sent to OpenAI.

`desktop.capture_window` captures only the authorized target window into a random-id file under the Runtime artifact directory. SQLite stores only metadata. Screenshot binaries are not written to logs or Git and smoke tests use an isolated artifact directory.

The `0007_desktop_automation` migration adds `desktop_sessions`, `window_targets`, `automation_actions`, `automation_profile_grants`, and `screen_artifacts`. Fresh databases and databases upgraded through `0006_capabilities_recovery` migrate to the new head through Alembic.

## Phase 7A Engineering Project Context

Phase 7A introduces a bounded, read-only engineering context service on top of the existing
Workspace Grant. It does not create a second project root or bypass WorkspacePathPolicy.

`ProjectContextService` detects project markers, language and framework families, common
entrypoints, declared package scripts, and safe Git HEAD metadata. It does not execute Git,
PowerShell, shell commands, package managers, builds, or tests. Candidate commands are labels
for a future approved runner and are never executed by this endpoint.

Scanning is bounded by depth, file count, and marker count. Dependency, cache, build, runtime,
and VCS directories are excluded. Symlinks and Windows junctions are not traversed. Source file
contents are not returned; only known small metadata files such as `package.json` and `.git/HEAD`
may be read with explicit size limits.

The authenticated endpoint is
`GET /api/engineering/projects/{workspace_id}/context`. Missing workspaces fail with 404;
disabled, missing, or unavailable workspace roots fail closed with 409.

## Phase 7B Approved Engineering Command Runner

Phase 7B introduces a deliberately narrow command runner for Windows project validation. API
callers select only the fixed command ids `test` or `build`; they cannot submit command text,
arguments, executable paths, or a working directory. The ids resolve only to repository-owned
`scripts/test_windows.ps1` and `scripts/build_desktop.ps1` inside the active Workspace Grant.

Every engineering command is classified high risk and flows through the existing Task, Action,
Approval, Observation, CapabilityPolicy, and AuditEvent path. Before approval, Runtime hashes
the selected script and binds the command id, display label, relative script path, SHA-256,
timeout, workspace, and command fingerprint into the exact approval arguments. A script change
while waiting invalidates the approval.

Execution uses an argument array with `shell=False`, a verified absolute path to Windows
PowerShell under System32, the granted workspace as `cwd`, a reduced environment, no stdin,
a maximum 60-second timeout, and a 128 KiB output cap. Timeout handling terminates the spawned
process tree. Output replaces the workspace path and redacts secret-like assignments and
authorization lines before persistence or display.

Arbitrary shell, command prompt, executable paths, package-manager arguments, interactive
input, background execution, and commands outside the two trusted repository scripts remain
blocked. Engineering Center UI, model routing, Git worktrees, and code-review automation remain
future phases.

## Phase 7C Engineering Center

Phase 7C adds a dedicated desktop Engineering Center backed by the Phase 7A read-only project
context and Phase 7B approved runner. It displays the selected Workspace Grant, detected stacks,
common entrypoints, bounded scan counts, and safe Git branch/commit metadata.

The Renderer receives two explicit bridge methods only: project-context retrieval and execution
of a fixed `test` or `build` command id. Main validates workspace identifiers and command ids,
constructs the fixed `ENGINEERING_RUN` request, sets the bounded timeout, and sends it to Runtime.
There is no command input, generic IPC, raw tool call, executable path, working-directory input,
or caller-controlled argument array.

Test and build controls are enabled only when Phase 7A detects the matching repository-owned
Windows script. Clicking a control creates a waiting-approval task. The page retrieves the
persisted approval, shows the localized risk reason and expiry, and requires a separate approve
or reject action. Sanitized command output is shown in a bounded scroll area, while the complete
task remains available in Task Center.

## Phase 7D Execution Feedback and General Project Commands

Phase 7D keeps the Renderer contract limited to the fixed `test` and `build` action ids, but the
Runtime may now resolve those ids from the active project's own markers. Repository-owned Windows
validation scripts remain the first choice. When they are absent, a root `package.json` script may
resolve to npm, pnpm, or yarn, and a Python project marker may resolve `test` to the fixed
`python -m pytest` action. Missing actions fail closed.
Python markers use the same bounded four-level, no-link traversal model as project-context
detection so the UI and execution policy cannot disagree for nested backend layouts.

The approval fingerprint binds the action id, displayed command, runner kind, controlling marker
path, and marker SHA-256. Callers still cannot provide raw command text, arguments, executables,
working directories, environment values, or timeouts. Processes use an argument array with
`shell=False`, a reduced environment, a 120-second timeout, bounded capture, process-tree
termination, secret/path redaction, ANSI removal, and UTF-8/Windows Traditional Chinese decoding.

Engineering Center switches to `RUNNING` immediately after approval, hides the stale approval
card, shows an elapsed timer, prevents duplicate clicks, and allows 135 seconds for the bounded
Runtime response. Final execution remains persisted in Task Center.

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
