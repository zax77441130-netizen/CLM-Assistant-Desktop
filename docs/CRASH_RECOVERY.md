# Crash Recovery

Phase 4 recovery is conservative.

- `WAITING_APPROVAL` tasks remain visible after Runtime restart and can continue through the existing exact approval flow.
- Completed side-effect steps are not blindly replayed.
- Unstarted steps remain unstarted after cancellation.
- If a future recovery pass cannot prove whether a filesystem write completed, the task must move to `NEEDS_REVIEW`.
- Recovery decisions must use persisted task state, step state, approval records, undo records, observations, and filesystem postconditions.

The current smoke test verifies that a task paused in `WAITING_APPROVAL` survives Runtime restart and can be approved afterward without changing formal AppData.

