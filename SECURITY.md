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
