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
