# Security

## Desktop Security

- `nodeIntegration` is disabled.
- `contextIsolation` is enabled.
- Renderer sandbox is enabled.
- Preload exposes only a small allowlist.
- No generic IPC bridge exists.
- Desktop session token is never exposed to Renderer.
- Renderer shows a blocking Chinese error if the Preload bridge is missing instead of falling back to no-op behavior.
- Preload is bundled as CommonJS and imports only the shared IPC contract, not Electron Main modules.

## Runtime Security

- Runtime listens on `127.0.0.1` only.
- `/api/*` endpoints require `X-Desktop-Token`.
- `/health` is intentionally unauthenticated for process supervision.
- Side-effecting tools must declare capability, risk, permission, timeout, retry behavior, side effects, undo support, idempotency key support, observations, and evidence.

## Approval Policy

Human approval is required for destructive deletion, overwrites, irreversible batch operations, cross-workspace bulk movement, application shutdown that may lose unsaved data, install/uninstall, registry/system settings, admin elevation, external transmission, account credentials, payments, forms, and reduced system protection.

Approval must bind exact tool, exact arguments, argument hash, working directory, risk reason, expiration, run ID, and action ID.

## Workspace Path Policy

Renderer and future LLM code may only reference files through `workspace_id` and relative paths. Runtime rejects path traversal, absolute paths, UNC paths, device paths, alternate data streams, reserved Windows device names, workspace escape through symlinks, same-path moves, and overwriting destinations without approval.

## Diagnostics

Development logs are stored locally in `.runtime/logs/`. Runtime API logs include request IDs and paths but do not include the desktop session token.

Runtime API exceptions are mapped to structured safe errors before they cross the Electron IPC boundary. Renderer-visible messages must not include raw SQL, SQL parameters, SQLAlchemy URLs, Python stack traces, local SQLite paths, tokens, or file contents. Detailed technical errors stay in local diagnostics with a correlation ID and redaction.

## Database Maintenance

Runtime database migration is local-only and backup-first. Before any schema-changing maintenance, stop the dev stack and confirm no tracked Runtime, Vite, or Electron process is still alive:

```powershell
Set-Location "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
.\scripts\stop_dev.ps1
.\scripts\verify_no_orphans.ps1
.\scripts\migrate_runtime_database.ps1 -WhatIf
.\scripts\migrate_runtime_database.ps1
```

The migration path never deletes, recreates, or clears the original SQLite database. Unknown legacy schemas fail closed after backup and require manual diagnosis.
