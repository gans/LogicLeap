"""epic context

Revision ID: a232c1e79ee6
Revises: 32d7bbfd4d03
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a232c1e79ee6"
down_revision: str | None = "32d7bbfd4d03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


epic_context_kind = postgresql.ENUM(
    "BUSINESS",
    "ARCHITECTURE",
    "DOMAIN",
    "CODEBASE",
    "CONSTRAINT",
    "SECURITY",
    "ENVIRONMENT",
    "OPERATIONS",
    "TESTING",
    "DEPLOYMENT",
    "LESSON_LEARNED",
    "DECISION_SUMMARY",
    "OTHER",
    name="epic_context_kind",
    create_type=False,
)
epic_context_status = postgresql.ENUM(
    "ACTIVE",
    "SUPERSEDED",
    "DEPRECATED",
    "REJECTED",
    name="epic_context_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    epic_context_kind.create(bind, checkfirst=True)
    epic_context_status.create(bind, checkfirst=True)
    op.create_table(
        "epic_context_entries",
        sa.Column("epic_id", sa.UUID(), nullable=False),
        sa.Column("kind", epic_context_kind, nullable=False),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "authority",
            postgresql.ENUM(name="context_authority", create_type=False),
            nullable=False,
        ),
        sa.Column("status", epic_context_status, nullable=False),
        sa.Column("created_by_actor_id", sa.UUID(), nullable=False),
        sa.Column("approved_by_actor_id", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_context_id", sa.UUID(), nullable=True),
        sa.Column("source_task_id", sa.UUID(), nullable=True),
        sa.Column("source_context_id", sa.UUID(), nullable=True),
        sa.Column("source_decision_id", sa.UUID(), nullable=True),
        sa.Column("source_evidence_id", sa.UUID(), nullable=True),
        sa.Column("source_uri", sa.String(length=2000), nullable=True),
        sa.Column("is_required_for_analysis", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "is_required_for_implementation", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("rejected_by_actor_id", sa.UUID(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deprecation_reason", sa.Text(), nullable=True),
        sa.Column("deprecated_by_actor_id", sa.UUID(), nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "supersedes_context_id IS NULL OR supersedes_context_id <> id",
            name="ck_epic_context_not_self",
        ),
        sa.CheckConstraint(
            "authority <> 'APPROVED' OR "
            "(approved_by_actor_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_epic_context_approval",
        ),
        sa.CheckConstraint(
            "status <> 'REJECTED' OR (rejection_reason IS NOT NULL AND "
            "rejected_by_actor_id IS NOT NULL AND rejected_at IS NOT NULL)",
            name="ck_epic_context_rejection",
        ),
        sa.CheckConstraint(
            "status <> 'DEPRECATED' OR (deprecation_reason IS NOT NULL AND "
            "deprecated_by_actor_id IS NOT NULL AND deprecated_at IS NOT NULL)",
            name="ck_epic_context_deprecation",
        ),
        sa.ForeignKeyConstraint(["approved_by_actor_id"], ["actors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_actor_id"], ["actors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deprecated_by_actor_id"], ["actors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["epic_id"], ["epics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rejected_by_actor_id"], ["actors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_context_id"], ["context_entries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_decision_id"], ["decisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_evidence_id"], ["evidence.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["supersedes_context_id"], ["epic_context_entries.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_epic_context_entries_epic_id", "epic_context_entries", ["epic_id"])
    op.create_index(
        "ix_epic_context_filter", "epic_context_entries", ["epic_id", "kind", "authority", "status"]
    )
    op.create_table(
        "context_conflicts",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("epic_context_id", sa.UUID(), nullable=False),
        sa.Column("task_context_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_actor_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_actor_id"], ["actors.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["epic_context_id"], ["epic_context_entries.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["task_context_id"], ["context_entries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id", "epic_context_id", "task_context_id", name="uq_context_conflict_pair"
        ),
    )
    op.create_index("ix_context_conflicts_task_id", "context_conflicts", ["task_id"])
    op.add_column("evidence", sa.Column("epic_context_version_used", sa.Integer(), nullable=True))
    op.add_column(
        "implementation_runs", sa.Column("epic_context_version_used", sa.Integer(), nullable=True)
    )
    op.add_column("reviews", sa.Column("epic_context_version_used", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("reviews", "epic_context_version_used")
    op.drop_column("implementation_runs", "epic_context_version_used")
    op.drop_column("evidence", "epic_context_version_used")
    op.drop_index("ix_context_conflicts_task_id", table_name="context_conflicts")
    op.drop_table("context_conflicts")
    op.drop_index("ix_epic_context_filter", table_name="epic_context_entries")
    op.drop_index("ix_epic_context_entries_epic_id", table_name="epic_context_entries")
    op.drop_table("epic_context_entries")
    epic_context_status.drop(op.get_bind(), checkfirst=True)
    epic_context_kind.drop(op.get_bind(), checkfirst=True)
