# Test Isolation

Windows smoke tests must never use the formal Runtime profile.

Blocked paths:

- `C:\Users\zong\AppData\Roaming\CLM Assistant Desktop`
- `C:\Users\zong\Desktop\測試資料夾`

Phase 2, Phase 3, Phase 3 write, and Phase 4 smoke scripts create unique temporary directories for:

- Runtime data
- SQLite database
- Runtime state
- Workspace
- Logs when applicable
- Runtime token

Each smoke asserts its resolved paths do not enter the formal AppData profile or the formal desktop verification workspace. Phase 4 additionally records the formal AppData database SHA-256 before and after the smoke and fails if it changes.

Smoke cleanup only removes the unique temporary directories created by that run.

