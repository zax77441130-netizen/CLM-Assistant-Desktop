# Changelog

## Phase 7B - Approved Engineering Command Runner

- Added fixed `test` and `build` command ids for repository-owned Windows validation scripts.
- Reused the existing exact approval, workspace, task, observation, capability, and audit flow.
- Bound approval to the selected script SHA-256 and invalidated changed scripts before execution.
- Pinned execution to System32 Windows PowerShell with `shell=False`, no stdin, a reduced environment, bounded timeout, and process-tree termination.
- Added bounded, path-masked, secret-redacted output and regression coverage for command rejection, approval invalidation, timeout, and output limits.

## Phase 7A - Engineering Project Context

- Added bounded, read-only engineering project inspection for existing workspace grants.
- Added project marker, stack, entrypoint, package-script, and safe Git HEAD detection.
- Added authenticated engineering context API with fail-closed workspace handling.
- Added scan limits and dependency/cache/build/VCS exclusions without arbitrary command execution.
- Added automated coverage for detection, ignored dependencies, disabled grants, and missing roots.

## 0.1.0 - Unreleased

- Established Phase 0 architecture baseline.
- Added Phase 1 Electron, React, and Python Agent Runtime foundation.
- Added secure runtime token boundary and status flow.
- Added SQLite/Alembic data model foundation.
- Added Windows bootstrap, dev, test, sidecar build, desktop build, and orphan verification scripts.
- Validated Windows backend tests, lint, typing, frontend tests, production build, Alembic migration, direct runtime smoke, PyInstaller sidecar build, and sidecar EXE smoke.
- Fixed Electron build output so Main and Preload emit to stable paths consumed by the launcher.
- Reworked Windows dev launcher to verify build outputs, Vite readiness, Electron survival, Agent Runtime state, logs, and tracked PID cleanup.
- Added Phase 2 secure workspace grants, centralized path policy, structured local file tools, host read tools, approval, undo, audit, and renderer IPC/API flow.
- Added tests for path safety, file tools, approvals, undo, audit redaction, host whitelist, IPC allowlist, and Chinese state labels.
- Fixed Phase 2.1 desktop end-to-end wiring by correcting the Preload path, bundling Preload as CommonJS, adding a shared IPC contract, wiring Renderer client methods through Main to Runtime API, and adding desktop diagnostics/smoke scripts.
- Fixed Phase 2.2 legacy runtime database migration by replacing startup `create_all()` upgrades with Alembic `upgrade head`, adding legacy schema baselining, timestamped verified backups, a Windows-safe migration lock, and a reconciliation migration for `undo_records.created_at`, nullable legacy columns, and missing task foreign keys.
- Added database diagnosis and migration scripts plus regression tests for empty databases, Phase 1/2/2.1 legacy schemas, missing `alembic_version`, inconsistent schemas, idempotency, row preservation, ORM query compatibility, API smoke, correlation IDs, migration locking, and backup failure safety.
- Sanitized Runtime and Electron error boundaries so Renderer-visible errors no longer expose raw SQL, SQLAlchemy details, stack traces, local SQLite paths, or tokens.
- Added Phase 3 Natural Language Assistant MVP with a Chinese task input, examples, workspace status, plan display, progress, Chinese result presentation, approval card, cancellation, and undo on the main Assistant page.
- Moved structured task controls to Settings, Advanced Settings, Developer Tools and moved Runtime/Bridge/Database diagnostics out of the Assistant home.
- Added Agent Orchestrator layers, deterministic local Chinese command planning, strict plan validation, high-risk approval policy, Phase 2 Tool SDK execution, prompt injection guardrails, and Chinese result composition.
- Added OpenAI planner provider scaffolding using the official Responses API with strict structured output and Windows Credential Manager API key storage without plaintext fallback.
- Added the `0004_agent_orchestration` Alembic migration for conversations, messages, plans, plan steps, clarifications, and provider settings.
- Added Phase 3 backend, renderer, IPC, provider, migration, and Windows smoke coverage.
- Fixed Phase 3.1 write-task false success risk by requiring real filesystem postconditions for write tools, rejecting stale workspace grants, preventing assistant write completion without verified observations, and adding a Windows `Test-Path` write smoke.
- Fixed duplicated LIST_DIRECTORY presentation so the main result shows one Chinese list while technical details stay collapsed.
- Renamed future migration backups from the fixed `phase2_2` suffix to revision/timestamp-based names.
- Added Phase 4 reliable multi-step task execution with plan versions, independent plan step state, dependency tracking, task events, idempotency records, workspace/path execution leases, and restart-safe waiting approval state.
- Added a persisted Chinese Task Center page and APIs for task list/detail, step timeline, observation preview, clarification answers, retry requests, continue requests, cancellation, and undo access.
- Added the `0005_reliable_task_execution` Alembic migration for task workspace binding, idempotency, action/observation workspace binding, plan step retry/output metadata, task events, execution leases, and idempotency records.
- Hardened smoke tests so Phase 2/3/3-write/4 runs use unique temporary Runtime data, SQLite, state, workspace, and token values, and Phase 4 smoke verifies the formal AppData database hash remains unchanged.
- Added Phase 5 secure Windows file and host capability suite with read-only directory analysis tools, append text, batch copy/move/rename, ZIP create/extract, assistant recovery bin move/restore, workspace file/folder open, clipboard read/write, and process termination policy wiring.
- Added centralized `CapabilityPolicy`, batch manifest persistence and artifacts, per-item batch observations and undo records, source-hash approval invalidation, safe ZIP extraction guards, recovery bin metadata, and the `0006_capabilities_recovery` Alembic migration.
- Added Phase 5 regression coverage and `scripts\smoke_phase5.ps1` for isolated Runtime data, SQLite, workspace, recovery bin, host adapters, clipboard adapter, ZIP rejection, undo, and formal AppData hash checks.
- Added Phase 6 secure Windows desktop automation with a production UIA adapter, semantic window/control resolvers, app profiles, desktop capability policy, screenshot artifact privacy, desktop postconditions, renderer desktop observation UI, and the `0007_desktop_automation` Alembic migration.
- Added Phase 6 contract coverage and `scripts\smoke_phase6.ps1` for isolated Runtime data, desktop adapter contracts, approval-gated control actions, screenshot artifacts, password control rejection, formal AppData hash checks, and explicit noninteractive live-UIA deferral.
