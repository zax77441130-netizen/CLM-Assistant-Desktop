from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_phase2_columns(engine: Engine) -> None:
    """Bring early Phase 1 local SQLite databases up to the Phase 2 shape."""
    desired_columns = {
        "approvals": {
            "task_id": "VARCHAR(36)",
            "tool_name": "VARCHAR(160)",
            "normalized_arguments": "JSON",
            "exact_tool": "VARCHAR(160)",
            "exact_arguments": "JSON",
            "argument_hash": "VARCHAR(128)",
            "risk_level": "VARCHAR(40)",
            "working_directory": "TEXT",
            "status": "VARCHAR(40)",
            "expires_at": "DATETIME",
            "created_at": "DATETIME",
            "decided_at": "DATETIME",
        },
        "undo_records": {
            "task_id": "VARCHAR(36)",
            "operation": "VARCHAR(80)",
            "source": "TEXT",
            "destination": "TEXT",
            "precondition": "JSON",
            "postcondition": "JSON",
            "backup_path": "TEXT",
            "status": "VARCHAR(40)",
            "applied_at": "DATETIME",
        },
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns in desired_columns.items():
            if table not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table)}
            for column_name, column_type in columns.items():
                if column_name not in existing_columns:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}"))
