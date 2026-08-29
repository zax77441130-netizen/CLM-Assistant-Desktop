# Changelog

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
