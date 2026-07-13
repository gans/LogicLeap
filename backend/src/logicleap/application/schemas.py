from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from logicleap.domain.enums import (
    ContextAuthority,
    EpicContextKind,
    EpicContextStatus,
    EvidenceKind,
    RequirementType,
    ReviewStatus,
    Severity,
    TaskState,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ActorCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=250)
    kind: str = "HUMAN"
    external_ref: str | None = None


class ActorRead(ORMModel):
    id: UUID
    display_name: str
    kind: str


class EpicCreate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    summary: str = Field(min_length=1)
    problem_statement: str = Field(min_length=1)
    desired_outcome: str = Field(min_length=1)
    architect_actor_id: UUID
    acting_actor_id: UUID


class EpicRead(ORMModel):
    id: UUID
    title: str
    summary: str
    problem_statement: str
    desired_outcome: str
    architect_actor_id: UUID
    version: int
    created_at: datetime


class EpicContextRead(ORMModel):
    id: UUID
    epic_id: UUID
    kind: EpicContextKind
    title: str
    content: str
    authority: ContextAuthority
    status: EpicContextStatus
    created_by_actor_id: UUID
    approved_by_actor_id: UUID | None
    approved_at: datetime | None
    supersedes_context_id: UUID | None
    source_task_id: UUID | None
    source_context_id: UUID | None
    source_decision_id: UUID | None
    source_evidence_id: UUID | None
    source_uri: str | None
    is_required_for_analysis: bool
    is_required_for_implementation: bool
    rejection_reason: str | None
    rejected_by_actor_id: UUID | None
    rejected_at: datetime | None
    deprecation_reason: str | None
    deprecated_by_actor_id: UUID | None
    deprecated_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class EpicContextCommand(BaseModel):
    acting_actor_id: UUID
    expected_epic_version: int


class EpicContextCreate(EpicContextCommand):
    kind: EpicContextKind
    title: str = Field(min_length=1, max_length=250)
    content: str = Field(min_length=1)
    source_uri: str | None = None
    supersedes_context_id: UUID | None = None
    is_required_for_analysis: bool = False
    is_required_for_implementation: bool = False
    approve_immediately: bool = False


class EpicContextReplacement(EpicContextCommand):
    kind: EpicContextKind | None = None
    title: str = Field(min_length=1, max_length=250)
    content: str = Field(min_length=1)
    source_uri: str | None = None
    is_required_for_analysis: bool | None = None
    is_required_for_implementation: bool | None = None


class EpicContextReview(EpicContextCommand):
    reason: str | None = None


class EpicContextDeprecate(EpicContextCommand):
    reason: str = Field(min_length=1)


class PromoteTaskLearning(EpicContextCreate):
    task_id: UUID
    source_context_id: UUID | None = None
    source_decision_id: UUID | None = None
    source_evidence_id: UUID | None = None


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    summary: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    architect_actor_id: UUID | None = None
    acting_actor_id: UUID


class TaskRead(ORMModel):
    id: UUID
    epic_id: UUID
    title: str
    summary: str
    objective: str
    state: TaskState
    blocked_from_state: TaskState | None
    architect_actor_id: UUID
    version: int
    created_at: datetime


class TaskCommand(BaseModel):
    acting_actor_id: UUID
    expected_version: int


class ActorAssignment(TaskCommand):
    actor_id: UUID
    role: str = Field(min_length=1, max_length=100)


class ContextCreate(TaskCommand):
    kind: str
    title: str
    content: str
    source_uri: str | None = None
    authority: ContextAuthority
    supersedes_context_entry_id: UUID | None = None


class ContextConflictCreate(TaskCommand):
    epic_context_id: UUID
    task_context_id: UUID
    reason: str = Field(min_length=1)


class RequirementCreate(TaskCommand):
    requirement_type: RequirementType
    description: str
    status: str = "PROPOSED"


class AcceptanceCriterionCreate(TaskCommand):
    description: str
    verification_method: str | None = None


class QuestionCreate(TaskCommand):
    question: str
    is_blocking: bool
    reason: str
    impact_if_unanswered: str
    assigned_to_actor_id: UUID | None = None


class AnswerCreate(BaseModel):
    answer: str
    acting_actor_id: UUID
    supersedes_answer_id: UUID | None = None


class BlockerCreate(TaskCommand):
    description: str


class ResolveBlocker(BaseModel):
    resolution: str
    acting_actor_id: UUID
    expected_version: int


class DecisionCreate(TaskCommand):
    title: str
    proposal: str
    rationale: str
    is_required: bool = False
    supersedes_decision_id: UUID | None = None


class ApproveDecision(BaseModel):
    acting_actor_id: UUID
    expected_version: int


class TransitionRequest(TaskCommand):
    target_state: TaskState
    reason: str | None = None


class ImplementationRunCreate(TaskCommand):
    summary: str
    status: str
    reference_uri: str | None = None
    epic_context_version_used: int | None = None


class EvidenceCreate(TaskCommand):
    kind: EvidenceKind
    title: str
    description: str
    reference_uri: str | None = None
    passed: bool | None = None
    implementation_run_id: UUID | None = None
    epic_context_version_used: int | None = None


class ReviewCreate(TaskCommand):
    summary: str
    status: ReviewStatus
    reviewer_actor_id: UUID
    epic_context_version_used: int | None = None


class ReviewFindingCreate(BaseModel):
    acting_actor_id: UUID
    expected_version: int
    description: str
    severity: Severity
    is_blocking: bool = False
