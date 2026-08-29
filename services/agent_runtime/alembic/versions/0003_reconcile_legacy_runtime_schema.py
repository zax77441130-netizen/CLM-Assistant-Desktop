"""reconcile legacy runtime schema

Revision ID: 0003_reconcile_legacy
Revises: 0002_workspace_tool
Create Date: 2026-08-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_reconcile_legacy"
down_revision = "0002_workspace_tool"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(f'PRAGMA table_info("{table_name}")').fetchall()
    return {str(row[1]) for row in rows}


def _add_column_if_missing(table_name: str, column: sa.Column[object]) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def upgrade() -> None:
    _add_column_if_missing("approvals", sa.Column("task_id", sa.String(length=36), nullable=True))
    _add_column_if_missing("approvals", sa.Column("tool_name", sa.String(length=160), nullable=True))
    _add_column_if_missing("approvals", sa.Column("normalized_arguments", sa.JSON(), nullable=True))
    _add_column_if_missing("approvals", sa.Column("risk_level", sa.String(length=40), nullable=True))
    _add_column_if_missing("approvals", sa.Column("status", sa.String(length=40), nullable=True))
    _add_column_if_missing("approvals", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("approvals", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))

    _add_column_if_missing("undo_records", sa.Column("task_id", sa.String(length=36), nullable=True))
    _add_column_if_missing("undo_records", sa.Column("operation", sa.String(length=80), nullable=True))
    _add_column_if_missing("undo_records", sa.Column("source", sa.Text(), nullable=True))
    _add_column_if_missing("undo_records", sa.Column("destination", sa.Text(), nullable=True))
    _add_column_if_missing("undo_records", sa.Column("precondition", sa.JSON(), nullable=True))
    _add_column_if_missing("undo_records", sa.Column("postcondition", sa.JSON(), nullable=True))
    _add_column_if_missing("undo_records", sa.Column("backup_path", sa.Text(), nullable=True))
    _add_column_if_missing("undo_records", sa.Column("status", sa.String(length=40), nullable=True))
    _add_column_if_missing("undo_records", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("undo_records", sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    bind.exec_driver_sql(
        """
        UPDATE approvals
        SET
          task_id = COALESCE(task_id, (SELECT actions.task_id FROM actions WHERE actions.id = approvals.action_id)),
          tool_name = COALESCE(tool_name, exact_tool, 'filesystem.unknown'),
          normalized_arguments = COALESCE(normalized_arguments, exact_arguments, '{}'),
          risk_level = COALESCE(risk_level, 'HIGH_RISK'),
          status = COALESCE(status, CASE WHEN approved THEN 'APPROVED' ELSE 'PENDING' END),
          created_at = COALESCE(created_at, expires_at, CURRENT_TIMESTAMP)
        """
    )
    bind.exec_driver_sql(
        """
        UPDATE undo_records
        SET
          task_id = COALESCE(task_id, (SELECT actions.task_id FROM actions WHERE actions.id = undo_records.action_id)),
          operation = COALESCE(operation, undo_type),
          precondition = COALESCE(precondition, '{}'),
          postcondition = COALESCE(postcondition, '{}'),
          payload = COALESCE(payload, '{}'),
          status = COALESCE(status, CASE WHEN applied THEN 'APPLIED' ELSE 'PENDING' END),
          created_at = COALESCE(
            created_at,
            (
              SELECT tasks.created_at
              FROM tasks
              JOIN actions ON actions.task_id = tasks.id
              WHERE actions.id = undo_records.action_id
            ),
            CURRENT_TIMESTAMP
          )
        """
    )

    with op.batch_alter_table("approvals", recreate="always") as batch:
        batch.alter_column("task_id", existing_type=sa.String(length=36), nullable=False)
        batch.alter_column("tool_name", existing_type=sa.String(length=160), nullable=False)
        batch.alter_column("normalized_arguments", existing_type=sa.JSON(), nullable=False)
        batch.alter_column("risk_level", existing_type=sa.String(length=40), nullable=False)
        batch.alter_column("status", existing_type=sa.String(length=40), nullable=False)
        batch.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.create_foreign_key("fk_approvals_task_id_tasks", "tasks", ["task_id"], ["id"])

    with op.batch_alter_table("undo_records", recreate="always") as batch:
        batch.alter_column("task_id", existing_type=sa.String(length=36), nullable=False)
        batch.alter_column("operation", existing_type=sa.String(length=80), nullable=False)
        batch.alter_column("precondition", existing_type=sa.JSON(), nullable=False)
        batch.alter_column("postcondition", existing_type=sa.JSON(), nullable=False)
        batch.alter_column("payload", existing_type=sa.JSON(), nullable=False)
        batch.alter_column("status", existing_type=sa.String(length=40), nullable=False)
        batch.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.create_foreign_key("fk_undo_records_task_id_tasks", "tasks", ["task_id"], ["id"])


def downgrade() -> None:
    pass
