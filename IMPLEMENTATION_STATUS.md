# Implementation Status

Legend:

- IMPLEMENTED: Code or document exists.
- TESTED: Automated test executed successfully.
- VERIFIED: Runtime behavior manually or system-verified.
- BLOCKED_EXTERNAL: Needs external key, account, hardware, human GUI check, or installed dependency.
- PARTIAL: Backend/tool structures exist, desktop end-to-end interaction failed human verification.
- NOT_IMPLEMENTED: Intentionally absent.

## Phase 0

- Project directory: IMPLEMENTED
- Git repository: IMPLEMENTED
- Product documentation: IMPLEMENTED
- Architecture documentation: IMPLEMENTED
- Security documentation: IMPLEMENTED
- Tool contract documentation: IMPLEMENTED
- Data model documentation: IMPLEMENTED
- Roadmap: IMPLEMENTED

## Phase 1

- Electron desktop shell: IMPLEMENTED
- React four-page UI: IMPLEMENTED
- Secure Electron boundary: IMPLEMENTED
- Python Agent Runtime: IMPLEMENTED
- Runtime health/status endpoints: IMPLEMENTED
- SQLite initialization: IMPLEMENTED
- Alembic migration scaffold: IMPLEMENTED
- Core data models: IMPLEMENTED
- Graceful shutdown endpoint: IMPLEMENTED
- Single instance handling: IMPLEMENTED
- System tray foundation: IMPLEMENTED
- Runtime process cleanup: IMPLEMENTED
- Mock task service: IMPLEMENTED

## Validation

- Windows dependency bootstrap: TESTED
- Backend pytest: TESTED
- Backend Ruff: TESTED
- Backend mypy: TESTED
- Frontend typecheck: TESTED
- Frontend Vitest: TESTED
- Frontend production build: TESTED
- Alembic migration: TESTED
- Runtime direct smoke test: TESTED
- PyInstaller sidecar build: TESTED
- Sidecar EXE smoke test: TESTED
- Electron static/security tests: TESTED
- Electron dev launcher: TESTED
- Electron process stays running after start_dev: TESTED
- Electron starts Agent Runtime through Main: TESTED
- GUI human verification: BLOCKED_EXTERNAL

## Phase 2

- Desktop end-to-end interaction: PARTIAL — backend/tool structures exist, desktop end-to-end interaction previously failed human verification; Phase 2.1 automated diagnostics now pass and human re-test is required.
- Workspace Grant: TESTED
- Native folder picker IPC: PARTIAL — wiring repaired and diagnostics pass; native picker still requires human Windows desktop verification.
- WorkspacePathPolicy: TESTED
- Path traversal rejection: TESTED
- Absolute path rejection: TESTED
- UNC path rejection: TESTED
- Device path rejection: TESTED
- Alternate data stream rejection: TESTED
- Reserved Windows name rejection: TESTED
- Symlink escape rejection: TESTED
- Junction escape test: BLOCKED_EXTERNAL
- Tool SDK result contract: IMPLEMENTED
- filesystem.list_directory: TESTED
- filesystem.stat: TESTED
- filesystem.read_text: TESTED
- filesystem.search: TESTED
- filesystem.hash_file: TESTED
- filesystem.find_duplicates: TESTED
- filesystem.create_directory: TESTED
- filesystem.write_new_text: TESTED
- filesystem.copy: TESTED
- filesystem.move: TESTED
- filesystem.rename: TESTED
- filesystem.overwrite_text: TESTED
- host.system_info: TESTED
- host.list_processes: TESTED
- host.list_registered_apps: TESTED
- host.launch_registered_app: TESTED_WITH_MOCK
- Structured Task Service: TESTED
- Exact Approval: TESTED
- Approval reject: TESTED
- Approval expiry: TESTED
- Argument tampering: TESTED
- File changed while waiting: TESTED
- Undo success: TESTED
- Undo conflict: TESTED
- Duplicate undo rejection: TESTED
- Audit redaction: TESTED
- Runtime restart persistence: TESTED
- Renderer generic IPC rejection: TESTED
- Renderer session token boundary: TESTED
- Chinese UI state mapping: TESTED
- Renderer button wiring automated contract test: TESTED
- Phase 2 Runtime API smoke: TESTED
- Phase 2 Desktop Bridge diagnostics: TESTED
- Renderer button wiring human verification: BLOCKED_EXTERNAL
- Native folder picker human verification: BLOCKED_EXTERNAL
- Tray human verification: BLOCKED_EXTERNAL
- Close-to-background human verification: BLOCKED_EXTERNAL
- Full quit human verification: BLOCKED_EXTERNAL

## Explicitly Not Implemented In Phase 1

- Production OpenAI API integration: NOT_IMPLEMENTED
- Windows UI Automation: NOT_IMPLEMENTED
- Broad tool execution: NOT_IMPLEMENTED
- Full observation/replan loop: NOT_IMPLEMENTED
- Installer/updater: NOT_IMPLEMENTED
