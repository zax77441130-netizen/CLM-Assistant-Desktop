# UIA Profile Design

Phase 6 profile registry:

- Windows Notepad (`notepad`): recognizes `notepad.exe`; supports list, wait, activate, window state, inspect, read, write, invoke, close, and capture. Close and dangerous invoke actions require approval.
- Windows File Explorer (`explorer`): recognizes `explorer.exe`; supports list, wait, activate, window state, inspect, read, select, scroll, and capture. Close requires approval.
- Generic UIA Read-only (`generic_readonly`): fallback for unknown apps; supports only discovery, activation, window state, and basic control metadata inspection.

Profiles define app identity, supported controls, allowed actions, dangerous actions, postcondition expectations, sensitive-screen rules, and compatibility policy. Generic profile intentionally does not permit arbitrary typing, clicking, selecting, scrolling, closing, or screenshot capture as a substitute for a trusted profile.

Production composition uses `WindowsUIAutomationAdapter`, backed by pywinauto UIA and psutil process metadata. Fake adapters are reserved for tests and isolated smoke contract checks through explicit environment selection.

Live UIA verification must run in a real interactive Windows desktop session. Noninteractive WSL/OpenClaw runs are recorded as:

`UIA_LIVE=DEFERRED_BY_USER_NONINTERACTIVE_SESSION`

The human/live fixture lives at `scripts\fixtures\phase6_uia_fixture.ps1`. It exposes a normal text box, password text box, list, status label, safe button, dangerous button, close button, and a normal resizable/minimizable/maximizable window for live UIA checks.
