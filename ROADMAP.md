# Roadmap

## Phase 0: Architecture Baseline

- Project structure.
- Product, architecture, security, tool contract, data model, roadmap, status, changelog, and README.
- Local Git repository with no remote.

## Phase 1: Desktop Runtime Foundation

- Electron + React + TypeScript shell.
- Secure preload allowlist.
- Python FastAPI Agent Runtime sidecar.
- Runtime lifecycle, token boundary, health/status endpoints.
- SQLite and Alembic foundation.
- Tests and Windows scripts.

## Phase 2: Controlled Tool Execution

- File operation tools.
- Safe PowerShell executor.
- Approval binding and undo journal.
- Observation sanitizer.
Status: file tools, host read tools, approval binding, and undo journal are implemented. Safe PowerShell executor remains future work.

## Phase 3: Agent Reasoning

- OpenAI provider adapter.
- Structured router, decision, planner, verifier.
- Bounded observation/replan loop.

## Phase 4: Packaging and Hardening

- PyInstaller sidecar.
- Electron installer.
- GUI validation.
- Production hardening and recovery.
