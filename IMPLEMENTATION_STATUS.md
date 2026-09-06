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
- Alembic startup migration: TESTED
- Legacy SQLite reconciliation: TESTED
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
- Phase 2.2 AppData database migration: TESTED
- Phase 2.2 legacy migration fixtures: TESTED
- Renderer raw SQL error suppression: TESTED
- Runtime diagnostic correlation ID: TESTED
- Runtime migration lock: TESTED
- LIST_DIRECTORY AppData API smoke: TESTED
- Renderer button wiring human verification: BLOCKED_EXTERNAL
- Native folder picker human verification: BLOCKED_EXTERNAL
- Tray human verification: BLOCKED_EXTERNAL
- Close-to-background human verification: BLOCKED_EXTERNAL
- Full quit human verification: BLOCKED_EXTERNAL

## Phase 2.2 External Verification

- Human Windows desktop verification: DEFERRED_BY_USER — consolidated human acceptance will be performed after feature completion

## Phase 3

- Natural language Assistant home: TESTED
- Structured task developer panel relocation: TESTED
- System diagnostics relocation: IMPLEMENTED
- TaskIntakeService: TESTED
- DeterministicPlannerProvider local command mode: TESTED
- OpenAIPlannerProvider strict structured output integration: IMPLEMENTED
- Windows Credential Manager API key storage: TESTED_WITH_FAKE
- PlanValidator strict tool/path/step checks: TESTED
- ExecutionPolicy high-risk approval routing: TESTED
- ToolExecutor through Phase 2 Tool SDK: TESTED
- ResultPresenter Chinese summaries: TESTED
- Prompt injection policy preservation: TESTED
- Assistant cancellation endpoint: TESTED
- Assistant Undo flow: TESTED
- Filesystem write postconditions: TESTED
- Workspace grant stale-root rejection: TESTED
- Production composition uses real StructuredTaskService: TESTED
- LIST_DIRECTORY duplicate result suppression: TESTED
- Phase 3 write smoke with Windows Test-Path: TESTED
- Provider settings IPC/API: TESTED
- Renderer raw JSON/SQL/stack suppression: TESTED
- Phase 3 migration `0004_agent_orchestration`: TESTED
- Phase 3 Runtime API smoke: TESTED
- OpenAI live connection: BLOCKED_EXTERNAL — requires user-provided OpenAI API key
- Human Windows desktop verification: DEFERRED_BY_USER — consolidated human acceptance will be performed after feature completion

## Phase 4

- Isolated smoke runtime data directories: TESTED
- Isolated smoke SQLite databases: TESTED
- Isolated smoke workspaces: TESTED
- Formal AppData unchanged during Phase 4 smoke: TESTED
- Plan version field: TESTED
- Independent PlanStep status: TESTED
- Step dependency persistence: TESTED
- Multi-step read-only execution: TESTED
- Multi-step create and copy execution: TESTED
- Failure stops following dependent work: TESTED
- Filesystem write postconditions in multi-step flow: TESTED
- TaskStateService centralized transitions: TESTED
- TaskEvent persistence: TESTED
- Idempotency key replay: TESTED
- Workspace/path write lock: TESTED
- Approval persists across Runtime restart: TESTED
- Approval resume through existing exact approval flow: TESTED
- Clarification waiting and answered event: TESTED
- Cancellation of waiting task: TESTED
- Retry request endpoint: IMPLEMENTED
- Continue request endpoint: IMPLEMENTED
- Task Center list API: TESTED
- Task Center detail API: TESTED
- Task Center Renderer page: TESTED
- OpenAI Responses API strict structured planner wiring: IMPLEMENTED
- OpenAI live connection: BLOCKED_EXTERNAL — requires user-provided OpenAI API key
- Human Windows desktop verification: DEFERRED_BY_USER — consolidated human acceptance will be performed after feature completion

## Phase 5

- filesystem.walk: TESTED
- filesystem.directory_summary: TESTED
- filesystem.find_large_files: TESTED
- filesystem.list_by_extension: TESTED
- filesystem.compare_files: TESTED
- filesystem.preview_batch: TESTED
- filesystem.append_text: TESTED
- filesystem.batch_copy: TESTED
- filesystem.batch_move: TESTED
- filesystem.batch_rename: TESTED
- filesystem.create_zip: TESTED
- filesystem.extract_zip: TESTED
- filesystem.move_to_recovery_bin: TESTED
- filesystem.restore_from_recovery_bin: TESTED
- host.open_workspace_file: TESTED_WITH_ADAPTER
- host.open_workspace_folder: TESTED_WITH_ADAPTER
- host.clipboard_read_text: TESTED_WITH_ADAPTER
- host.clipboard_write_text: TESTED_WITH_ADAPTER
- host.terminate_process: TESTED_WITH_ADAPTER
- CapabilityPolicy: TESTED
- Batch Manifest hash/artifact/partial failure tracking: TESTED
- Batch source revalidation and approval invalidation: TESTED
- ZIP slip rejection: TESTED
- ZIP extraction approval: TESTED
- Recovery Bin move/restore/conflict/quota metadata: TESTED
- Permanent delete tool absence: TESTED
- Planner support for large-file, ZIP, clipboard, and open-file examples: TESTED
- PlanValidator policy bypass rejection: TESTED
- Phase 5 migration `0006_capabilities_recovery`: TESTED
- Phase 5 Windows smoke script: TESTED
- Live Windows PowerShell smoke from current WSL shell: TESTED
- Human Windows desktop verification: DEFERRED_BY_USER — consolidated human acceptance will be performed after feature completion

## Phase 6

- DesktopAutomationAdapter interface: TESTED
- WindowsUIAutomationAdapter production composition: TESTED
- pywinauto UIA dependency wiring: TESTED
- psutil process identity binding: TESTED
- DesktopSessionService: TESTED
- WindowDiscoveryService: TESTED
- WindowTargetResolver fingerprint revalidation: TESTED
- ControlResolver semantic selector validation: TESTED
- DesktopActionPolicy: TESTED
- DesktopObservationService: TESTED
- ScreenArtifactService isolated artifact id: TESTED
- AutomationPostcondition: TESTED
- AutomationProfileRegistry for Notepad, File Explorer, Generic UIA Read-only: TESTED
- desktop.list_windows: TESTED_WITH_CONTRACT_FIXTURE
- desktop.wait_for_window: TESTED_WITH_CONTRACT_FIXTURE
- desktop.activate_window: TESTED_WITH_CONTRACT_FIXTURE
- desktop.get_window_state: TESTED_WITH_CONTRACT_FIXTURE
- desktop.set_window_state: TESTED_WITH_CONTRACT_FIXTURE
- desktop.inspect_controls: TESTED_WITH_CONTRACT_FIXTURE
- desktop.read_control_text: TESTED_WITH_CONTRACT_FIXTURE
- desktop.invoke_control: TESTED_WITH_CONTRACT_FIXTURE
- desktop.set_control_text: TESTED_WITH_CONTRACT_FIXTURE
- desktop.select_item: TESTED_WITH_CONTRACT_FIXTURE
- desktop.scroll_control: TESTED_WITH_CONTRACT_FIXTURE
- desktop.close_window: TESTED_WITH_CONTRACT_FIXTURE
- desktop.capture_window: TESTED_WITH_CONTRACT_FIXTURE
- CapabilityPolicy desktop capabilities: TESTED
- Planner desktop tool support: TESTED
- PlanValidator raw PID/HWND/selector/coordinate rejection: TESTED
- UI prompt-injection text treated as untrusted observation: TESTED
- Screenshot artifact isolation and metadata-only result: TESTED
- Renderer desktop observation card and masked technical details: IMPLEMENTED
- Phase 6 migration `0007_desktop_automation`: TESTED
- Phase 6 Windows smoke script: TESTED
- Live interactive UIA smoke: DEFERRED_BY_USER_NONINTERACTIVE_SESSION
- Human Windows desktop verification: DEFERRED_BY_USER — consolidated human acceptance will be performed after feature completion

## Phase 7A

- Engineering project context service: IMPLEMENTED
- Reuse existing Workspace Grant as engineering project boundary: IMPLEMENTED
- Bounded marker and stack detection: IMPLEMENTED
- Common entrypoint detection: IMPLEMENTED
- Declared package-script discovery: IMPLEMENTED
- Safe Git HEAD branch and commit inspection without command execution: IMPLEMENTED
- Dependency/cache/build/VCS directory exclusion: IMPLEMENTED
- Symlink and junction traversal rejection: IMPLEMENTED
- Authenticated engineering context API: IMPLEMENTED
- Phase 7A Windows validation: TESTED — 86 passed, 1 skipped; Ruff/mypy, TypeScript typecheck, 15 Vitest tests, and production build passed
- Engineering Center Renderer page: IMPLEMENTED — Phase 7C
- Approved Git/build/test command runner: PARTIAL — Phase 7B allows only exact-approved repository Windows test/build scripts
- Git worktree lifecycle: NOT_IMPLEMENTED
- Model router and independent code reviewer: NOT_IMPLEMENTED
- Human Windows desktop verification: DEFERRED_BY_USER

## Phase 7B

- Fixed engineering command ids (`test`, `build`): IMPLEMENTED
- Repository-owned Windows script restriction: IMPLEMENTED
- Existing Workspace Grant boundary reuse: IMPLEMENTED
- Existing exact approval, Task, Action, Observation, and audit integration: IMPLEMENTED
- Script SHA-256 approval binding and change invalidation: IMPLEMENTED
- Pinned System32 Windows PowerShell executable: IMPLEMENTED
- Raw command, raw arguments, executable path, and working-directory input rejection: IMPLEMENTED
- Reduced child-process environment and disabled stdin: IMPLEMENTED
- `shell=False` execution: IMPLEMENTED
- 60-second timeout and process-tree termination: IMPLEMENTED
- 128 KiB bounded output with workspace-path and secret redaction: IMPLEMENTED
- Phase 7B Windows validation: TESTED — 92 passed, 1 skipped; Ruff/mypy, TypeScript typecheck, 15 Vitest tests, and production build passed
- Engineering Center Renderer controls: IMPLEMENTED — Phase 7C
- General package-manager command catalog: NOT_IMPLEMENTED
- Git command/worktree lifecycle: NOT_IMPLEMENTED
- Human Windows desktop verification: DEFERRED_BY_USER

## Phase 7C

- Engineering Center navigation and responsive page: IMPLEMENTED
- Active Workspace Grant selection and persistence: IMPLEMENTED
- Bounded project-context summary: IMPLEMENTED
- Stack, entrypoint, Git, and scan-count presentation: IMPLEMENTED
- Explicit Engineering context IPC channel: IMPLEMENTED
- Explicit fixed-command Engineering IPC channel: IMPLEMENTED
- Main-process workspace-id and command-id validation: IMPLEMENTED
- Renderer raw command/argument/path/timeout input absence: IMPLEMENTED
- Test/build availability derived from trusted project context: IMPLEMENTED
- Persisted exact-approval card with expiry: IMPLEMENTED
- Chinese Engineering task and approval presentation: IMPLEMENTED
- Sanitized bounded command-output panel: IMPLEMENTED
- Engineering task persistence in Task Center: IMPLEMENTED
- Phase 7C Windows automated validation: TESTED — 92 passed, 1 skipped; Ruff/mypy, TypeScript typecheck, 18 Vitest tests, and production build passed
- Human Windows GUI verification: BLOCKED_EXTERNAL

## Explicitly Not Implemented In Phase 1

- Production OpenAI API integration: NOT_IMPLEMENTED
- Broad tool execution: NOT_IMPLEMENTED
- Full autonomous observation/replan loop beyond bounded single-pass MVP: NOT_IMPLEMENTED
- Installer/updater: NOT_IMPLEMENTED
