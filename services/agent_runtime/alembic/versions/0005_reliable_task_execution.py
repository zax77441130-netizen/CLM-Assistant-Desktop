"""reliable task execution

Revision ID: 0005_reliable_task_execution
Revises: 0004_agent_orchestration
Create Date: 2026-08-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_reliable_task_execution"
down_revision = "0004_agent_orchestration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("workspace_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("idempotency_key", sa.String(length=120), nullable=True))
        batch.create_foreign_key("fk_tasks_workspace_id", "workspace_grants", ["workspace_id"], ["id"])
        batch.create_index("ix_tasks_workspace_id", ["workspace_id"])
        batch.create_index("ix_tasks_idempotency_key", ["idempotency_key"], unique=True)

    with op.batch_alter_table("actions") as batch:
        batch.add_column(sa.Column("workspace_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("target_path", sa.Text(), nullable=True))
        batch.create_foreign_key("fk_actions_workspace_id", "workspace_grants", ["workspace_id"], ["id"])
        batch.create_index("ix_actions_workspace_id", ["workspace_id"])

    with op.batch_alter_table("observations") as batch:
        batch.add_column(sa.Column("task_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("workspace_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key("fk_observations_task_id", "tasks", ["task_id"], ["id"])
        batch.create_foreign_key("fk_observations_workspace_id", "workspace_grants", ["workspace_id"], ["id"])
        batch.create_index("ix_observations_task_id", ["task_id"])
        batch.create_index("ix_observations_workspace_id", ["workspace_id"])

    with op.batch_alter_table("plans") as batch:
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("parent_plan_id", sa.String(length=36), nullable=True))
        batch.create_index("ix_plans_task_id", ["task_id"])

    with op.batch_alter_table("plan_steps") as batch:
        batch.add_column(sa.Column("workspace_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("depends_on_step_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("output_size", sa.Integer(), nullable=False, server_default="0"))
        batch.create_foreign_key("fk_plan_steps_workspace_id", "workspace_grants", ["workspace_id"], ["id"])
        batch.create_index("ix_plan_steps_plan_id", ["plan_id"])
        batch.create_index("ix_plan_steps_task_id", ["task_id"])
        batch.create_index("ix_plan_steps_workspace_id", ["workspace_id"])

    op.create_table(
        "task_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("from_state", sa.String(length=40), nullable=True),
        sa.Column("to_state", sa.String(length=40), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])

    op.create_table(
        "execution_leases",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("workspace_id", sa.String(length=36), sa.ForeignKey("workspace_grants.id"), nullable=False),
        sa.Column("path_key", sa.Text(), nullable=False),
        sa.Column("holder_task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_execution_leases_workspace_path", "execution_leases", ["workspace_id", "path_key"])

    op.create_table(
        "idempotency_records",
        sa.Column("key", sa.String(length=120), primary_key=True),
        sa.Column("request_hash", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_idempotency_records_task_id", "idempotency_records", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_records_task_id", table_name="idempotency_records")
    op.drop_table("idempotency_records")
    op.drop_index("ix_execution_leases_workspace_path", table_name="execution_leases")
    op.drop_table("execution_leases")
    op.drop_index("ix_task_events_task_id", table_name="task_events")
    op.drop_table("task_events")

    with op.batch_alter_table("plan_steps") as batch:
        batch.drop_index("ix_plan_steps_workspace_id")
        batch.drop_index("ix_plan_steps_task_id")
        batch.drop_index("ix_plan_steps_plan_id")
        batch.drop_constraint("fk_plan_steps_workspace_id", type_="foreignkey")
        batch.drop_column("output_size")
        batch.drop_column("max_attempts")
        batch.drop_column("retry_count")
        batch.drop_column("depends_on_step_id")
        batch.drop_column("workspace_id")

    with op.batch_alter_table("plans") as batch:
        batch.drop_index("ix_plans_task_id")
        batch.drop_column("parent_plan_id")
        batch.drop_column("version")

    with op.batch_alter_table("observations") as batch:
        batch.drop_index("ix_observations_workspace_id")
        batch.drop_index("ix_observations_task_id")
        batch.drop_constraint("fk_observations_workspace_id", type_="foreignkey")
        batch.drop_constraint("fk_observations_task_id", type_="foreignkey")
        batch.drop_column("workspace_id")
        batch.drop_column("task_id")

    with op.batch_alter_table("actions") as batch:
        batch.drop_index("ix_actions_workspace_id")
        batch.drop_constraint("fk_actions_workspace_id", type_="foreignkey")
        batch.drop_column("target_path")
        batch.drop_column("workspace_id")

    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_idempotency_key")
        batch.drop_index("ix_tasks_workspace_id")
        batch.drop_constraint("fk_tasks_workspace_id", type_="foreignkey")
        batch.drop_column("idempotency_key")
        batch.drop_column("workspace_id")
