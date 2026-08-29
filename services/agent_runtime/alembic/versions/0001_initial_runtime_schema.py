"""initial runtime schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-29
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("tasks", sa.Column("id", sa.String(length=36), primary_key=True), sa.Column("title", sa.String(length=240), nullable=False), sa.Column("state", sa.String(length=14), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("task_steps", sa.Column("id", sa.String(length=36), primary_key=True), sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False), sa.Column("title", sa.String(length=240), nullable=False), sa.Column("state", sa.String(length=14), nullable=False), sa.Column("sort_order", sa.Integer(), nullable=False))
    op.create_table("actions", sa.Column("id", sa.String(length=36), primary_key=True), sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False), sa.Column("tool_name", sa.String(length=160), nullable=False), sa.Column("arguments_hash", sa.String(length=128), nullable=False), sa.Column("risk_level", sa.String(length=40), nullable=False), sa.Column("status", sa.String(length=40), nullable=False))
    op.create_table("approvals", sa.Column("id", sa.String(length=36), primary_key=True), sa.Column("action_id", sa.String(length=36), sa.ForeignKey("actions.id"), nullable=False), sa.Column("exact_tool", sa.String(length=160), nullable=False), sa.Column("exact_arguments", sa.JSON(), nullable=False), sa.Column("argument_hash", sa.String(length=128), nullable=False), sa.Column("working_directory", sa.Text(), nullable=False), sa.Column("risk_reason", sa.Text(), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("approved", sa.Boolean(), nullable=False))
    op.create_table("observations", sa.Column("id", sa.String(length=36), primary_key=True), sa.Column("action_id", sa.String(length=36), sa.ForeignKey("actions.id"), nullable=False), sa.Column("summary", sa.Text(), nullable=False), sa.Column("evidence", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("artifacts", sa.Column("id", sa.String(length=36), primary_key=True), sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False), sa.Column("path", sa.Text(), nullable=False), sa.Column("kind", sa.String(length=80), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("undo_records", sa.Column("id", sa.String(length=36), primary_key=True), sa.Column("action_id", sa.String(length=36), sa.ForeignKey("actions.id"), nullable=False), sa.Column("undo_type", sa.String(length=80), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("applied", sa.Boolean(), nullable=False))
    op.create_table("audit_events", sa.Column("id", sa.String(length=36), primary_key=True), sa.Column("event_type", sa.String(length=120), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("scheduled_tasks", sa.Column("id", sa.String(length=36), primary_key=True), sa.Column("task_template", sa.JSON(), nullable=False), sa.Column("cron", sa.String(length=120), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False))


def downgrade() -> None:
    op.drop_table("scheduled_tasks")
    op.drop_table("audit_events")
    op.drop_table("undo_records")
    op.drop_table("artifacts")
    op.drop_table("observations")
    op.drop_table("approvals")
    op.drop_table("actions")
    op.drop_table("task_steps")
    op.drop_table("tasks")
