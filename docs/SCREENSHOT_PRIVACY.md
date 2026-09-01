# Screenshot Privacy

`desktop.capture_window` is scoped to the currently authorized target window. It must not capture the full desktop by default, and Phase 6 does not implement vision coordinate fallback or background recording.

Capture requires explicit approval. The target is revalidated immediately before capture using the same window identity binding used by other desktop actions. Password, secure, protected, high-integrity, or unknown-sensitive windows are rejected.

Screenshot artifacts use random ids and are stored under the Runtime artifact directory. The filename is not derived from the window title. Smoke tests use an isolated artifact directory. Screenshot binaries are not stored in SQLite, logs, task observations, or Git.

Runtime responses expose only metadata such as artifact id and size. Main UI shows a user-readable artifact entry, while low-level identifiers remain masked in collapsed technical details.

Artifacts are intended to have a retention and capacity policy under Runtime control. User-facing deletion from Task Center is the expected cleanup path; automatic background capture or monitoring is not allowed.
