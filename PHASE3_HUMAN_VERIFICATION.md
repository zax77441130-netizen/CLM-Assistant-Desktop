# Phase 3 Human Verification

Run this checklist on Windows after automated validation passes.

```powershell
Set-Location "C:\Users\zong\Desktop\CLM-Assistant-Desktop"
.\scripts\start_dev.ps1
.\scripts\diagnose_desktop.ps1
.\scripts\diagnose_database.ps1
```

Verify:

- Main, Preload, Renderer, Bridge, IPC, Runtime, and Database show healthy diagnostics.
- The Assistant page shows Chinese natural language controls, current workspace, assistant status, task plan, progress, result, approval, stop, and undo.
- The Assistant page does not show tool IDs, English enums, raw JSON, SQL, stack traces, IPC, token, or port details by default.
- Select a temporary workspace and run `列出目前工作區的檔案`.
- Run `讀取 example.txt` against a known text file.
- Run `找出重複檔案` in a workspace with duplicate files.
- Run `建立資料夾 測試建立`, then use Undo and confirm the folder is gone.
- For write verification, use a unique folder name such as `真人驗證-20260830-001` and confirm with Windows PowerShell:

```powershell
Test-Path -LiteralPath "<實際工作區>\<唯一資料夾名稱>"
```

- After GUI Undo, run the same `Test-Path -LiteralPath` again and confirm it returns `False`.
- Trigger an overwrite request and confirm it enters approval before changing the file.
- Reject the overwrite and confirm the original file remains unchanged.
- Send an ambiguous request and confirm the task waits for clarification.
- Confirm Settings shows provider mode, key configured/unconfigured status, and model ID without revealing the API key.
- Confirm System Diagnostics and Developer Tools live under Settings and are not part of the main assistant workflow.

Result marker until this is completed by a human tester:

`BLOCKED_EXTERNAL — waiting for human Windows desktop verification`
