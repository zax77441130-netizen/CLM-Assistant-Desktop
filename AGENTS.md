# AGENTS.md

## Project Rules

This project targets Windows 10/11 x64.

OpenClaw and the bot run in WSL, but official Windows validation must be executed through Windows PowerShell.

WSL may be used for source editing, repo inspection, architecture analysis, and search.

Windows must be used for npm install/npm ci, React tests, Electron tests, `.venv-win` pytest, PyInstaller, sidecar build, desktop packaging, EXE smoke tests, Windows path behavior, System Tray, notifications, startup at login, desktop automation, and UI Automation.

Do not run Linux `npm install` in `/mnt/c/...` to modify Windows `node_modules`.

Do not declare Windows PASS unless the command ran on Windows.

Do not declare GUI PASS unless a human verified the GUI.

Do not modify the old project. It is read-only reference material only.

## Phase 2 Tool Engine Rules

Renderer must not receive the desktop session token, call generic IPC, execute raw tools, run commands, or send arbitrary absolute paths as tool arguments.

Local tools must execute through WorkspaceGrant plus relative paths. Centralized WorkspacePathPolicy is mandatory for filesystem tools.

Overwriting files requires exact approval and backup-backed undo. Permanent delete, unrestricted shell, natural language planning, production LLM calls, and Windows UI Automation are outside Phase 2.

## Phase 7B Engineering Command Rules

Engineering commands must be selected by a fixed command id. Renderer, planners, models, and
API callers must never supply raw command text, argument arrays, executable paths, or a working
directory.

Only repository-owned `scripts/test_windows.ps1` and `scripts/build_desktop.ps1` are allowed
in the first Phase 7B scope. Execution requires an existing Workspace Grant, exact approval,
a script SHA-256 fingerprint, a bounded timeout, bounded and redacted output, `shell=False`,
a pinned system PowerShell path, and timeout process-tree termination.

Changing the selected script after approval invalidates the approval. Unknown commands,
missing scripts, unavailable system PowerShell, and out-of-range timeouts fail closed.

## Phase 7C Engineering Center Rules

Engineering Center must use explicit `engineering:getProjectContext` and
`engineering:runCommand` IPC channels. Main validates workspace ids and accepts only the
`test` and `build` command ids, then constructs the fixed Runtime request itself.

Renderer must not receive the desktop token or submit raw command text, command arguments,
executable paths, working directories, timeouts, or environment values. The page must show an
exact approval card before execution and must not claim GUI verification without a human test.

## Phase 7D General Engineering Execution Rules

The fixed `test` and `build` action ids may resolve to repository Windows scripts first, then to
manifest-declared Node package scripts or the fixed Python `python -m pytest` action. Resolution
must remain inside the active Workspace Grant and fail closed when no supported marker exists.

Renderer must still never submit command text, argument arrays, executable paths, working
directories, timeouts, or environment values. The exact approval fingerprint must cover the
selected action, displayed command, runner kind, controlling project marker, and its SHA-256.
Execution uses `shell=False`, a reduced environment, bounded output and timeout, secret/path
redaction, ANSI removal, Windows output decoding, and process-tree termination on timeout.

## Phase 7E Project Readiness Rules

Engineering Center must use the same command catalog for display and execution. A language,
manifest, or lock-file marker alone must never make an action runnable. Before enabling an
action, Runtime must verify the fixed script or declared manifest action, the required package
manager or Python interpreter, and the required local dependencies.

Root and bounded nested project units may be discovered, but multiple runnable nested units must
fail closed as ambiguous until a future opaque unit selector is implemented. The Renderer must
not submit a working directory, marker path, executable, arguments, environment, or raw command.
Readiness probes must be fixed, non-mutating, `shell=False`, bounded, and must not install or
modify dependencies. Missing tools, missing dependencies, missing scripts, ambiguity, and
unsupported runners must be presented as distinct states.
