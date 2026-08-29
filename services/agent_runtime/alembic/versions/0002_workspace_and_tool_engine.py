"""workspace and tool engine

Revision ID: 0002_workspace_tool
Revises: 0001_initial
Create Date: 2026-08-29
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_workspace_tool"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_grants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("permission_profile", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("approvals", sa.Column("task_id", sa.String(length=36), nullable=True))
    op.add_column("approvals", sa.Column("tool_name", sa.String(length=160), nullable=True))
    op.add_column("approvals", sa.Column("normalized_arguments", sa.JSON(), nullable=True))
    op.add_column("approvals", sa.Column("risk_level", sa.String(length=40), nullable=True))
    op.add_column("approvals", sa.Column("status", sa.String(length=40), nullable=True))
    op.add_column("approvals", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("approvals", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("undo_records", sa.Column("task_id", sa.String(length=36), nullable=True))
    op.add_column("undo_records", sa.Column("operation", sa.String(length=80), nullable=True))
    op.add_column("undo_records", sa.Column("source", sa.Text(), nullable=True))
    op.add_column("undo_records", sa.Column("destination", sa.Text(), nullable=True))
    op.add_column("undo_records", sa.Column("precondition", sa.JSON(), nullable=True))
    op.add_column("undo_records", sa.Column("postcondition", sa.JSON(), nullable=True))
    op.add_column("undo_records", sa.Column("backup_path", sa.Text(), nullable=True))
    op.add_column("undo_records", sa.Column("status", sa.String(length=40), nullable=True))
    op.add_column("undo_records", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("undo_records", sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for column in ["applied_at", "created_at", "status", "backup_path", "postcondition", "precondition", "destination", "source", "operation", "task_id"]:
        op.drop_column("undo_records", column)
    for column in ["decided_at", "created_at", "status", "risk_level", "normalized_arguments", "tool_name", "task_id"]:
        op.drop_column("approvals", column)
    op.drop_table("workspace_grants")
