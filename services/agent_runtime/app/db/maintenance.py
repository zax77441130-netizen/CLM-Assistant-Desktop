from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from app.config import RuntimeSettings
from app.db.migration_manager import backup_database, collect_diagnostics, migrate_to_head


def settings_for(data_dir: str) -> RuntimeSettings:
    root = Path(data_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return RuntimeSettings(
        desktop_token="maintenance-token",
        data_dir=root,
        resource_dir=Path.cwd().resolve(),
        state_file=root / "runtime-state.json",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--migrate", action="store_true")
    parser.add_argument("--backup-only", action="store_true")
    args = parser.parse_args()
    settings = settings_for(args.data_dir)
    try:
        backup = None
        if args.backup_only:
            backup = backup_database(settings)
        elif args.migrate:
            backup = migrate_to_head(settings)
        diagnostics = collect_diagnostics(settings)
        payload = {
            "databasePath": str(diagnostics.database_path),
            "currentRevision": diagnostics.current_revision,
            "headRevision": diagnostics.head_revision,
            "legacyState": diagnostics.legacy_state,
            "issues": [asdict(issue) for issue in diagnostics.issues],
            "rowCounts": diagnostics.row_counts,
            "backup": asdict(backup) if backup else None,
        }
        print(json.dumps(payload, indent=2, default=str))
        return 1 if diagnostics.issues else 0
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
