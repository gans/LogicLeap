from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from logicleap.domain.enums import (
    ActorKind,
    ContextAuthority,
    ContextStatus,
    EpicContextKind,
    EpicContextStatus,
    EvidenceKind,
    RequirementType,
    ReviewStatus,
    Severity,
    TaskState,
)


class Base(DeclarativeBase):
    pass


class IdentityMixin:
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VersionMixin:
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)


class Actor(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "actors"
    kind: Mapped[ActorKind] = mapped_column(Enum(ActorKind, name="actor_kind"))
    display_name: Mapped[str] = mapped_column(String(250))
    external_ref: Mapped[str | None] = mapped_column(String(500), unique=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, server_default="{}"
    )


class Epic(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "epics"
    title: Mapped[str] = mapped_column(String(250))
    summary: Mapped[str] = mapped_column(Text)
    problem_statement: Mapped[str] = mapped_column(Text)
    desired_outcome: Mapped[str] = mapped_column(Text)
    architect_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    created_by_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))


class Task(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "tasks"
    epic_id: Mapped[UUID] = mapped_column(ForeignKey("epics.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(250))
    summary: Mapped[str] = mapped_column(Text)
    objective: Mapped[str] = mapped_column(Text)
    state: Mapped[TaskState] = mapped_column(
        Enum(TaskState, name="task_state"), default=TaskState.DRAFT
    )
    blocked_from_state: Mapped[TaskState | None] = mapped_column(Enum(TaskState, name="task_state"))
    architect_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    created_by_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    __table_args__ = (
        CheckConstraint(
            "state = 'BLOCKED' OR blocked_from_state IS NULL", name="ck_task_blocked_from"
        ),
    )


class TaskActor(Base):
    __tablename__ = "task_actors"
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"), primary_key=True
    )
    actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("actors.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(100))
    added_by_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EpicContextEntry(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "epic_context_entries"
    epic_id: Mapped[UUID] = mapped_column(ForeignKey("epics.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[EpicContextKind] = mapped_column(Enum(EpicContextKind, name="epic_context_kind"))
    title: Mapped[str] = mapped_column(String(250))
    content: Mapped[str] = mapped_column(Text)
    authority: Mapped[ContextAuthority] = mapped_column(
        Enum(ContextAuthority, name="context_authority")
    )
    status: Mapped[EpicContextStatus] = mapped_column(
        Enum(EpicContextStatus, name="epic_context_status")
    )
    created_by_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    approved_by_actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("actors.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_context_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("epic_context_entries.id", ondelete="RESTRICT")
    )
    source_task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"))
    source_context_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("context_entries.id", ondelete="RESTRICT")
    )
    source_decision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("decisions.id", ondelete="RESTRICT")
    )
    source_evidence_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("evidence.id", ondelete="RESTRICT")
    )
    source_uri: Mapped[str | None] = mapped_column(String(2000))
    is_required_for_analysis: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    is_required_for_implementation: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    rejected_by_actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("actors.id", ondelete="RESTRICT")
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deprecation_reason: Mapped[str | None] = mapped_column(Text)
    deprecated_by_actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("actors.id", ondelete="RESTRICT")
    )
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "supersedes_context_id IS NULL OR supersedes_context_id <> id",
            name="ck_epic_context_not_self",
        ),
        CheckConstraint(
            "authority <> 'APPROVED' OR "
            "(approved_by_actor_id IS NOT NULL AND approved_at IS NOT NULL)",
            name="ck_epic_context_approval",
        ),
        CheckConstraint(
            "status <> 'REJECTED' OR (rejection_reason IS NOT NULL AND "
            "rejected_by_actor_id IS NOT NULL AND rejected_at IS NOT NULL)",
            name="ck_epic_context_rejection",
        ),
        CheckConstraint(
            "status <> 'DEPRECATED' OR (deprecation_reason IS NOT NULL AND "
            "deprecated_by_actor_id IS NOT NULL AND deprecated_at IS NOT NULL)",
            name="ck_epic_context_deprecation",
        ),
        Index("ix_epic_context_filter", "epic_id", "kind", "authority", "status"),
    )


class ContextConflict(Base, IdentityMixin, TimestampMixin):
    __tablename__ = "context_conflicts"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    epic_context_id: Mapped[UUID] = mapped_column(
        ForeignKey("epic_context_entries.id", ondelete="RESTRICT")
    )
    task_context_id: Mapped[UUID] = mapped_column(
        ForeignKey("context_entries.id", ondelete="RESTRICT")
    )
    reason: Mapped[str] = mapped_column(Text)
    created_by_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    __table_args__ = (
        UniqueConstraint(
            "task_id", "epic_context_id", "task_context_id", name="uq_context_conflict_pair"
        ),
    )


class Requirement(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "requirements"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    requirement_type: Mapped[RequirementType] = mapped_column(
        Enum(RequirementType, name="requirement_type")
    )
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="PROPOSED")
    created_by_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    __table_args__ = (
        CheckConstraint(
            "status IN ('PROPOSED','CONFIRMED','WITHDRAWN')", name="ck_requirement_status"
        ),
    )


class AcceptanceCriterion(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "acceptance_criteria"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    description: Mapped[str] = mapped_column(Text)
    verification_method: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="ACTIVE")
    created_by_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))


class ContextEntry(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "context_entries"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(250))
    content: Mapped[str] = mapped_column(Text)
    source_uri: Mapped[str | None] = mapped_column(String(2000))
    authority: Mapped[ContextAuthority] = mapped_column(
        Enum(ContextAuthority, name="context_authority")
    )
    status: Mapped[ContextStatus] = mapped_column(
        Enum(ContextStatus, name="context_status"), default=ContextStatus.ACTIVE
    )
    supersedes_context_entry_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("context_entries.id", ondelete="RESTRICT")
    )
    created_by_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    __table_args__ = (
        CheckConstraint(
            "supersedes_context_entry_id IS NULL OR supersedes_context_entry_id <> id",
            name="ck_context_not_self",
        ),
    )


class Question(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "questions"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    question: Mapped[str] = mapped_column(Text)
    is_blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text)
    impact_if_unanswered: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    asked_by_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    assigned_to_actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("actors.id", ondelete="RESTRICT")
    )
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','ANSWERED','WITHDRAWN')", name="ck_question_status"),
    )


class QuestionAnswer(Base, IdentityMixin):
    __tablename__ = "question_answers"
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("questions.id", ondelete="RESTRICT"), index=True
    )
    answer: Mapped[str] = mapped_column(Text)
    answered_by_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    supersedes_answer_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("question_answers.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Blocker(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "blockers"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    created_by_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    resolved_by_actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("actors.id", ondelete="RESTRICT")
    )
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','RESOLVED')", name="ck_blocker_status"),
        CheckConstraint(
            "status = 'OPEN' OR (resolution IS NOT NULL "
            "AND resolved_by_actor_id IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_blocker_resolution",
        ),
    )


class Decision(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "decisions"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(250))
    proposal: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="PROPOSED")
    proposed_by_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    approved_by_actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("actors.id", ondelete="RESTRICT")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_decision_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("decisions.id", ondelete="RESTRICT")
    )
    __table_args__ = (
        CheckConstraint(
            "status IN ('PROPOSED','APPROVED','REJECTED','SUPERSEDED')", name="ck_decision_status"
        ),
    )


class ImplementationRun(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "implementation_runs"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30))
    reference_uri: Mapped[str | None] = mapped_column(String(2000))
    epic_context_version_used: Mapped[int | None] = mapped_column(Integer)
    registered_by_actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("actors.id", ondelete="RESTRICT")
    )


class Evidence(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "evidence"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    implementation_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("implementation_runs.id", ondelete="RESTRICT")
    )
    kind: Mapped[EvidenceKind] = mapped_column(Enum(EvidenceKind, name="evidence_kind"))
    title: Mapped[str] = mapped_column(String(250))
    description: Mapped[str] = mapped_column(Text)
    reference_uri: Mapped[str | None] = mapped_column(String(2000))
    passed: Mapped[bool | None] = mapped_column(Boolean)
    epic_context_version_used: Mapped[int | None] = mapped_column(Integer)
    registered_by_actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("actors.id", ondelete="RESTRICT")
    )


class Review(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "reviews"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[ReviewStatus] = mapped_column(Enum(ReviewStatus, name="review_status"))
    reviewer_actor_id: Mapped[UUID] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    epic_context_version_used: Mapped[int | None] = mapped_column(Integer)


class ReviewFinding(Base, IdentityMixin, TimestampMixin, VersionMixin):
    __tablename__ = "review_findings"
    review_id: Mapped[UUID] = mapped_column(
        ForeignKey("reviews.id", ondelete="RESTRICT"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[Severity] = mapped_column(Enum(Severity, name="severity"))
    is_blocking: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    resolution: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','RESOLVED')", name="ck_review_finding_status"),
    )


class TaskStateTransition(Base, IdentityMixin):
    __tablename__ = "task_state_transitions"
    task_id: Mapped[UUID] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), index=True)
    from_state: Mapped[TaskState] = mapped_column(Enum(TaskState, name="task_state"))
    to_state: Mapped[TaskState] = mapped_column(Enum(TaskState, name="task_state"))
    requested_by_actor_id: Mapped[UUID] = mapped_column(
        ForeignKey("actors.id", ondelete="RESTRICT")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    task_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DomainEvent(Base, IdentityMixin):
    __tablename__ = "domain_events"
    aggregate_type: Mapped[str] = mapped_column(String(100))
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), index=True)
    aggregate_sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(150))
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("actors.id", ondelete="RESTRICT"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    correlation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    causation_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    __table_args__ = (
        UniqueConstraint(
            "aggregate_type",
            "aggregate_id",
            "aggregate_sequence",
            name="uq_event_aggregate_sequence",
        ),
        CheckConstraint("aggregate_sequence > 0", name="ck_event_sequence_positive"),
        Index("ix_domain_event_timeline", "aggregate_id", "occurred_at", "id"),
    )
