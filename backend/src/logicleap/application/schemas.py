from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from logicleap.domain.enums import (
    ContextAuthority,
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


class EvidenceCreate(TaskCommand):
    kind: EvidenceKind
    title: str
    description: str
    reference_uri: str | None = None
    passed: bool | None = None
    implementation_run_id: UUID | None = None


class ReviewCreate(TaskCommand):
    summary: str
    status: ReviewStatus
    reviewer_actor_id: UUID


class ReviewFindingCreate(BaseModel):
    acting_actor_id: UUID
    expected_version: int
    description: str
    severity: Severity
    is_blocking: bool = False
