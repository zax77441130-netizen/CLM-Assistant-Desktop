"""capabilities and recovery bin

Revision ID: 0006_capabilities_recovery
Revises: 0005_reliable_task_execution
Create Date: 2026-08-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_capabilities_recovery"
down_revision = "0005_reliable_task_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capability_grants",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("capability", sa.String(length=120), nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_capability_grants_capability", "capability_grants", ["capability"])

    op.create_table(
        "batch_manifests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("plan_id", sa.String(length=36), sa.ForeignKey("plans.id"), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspace_grants.id"), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("arguments_hash", sa.String(length=128), nullable=False),
        sa.Column("manifest_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_batch_manifests_task_id", "batch_manifests", ["task_id"])
    op.create_index("ix_batch_manifests_workspace_id", "batch_manifests", ["workspace_id"])

    op.create_table(
        "batch_manifest_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("manifest_id", sa.String(length=36), sa.ForeignKey("batch_manifests.id"), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("destination", sa.Text(), nullable=True),
        sa.Column("source_hash", sa.String(length=128), nullable=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_batch_manifest_items_manifest_id", "batch_manifest_items", ["manifest_id"])

    op.create_table(
        "recovery_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspace_grants.id"), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("recovery_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=128), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_recovery_items_workspace_id", "recovery_items", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_recovery_items_workspace_id", table_name="recovery_items")
    op.drop_table("recovery_items")
    op.drop_index("ix_batch_manifest_items_manifest_id", table_name="batch_manifest_items")
    op.drop_table("batch_manifest_items")
    op.drop_index("ix_batch_manifests_workspace_id", table_name="batch_manifests")
    op.drop_index("ix_batch_manifests_task_id", table_name="batch_manifests")
    op.drop_table("batch_manifests")
    op.drop_index("ix_capability_grants_capability", table_name="capability_grants")
    op.drop_table("capability_grants")
