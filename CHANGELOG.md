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
