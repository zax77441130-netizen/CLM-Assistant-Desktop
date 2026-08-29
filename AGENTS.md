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
