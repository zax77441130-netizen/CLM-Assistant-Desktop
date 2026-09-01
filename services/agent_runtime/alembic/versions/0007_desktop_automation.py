"""desktop automation

Revision ID: 0007_desktop_automation
Revises: 0006_capabilities_recovery
Create Date: 2026-09-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_desktop_automation"
down_revision = "0006_capabilities_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "desktop_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("app_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "window_targets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("desktop_sessions.id"), nullable=False),
        sa.Column("app_id", sa.String(length=80), nullable=False),
        sa.Column("executable", sa.String(length=240), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column("process_creation_time", sa.String(length=120), nullable=False),
        sa.Column("window_handle", sa.Integer(), nullable=False),
        sa.Column("runtime_id", sa.String(length=240), nullable=False),
        sa.Column("target_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("title_preview", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_window_targets_session_id", "window_targets", ["session_id"])
    op.create_index("ix_window_targets_fingerprint", "window_targets", ["target_fingerprint"])
    op.create_table(
        "automation_actions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("action_id", sa.String(length=36), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("window_target_id", sa.String(length=36), sa.ForeignKey("window_targets.id"), nullable=True),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("postcondition", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_automation_actions_task_id", "automation_actions", ["task_id"])
    op.create_table(
        "automation_profile_grants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("app_id", sa.String(length=80), nullable=False),
        sa.Column("profile", sa.String(length=80), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "screen_artifacts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("artifact_hash", sa.String(length=128), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_screen_artifacts_task_id", "screen_artifacts", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_screen_artifacts_task_id", table_name="screen_artifacts")
    op.drop_table("screen_artifacts")
    op.drop_table("automation_profile_grants")
    op.drop_index("ix_automation_actions_task_id", table_name="automation_actions")
    op.drop_table("automation_actions")
    op.drop_index("ix_window_targets_fingerprint", table_name="window_targets")
    op.drop_index("ix_window_targets_session_id", table_name="window_targets")
    op.drop_table("window_targets")
    op.drop_table("desktop_sessions")
