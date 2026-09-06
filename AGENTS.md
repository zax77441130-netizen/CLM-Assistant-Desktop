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

