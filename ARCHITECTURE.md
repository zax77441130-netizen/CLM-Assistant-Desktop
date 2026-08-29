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
