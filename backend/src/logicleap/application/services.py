from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from logicleap.application import schemas
from logicleap.domain.enums import (
    ActorKind,
    ContextAuthority,
    EpicContextKind,
    EpicContextStatus,
    EvidenceKind,
    ReviewStatus,
    Severity,
    TaskState,
)
from logicleap.domain.policies.readiness import ReadinessFacts, ReadinessResult, evaluate_readiness
from logicleap.domain.policies.transitions import allowed_transitions, validate_transition
from logicleap.infrastructure.persistence import models


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class PolicyError(Exception):
    pass


def _get[ModelT: models.Base](session: Session, model: type[ModelT], entity_id: UUID) -> ModelT:
    entity = session.get(model, entity_id)
    if entity is None:
        raise NotFoundError(f"{model.__name__} not found")
    return entity


def _task(session: Session, task_id: UUID, expected_version: int | None = None) -> models.Task:
    task = _get(session, models.Task, task_id)
    if expected_version is not None and task.version != expected_version:
        raise ConflictError(
            f"Expected version {expected_version}, current version is {task.version}"
        )
    return task


def _epic(session: Session, epic_id: UUID, expected_version: int | None = None) -> models.Epic:
    epic = session.scalar(select(models.Epic).where(models.Epic.id == epic_id).with_for_update())
    if epic is None:
        raise NotFoundError("Epic not found")
    if expected_version is not None and epic.version != expected_version:
        raise ConflictError(
            f"Expected epic version {expected_version}, current version is {epic.version}"
        )
    return epic


def _event(
    session: Session,
    aggregate_type: str,
    aggregate_id: UUID,
    sequence: int,
    event_type: str,
    actor_id: UUID | None,
    payload: dict[str, Any],
) -> None:
    session.add(
        models.DomainEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_sequence=sequence,
            event_type=event_type,
            actor_id=actor_id,
            payload=payload,
        )
    )


def _mutate_task(
    session: Session, task: models.Task, event_type: str, actor_id: UUID, payload: dict[str, Any]
) -> None:
    task.version += 1
    _event(session, "Task", task.id, task.version, event_type, actor_id, payload)


def _mutate_epic(
    session: Session, epic: models.Epic, event_type: str, actor_id: UUID, payload: dict[str, Any]
) -> None:
    epic.version += 1
    _event(session, "EPIC", epic.id, epic.version, event_type, actor_id, payload)


def _require_epic_architect(epic: models.Epic, actor_id: UUID) -> None:
    if actor_id != epic.architect_actor_id:
        raise PolicyError("Only the epic architect may perform this action")


def _epic_context(session: Session, epic_id: UUID, context_id: UUID) -> models.EpicContextEntry:
    entry = _get(session, models.EpicContextEntry, context_id)
    if entry.epic_id != epic_id:
        raise PolicyError("Epic context entry does not belong to this epic")
    return entry


def _validate_supersedes(
    session: Session, epic_id: UUID, supersedes_id: UUID | None, new_id: UUID | None = None
) -> models.EpicContextEntry | None:
    if supersedes_id is None:
        return None
    if new_id is not None and supersedes_id == new_id:
        raise PolicyError("An epic context entry cannot supersede itself")
    previous = _epic_context(session, epic_id, supersedes_id)
    if previous.status is EpicContextStatus.REJECTED:
        raise PolicyError("A rejected proposal cannot be superseded")
    seen = {new_id} if new_id else set()
    cursor: models.EpicContextEntry | None = previous
    while cursor is not None:
        if cursor.id in seen:
            raise PolicyError("Epic context superseding cycle detected")
        seen.add(cursor.id)
        cursor = (
            session.get(models.EpicContextEntry, cursor.supersedes_context_id)
            if cursor.supersedes_context_id
            else None
        )
        if cursor is not None and cursor.epic_id != epic_id:
            raise PolicyError("Superseding chain crosses epic boundaries")
    return previous


def create_epic_context(
    session: Session, epic_id: UUID, command: schemas.EpicContextCreate
) -> models.EpicContextEntry:
    epic = _epic(session, epic_id, command.expected_epic_version)
    _get(session, models.Actor, command.acting_actor_id)
    superseded = _validate_supersedes(session, epic_id, command.supersedes_context_id)
    immediate = command.approve_immediately
    if immediate:
        _require_epic_architect(epic, command.acting_actor_id)
        if superseded is not None and superseded.status is not EpicContextStatus.ACTIVE:
            raise PolicyError("The context being replaced is no longer active")
    now = utcnow() if immediate else None
    entry = models.EpicContextEntry(
        epic_id=epic_id,
        kind=command.kind,
        title=command.title,
        content=command.content,
        authority=ContextAuthority.APPROVED if immediate else ContextAuthority.PROPOSED,
        status=EpicContextStatus.ACTIVE,
        created_by_actor_id=command.acting_actor_id,
        approved_by_actor_id=command.acting_actor_id if immediate else None,
        approved_at=now,
        supersedes_context_id=command.supersedes_context_id,
        source_uri=command.source_uri,
        is_required_for_analysis=command.is_required_for_analysis,
        is_required_for_implementation=command.is_required_for_implementation,
    )
    session.add(entry)
    session.flush()
    _mutate_epic(
        session,
        epic,
        "EpicContextApproved" if immediate else "EpicContextProposed",
        command.acting_actor_id,
        {"context_id": str(entry.id), "kind": entry.kind, "title": entry.title},
    )
    if immediate and entry.supersedes_context_id:
        previous = _epic_context(session, epic_id, entry.supersedes_context_id)
        previous.status = EpicContextStatus.SUPERSEDED
        previous.version += 1
        _mutate_epic(
            session,
            epic,
            "EpicContextSuperseded",
            command.acting_actor_id,
            {"context_id": str(previous.id), "replacement_context_id": str(entry.id)},
        )
    session.commit()
    session.refresh(entry)
    return entry


def propose_epic_context_replacement(
    session: Session,
    epic_id: UUID,
    context_id: UUID,
    command: schemas.EpicContextReplacement,
) -> models.EpicContextEntry:
    current = _epic_context(session, epic_id, context_id)
    if current.status is not EpicContextStatus.ACTIVE:
        raise PolicyError("Only active epic context can be improved")
    return create_epic_context(
        session,
        epic_id,
        schemas.EpicContextCreate(
            acting_actor_id=command.acting_actor_id,
            expected_epic_version=command.expected_epic_version,
            kind=command.kind or current.kind,
            title=command.title,
            content=command.content,
            source_uri=command.source_uri,
            supersedes_context_id=current.id,
            is_required_for_analysis=(
                current.is_required_for_analysis
                if command.is_required_for_analysis is None
                else command.is_required_for_analysis
            ),
            is_required_for_implementation=(
                current.is_required_for_implementation
                if command.is_required_for_implementation is None
                else command.is_required_for_implementation
            ),
        ),
    )


def approve_epic_context(
    session: Session, epic_id: UUID, context_id: UUID, command: schemas.EpicContextReview
) -> models.EpicContextEntry:
    epic = _epic(session, epic_id, command.expected_epic_version)
    _require_epic_architect(epic, command.acting_actor_id)
    entry = _epic_context(session, epic_id, context_id)
    if (
        entry.authority is not ContextAuthority.PROPOSED
        or entry.status is not EpicContextStatus.ACTIVE
    ):
        raise PolicyError("Only active proposed context may be approved")
    previous = _validate_supersedes(session, epic_id, entry.supersedes_context_id, entry.id)
    if previous is not None:
        if previous.status is not EpicContextStatus.ACTIVE:
            raise PolicyError("The context being replaced is no longer active")
        previous.status = EpicContextStatus.SUPERSEDED
        previous.version += 1
        _mutate_epic(
            session,
            epic,
            "EpicContextSuperseded",
            command.acting_actor_id,
            {"context_id": str(previous.id), "replacement_context_id": str(entry.id)},
        )
    entry.authority = ContextAuthority.APPROVED
    entry.approved_by_actor_id = command.acting_actor_id
    entry.approved_at = utcnow()
    entry.version += 1
    _mutate_epic(
        session,
        epic,
        "EpicContextApproved",
        command.acting_actor_id,
        {"context_id": str(entry.id)},
    )
    session.commit()
    session.refresh(entry)
    return entry


def reject_epic_context(
    session: Session, epic_id: UUID, context_id: UUID, command: schemas.EpicContextReview
) -> models.EpicContextEntry:
    epic = _epic(session, epic_id, command.expected_epic_version)
    _require_epic_architect(epic, command.acting_actor_id)
    entry = _epic_context(session, epic_id, context_id)
    if (
        entry.authority is not ContextAuthority.PROPOSED
        or entry.status is not EpicContextStatus.ACTIVE
    ):
        raise PolicyError("Only active proposed context may be rejected")
    if not command.reason or not command.reason.strip():
        raise PolicyError("A rejection reason is required")
    entry.status = EpicContextStatus.REJECTED
    entry.rejection_reason = command.reason
    entry.rejected_by_actor_id = command.acting_actor_id
    entry.rejected_at = utcnow()
    entry.version += 1
    _mutate_epic(
        session,
        epic,
        "EpicContextRejected",
        command.acting_actor_id,
        {"context_id": str(entry.id), "reason": command.reason},
    )
    session.commit()
    session.refresh(entry)
    return entry


def deprecate_epic_context(
    session: Session, epic_id: UUID, context_id: UUID, command: schemas.EpicContextDeprecate
) -> models.EpicContextEntry:
    epic = _epic(session, epic_id, command.expected_epic_version)
    _require_epic_architect(epic, command.acting_actor_id)
    entry = _epic_context(session, epic_id, context_id)
    if entry.status is not EpicContextStatus.ACTIVE or entry.authority not in {
        ContextAuthority.APPROVED,
        ContextAuthority.AUTHORITATIVE,
    }:
        raise PolicyError("Only active approved context may be deprecated")
    entry.status = EpicContextStatus.DEPRECATED
    entry.deprecation_reason = command.reason
    entry.deprecated_by_actor_id = command.acting_actor_id
    entry.deprecated_at = utcnow()
    entry.version += 1
    _mutate_epic(
        session,
        epic,
        "EpicContextDeprecated",
        command.acting_actor_id,
        {"context_id": str(entry.id), "reason": command.reason},
    )
    session.commit()
    session.refresh(entry)
    return entry


def promote_task_learning(
    session: Session, epic_id: UUID, command: schemas.PromoteTaskLearning
) -> models.EpicContextEntry:
    task = _task(session, command.task_id)
    if task.epic_id != epic_id:
        raise PolicyError("Task does not belong to this epic")
    epic = _epic(session, epic_id, command.expected_epic_version)
    participant = session.get(models.TaskActor, (task.id, command.acting_actor_id))
    if command.acting_actor_id != epic.architect_actor_id and participant is None:
        raise PolicyError("Actor must participate in the task or be the epic architect")
    source_context = (
        _get(session, models.ContextEntry, command.source_context_id)
        if command.source_context_id
        else None
    )
    source_decision = (
        _get(session, models.Decision, command.source_decision_id)
        if command.source_decision_id
        else None
    )
    source_evidence = (
        _get(session, models.Evidence, command.source_evidence_id)
        if command.source_evidence_id
        else None
    )
    if any(
        source is not None and source.task_id != task.id
        for source in (source_context, source_decision, source_evidence)
    ):
        raise PolicyError("Referenced task entity does not belong to the source task")
    if command.source_decision_id is not None and (
        source_decision is None or source_decision.status != "APPROVED"
    ):
        raise PolicyError("Only an approved decision may be promoted")
    superseded = _validate_supersedes(session, epic_id, command.supersedes_context_id)
    if command.approve_immediately:
        _require_epic_architect(epic, command.acting_actor_id)
        if superseded is not None and superseded.status is not EpicContextStatus.ACTIVE:
            raise PolicyError("The context being replaced is no longer active")
    immediate = command.approve_immediately
    entry = models.EpicContextEntry(
        epic_id=epic_id,
        kind=command.kind,
        title=command.title,
        content=command.content,
        authority=ContextAuthority.APPROVED if immediate else ContextAuthority.PROPOSED,
        status=EpicContextStatus.ACTIVE,
        created_by_actor_id=command.acting_actor_id,
        approved_by_actor_id=command.acting_actor_id if immediate else None,
        approved_at=utcnow() if immediate else None,
        supersedes_context_id=command.supersedes_context_id,
        source_task_id=task.id,
        source_context_id=command.source_context_id,
        source_decision_id=command.source_decision_id,
        source_evidence_id=command.source_evidence_id,
        source_uri=command.source_uri,
        is_required_for_analysis=command.is_required_for_analysis,
        is_required_for_implementation=command.is_required_for_implementation,
    )
    session.add(entry)
    session.flush()
    _mutate_epic(
        session,
        epic,
        "EpicContextApproved" if immediate else "EpicContextProposed",
        command.acting_actor_id,
        {"context_id": str(entry.id), "kind": entry.kind, "title": entry.title},
    )
    if immediate and entry.supersedes_context_id:
        previous = _epic_context(session, epic_id, entry.supersedes_context_id)
        previous.status = EpicContextStatus.SUPERSEDED
        previous.version += 1
        _mutate_epic(
            session,
            epic,
            "EpicContextSuperseded",
            command.acting_actor_id,
            {"context_id": str(previous.id), "replacement_context_id": str(entry.id)},
        )
    _mutate_epic(
        session,
        epic,
        "TaskLearningPromoted",
        command.acting_actor_id,
        {"context_id": str(entry.id), "task_id": str(task.id)},
    )
    session.commit()
    session.refresh(entry)
    return entry


def list_epic_context(
    session: Session,
    epic_id: UUID,
    *,
    include_proposed: bool = False,
    include_history: bool = False,
    kind: EpicContextKind | None = None,
    authority: ContextAuthority | None = None,
    status: EpicContextStatus | None = None,
    source_task_id: UUID | None = None,
) -> list[models.EpicContextEntry]:
    _get(session, models.Epic, epic_id)
    query = select(models.EpicContextEntry).where(models.EpicContextEntry.epic_id == epic_id)
    if not include_history:
        allowed_authorities = [ContextAuthority.APPROVED, ContextAuthority.AUTHORITATIVE]
        if include_proposed:
            allowed_authorities.append(ContextAuthority.PROPOSED)
        query = query.where(
            models.EpicContextEntry.status == EpicContextStatus.ACTIVE,
            models.EpicContextEntry.authority.in_(allowed_authorities),
        )
    if kind is not None:
        query = query.where(models.EpicContextEntry.kind == kind)
    if authority is not None:
        query = query.where(models.EpicContextEntry.authority == authority)
    if status is not None:
        query = query.where(models.EpicContextEntry.status == status)
    if source_task_id is not None:
        query = query.where(models.EpicContextEntry.source_task_id == source_task_id)
    authority_order = case(
        (models.EpicContextEntry.authority == ContextAuthority.AUTHORITATIVE, 0),
        (models.EpicContextEntry.authority == ContextAuthority.APPROVED, 1),
        else_=2,
    )
    return list(
        session.scalars(
            query.order_by(
                authority_order,
                models.EpicContextEntry.kind,
                models.EpicContextEntry.title,
                models.EpicContextEntry.approved_at,
                models.EpicContextEntry.created_at,
            )
        )
    )


def create_actor(session: Session, command: schemas.ActorCreate) -> models.Actor:
    actor = models.Actor(
        kind=ActorKind(command.kind),
        display_name=command.display_name,
        external_ref=command.external_ref,
    )
    session.add(actor)
    session.flush()
    _event(
        session,
        "Actor",
        actor.id,
        1,
        "ActorCreated",
        actor.id,
        {"display_name": actor.display_name},
    )
    session.commit()
    session.refresh(actor)
    return actor


def create_epic(session: Session, command: schemas.EpicCreate) -> models.Epic:
    _get(session, models.Actor, command.architect_actor_id)
    _get(session, models.Actor, command.acting_actor_id)
    epic = models.Epic(
        **command.model_dump(exclude={"acting_actor_id"}),
        created_by_actor_id=command.acting_actor_id,
    )
    session.add(epic)
    session.flush()
    _event(
        session, "EPIC", epic.id, 1, "EpicCreated", command.acting_actor_id, {"title": epic.title}
    )
    session.commit()
    session.refresh(epic)
    return epic


def create_task(session: Session, epic_id: UUID, command: schemas.TaskCreate) -> models.Task:
    epic = _get(session, models.Epic, epic_id)
    architect_id = command.architect_actor_id or epic.architect_actor_id
    _get(session, models.Actor, architect_id)
    task = models.Task(
        epic_id=epic_id,
        title=command.title,
        summary=command.summary,
        objective=command.objective,
        architect_actor_id=architect_id,
        created_by_actor_id=command.acting_actor_id,
    )
    session.add(task)
    session.flush()
    _event(
        session,
        "Task",
        task.id,
        1,
        "TaskCreated",
        command.acting_actor_id,
        {"title": task.title, "architect_actor_id": str(architect_id)},
    )
    session.commit()
    session.refresh(task)
    return task


def add_task_entity[EntityT: models.Base](
    session: Session,
    task_id: UUID,
    command: schemas.TaskCommand,
    entity: EntityT,
    event_type: str,
) -> EntityT:
    task = _task(session, task_id, command.expected_version)
    session.add(entity)
    session.flush()
    _mutate_task(
        session,
        task,
        event_type,
        command.acting_actor_id,
        {"entity_id": str(getattr(entity, "id", ""))},
    )
    session.commit()
    session.refresh(entity)
    return entity


def transition_task(
    session: Session, task_id: UUID, command: schemas.TransitionRequest
) -> models.Task:
    task = _task(session, task_id, command.expected_version)
    decision = validate_transition(task.state, command.target_state, task.blocked_from_state)
    if not decision.allowed:
        raise PolicyError(decision.reason or "Transition not allowed")
    readiness = get_readiness(session, task, command.target_state, command.acting_actor_id)
    if not readiness.ready:
        raise PolicyError(", ".join(item.message for item in readiness.missing))
    previous = task.state
    if command.target_state is TaskState.BLOCKED:
        task.blocked_from_state = previous
    elif previous is TaskState.BLOCKED:
        task.blocked_from_state = None
    task.state = command.target_state
    _mutate_task(
        session,
        task,
        "TaskTransitioned",
        command.acting_actor_id,
        {"from": previous, "to": command.target_state, "reason": command.reason},
    )
    session.add(
        models.TaskStateTransition(
            task_id=task.id,
            from_state=previous,
            to_state=command.target_state,
            requested_by_actor_id=command.acting_actor_id,
            reason=command.reason,
            task_version=task.version,
        )
    )
    session.commit()
    session.refresh(task)
    return task


def get_readiness(
    session: Session, task: models.Task, target: TaskState, actor_id: UUID | None = None
) -> ReadinessResult:
    def count(model: type[models.Base], *criteria: Any) -> int:
        return session.scalar(select(func.count()).select_from(model).where(*criteria)) or 0

    evidence = frozenset(
        session.scalars(select(models.Evidence.kind).where(models.Evidence.task_id == task.id))
    )
    required_flag = None
    if target is TaskState.READY_FOR_ANALYSIS:
        required_flag = models.EpicContextEntry.is_required_for_analysis
    elif target is TaskState.READY_FOR_IMPLEMENTATION:
        required_flag = models.EpicContextEntry.is_required_for_implementation
    missing_epic_context_kinds: tuple[str, ...] = ()
    if required_flag is not None:
        required_kinds = set(
            session.scalars(
                select(models.EpicContextEntry.kind).where(
                    models.EpicContextEntry.epic_id == task.epic_id,
                    required_flag.is_(True),
                    models.EpicContextEntry.status != EpicContextStatus.REJECTED,
                )
            )
        )
        approved_kinds = set(
            session.scalars(
                select(models.EpicContextEntry.kind).where(
                    models.EpicContextEntry.epic_id == task.epic_id,
                    models.EpicContextEntry.status == EpicContextStatus.ACTIVE,
                    models.EpicContextEntry.authority.in_(
                        [ContextAuthority.APPROVED, ContextAuthority.AUTHORITATIVE]
                    ),
                )
            )
        )
        missing_epic_context_kinds = tuple(
            sorted(kind.value for kind in required_kinds - approved_kinds)
        )
    facts = ReadinessFacts(
        objective_exists=bool(task.objective.strip()),
        architect_assigned=task.architect_actor_id is not None,
        actor_count=count(models.TaskActor, models.TaskActor.task_id == task.id),
        open_blocking_questions=count(
            models.Question,
            models.Question.task_id == task.id,
            models.Question.status == "OPEN",
            models.Question.is_blocking.is_(True),
        ),
        open_blocking_questions_for_architect=count(
            models.Question,
            models.Question.task_id == task.id,
            models.Question.status == "OPEN",
            models.Question.is_blocking.is_(True),
            models.Question.assigned_to_actor_id == task.architect_actor_id,
        ),
        open_blockers=count(
            models.Blocker, models.Blocker.task_id == task.id, models.Blocker.status == "OPEN"
        ),
        confirmed_requirements=count(
            models.Requirement,
            models.Requirement.task_id == task.id,
            models.Requirement.status == "CONFIRMED",
        ),
        acceptance_criteria=count(
            models.AcceptanceCriterion,
            models.AcceptanceCriterion.task_id == task.id,
            models.AcceptanceCriterion.status == "ACTIVE",
        ),
        required_decisions_unapproved=count(
            models.Decision,
            models.Decision.task_id == task.id,
            models.Decision.is_required.is_(True),
            models.Decision.status != "APPROVED",
        ),
        evidence_kinds=evidence,
        preproduction_validation_passed=count(
            models.Evidence,
            models.Evidence.task_id == task.id,
            models.Evidence.kind == EvidenceKind.PREPRODUCTION_VALIDATION,
            models.Evidence.passed.is_(True),
        )
        > 0,
        approved_review_exists=count(
            models.Review,
            models.Review.task_id == task.id,
            models.Review.status == ReviewStatus.APPROVED,
        )
        > 0,
        unresolved_blocking_review_findings=count(
            models.ReviewFinding,
            models.ReviewFinding.review_id.in_(
                select(models.Review.id).where(models.Review.task_id == task.id)
            ),
            models.ReviewFinding.is_blocking.is_(True),
            models.ReviewFinding.status == "OPEN",
        ),
        unresolved_critical_issues=count(
            models.ReviewFinding,
            models.ReviewFinding.review_id.in_(
                select(models.Review.id).where(models.Review.task_id == task.id)
            ),
            models.ReviewFinding.severity == Severity.CRITICAL,
            models.ReviewFinding.status == "OPEN",
        ),
        performed_by_architect=actor_id == task.architect_actor_id,
        missing_epic_context_kinds=missing_epic_context_kinds,
    )
    return evaluate_readiness(target, facts)


def allowed_for_task(
    session: Session, task: models.Task, actor_id: UUID | None = None
) -> list[dict[str, Any]]:
    result = []
    for target in sorted(allowed_transitions(task.state, task.blocked_from_state), key=str):
        readiness = get_readiness(session, task, target, actor_id)
        result.append(
            {
                "target_state": target,
                "ready": readiness.ready,
                "missing": [item.__dict__ for item in readiness.missing],
                "suggested": task.state is TaskState.BLOCKED and target == task.blocked_from_state,
            }
        )
    return result


def assign_actor(session: Session, task_id: UUID, command: schemas.ActorAssignment) -> None:
    task = _task(session, task_id, command.expected_version)
    _get(session, models.Actor, command.actor_id)
    session.add(
        models.TaskActor(
            task_id=task_id,
            actor_id=command.actor_id,
            role=command.role,
            added_by_actor_id=command.acting_actor_id,
        )
    )
    _mutate_task(
        session,
        task,
        "ActorAddedToTask",
        command.acting_actor_id,
        {"actor_id": str(command.actor_id), "role": command.role},
    )
    session.commit()


def add_context(
    session: Session, task_id: UUID, command: schemas.ContextCreate
) -> models.ContextEntry:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity: models.ContextEntry = models.ContextEntry(
        task_id=task_id,
        **data,
        status="ACTIVE",
        created_by_actor_id=command.acting_actor_id,
    )
    return add_task_entity(session, task_id, command, entity, "ContextAdded")


def create_context_conflict(
    session: Session, task_id: UUID, command: schemas.ContextConflictCreate
) -> models.ContextConflict:
    task = _task(session, task_id, command.expected_version)
    epic_context = _epic_context(session, task.epic_id, command.epic_context_id)
    task_context = _get(session, models.ContextEntry, command.task_context_id)
    if task_context.task_id != task.id:
        raise PolicyError("Task context entry does not belong to this task")
    if epic_context.status is not EpicContextStatus.ACTIVE or epic_context.authority not in {
        ContextAuthority.APPROVED,
        ContextAuthority.AUTHORITATIVE,
    }:
        raise PolicyError("A conflict must reference active approved epic context")
    conflict = models.ContextConflict(
        task_id=task.id,
        epic_context_id=epic_context.id,
        task_context_id=task_context.id,
        reason=command.reason,
        created_by_actor_id=command.acting_actor_id,
    )
    session.add(conflict)
    session.flush()
    _mutate_task(
        session,
        task,
        "ContextConflictRecorded",
        command.acting_actor_id,
        {"conflict_id": str(conflict.id)},
    )
    session.commit()
    session.refresh(conflict)
    return conflict


def add_requirement(
    session: Session, task_id: UUID, command: schemas.RequirementCreate
) -> models.Requirement:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity: models.Requirement = models.Requirement(
        task_id=task_id, **data, created_by_actor_id=command.acting_actor_id
    )
    return add_task_entity(session, task_id, command, entity, "RequirementAdded")


def add_acceptance_criterion(
    session: Session, task_id: UUID, command: schemas.AcceptanceCriterionCreate
) -> models.AcceptanceCriterion:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity: models.AcceptanceCriterion = models.AcceptanceCriterion(
        task_id=task_id,
        **data,
        status="ACTIVE",
        created_by_actor_id=command.acting_actor_id,
    )
    return add_task_entity(session, task_id, command, entity, "AcceptanceCriterionAdded")


def ask_question(
    session: Session, task_id: UUID, command: schemas.QuestionCreate
) -> models.Question:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity: models.Question = models.Question(
        task_id=task_id,
        **data,
        status="OPEN",
        asked_by_actor_id=command.acting_actor_id,
    )
    return add_task_entity(session, task_id, command, entity, "QuestionAsked")


def answer_question(
    session: Session, question_id: UUID, command: schemas.AnswerCreate
) -> models.QuestionAnswer:
    question = _get(session, models.Question, question_id)
    task = _task(session, question.task_id)
    answer = models.QuestionAnswer(
        question_id=question_id,
        answer=command.answer,
        answered_by_actor_id=command.acting_actor_id,
        supersedes_answer_id=command.supersedes_answer_id,
    )
    session.add(answer)
    question.status = "ANSWERED"
    _mutate_task(
        session,
        task,
        "QuestionAnswered",
        command.acting_actor_id,
        {"question_id": str(question_id)},
    )
    session.commit()
    session.refresh(answer)
    return answer


def create_blocker(
    session: Session, task_id: UUID, command: schemas.BlockerCreate
) -> models.Blocker:
    entity: models.Blocker = models.Blocker(
        task_id=task_id,
        description=command.description,
        status="OPEN",
        created_by_actor_id=command.acting_actor_id,
    )
    return add_task_entity(session, task_id, command, entity, "BlockerCreated")


def resolve_blocker(
    session: Session, blocker_id: UUID, command: schemas.ResolveBlocker
) -> models.Blocker:
    blocker = _get(session, models.Blocker, blocker_id)
    task = _task(session, blocker.task_id, command.expected_version)
    blocker.status = "RESOLVED"
    blocker.resolution = command.resolution
    blocker.resolved_by_actor_id = command.acting_actor_id
    blocker.resolved_at = utcnow()
    blocker.version += 1
    _mutate_task(
        session, task, "BlockerResolved", command.acting_actor_id, {"blocker_id": str(blocker_id)}
    )
    session.commit()
    session.refresh(blocker)
    return blocker


def propose_decision(
    session: Session, task_id: UUID, command: schemas.DecisionCreate
) -> models.Decision:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity: models.Decision = models.Decision(
        task_id=task_id,
        **data,
        status="PROPOSED",
        proposed_by_actor_id=command.acting_actor_id,
    )
    return add_task_entity(session, task_id, command, entity, "DecisionProposed")


def approve_decision(
    session: Session, decision_id: UUID, command: schemas.ApproveDecision
) -> models.Decision:
    decision = _get(session, models.Decision, decision_id)
    task = _task(session, decision.task_id, command.expected_version)
    if command.acting_actor_id != task.architect_actor_id:
        raise PolicyError("Only the assigned architect may approve a decision")
    decision.status = "APPROVED"
    decision.approved_by_actor_id = command.acting_actor_id
    decision.approved_at = utcnow()
    decision.version += 1
    _mutate_task(
        session,
        task,
        "DecisionApproved",
        command.acting_actor_id,
        {"decision_id": str(decision_id)},
    )
    session.commit()
    session.refresh(decision)
    return decision


def get_task_working_context(session: Session, task_id: UUID) -> dict[str, Any]:
    task = _task(session, task_id)
    epic = _get(session, models.Epic, task.epic_id)
    result: dict[str, Any] = {
        "task": schemas.TaskRead.model_validate(task).model_dump(mode="json"),
        "epic_version": epic.version,
        "task_version": task.version,
        "allowed_transitions": allowed_for_task(session, task),
    }
    events = session.scalars(
        select(models.DomainEvent)
        .where(models.DomainEvent.aggregate_id == task_id)
        .order_by(models.DomainEvent.aggregate_sequence)
    )
    result["timeline"] = [
        {
            "id": str(event.id),
            "sequence": event.aggregate_sequence,
            "type": event.event_type,
            "actor_id": str(event.actor_id) if event.actor_id else None,
            "payload": event.payload,
            "occurred_at": event.occurred_at.isoformat(),
        }
        for event in events
    ]
    collections: dict[str, Any] = {
        "actors": models.TaskActor,
        "requirements": models.Requirement,
        "acceptance_criteria": models.AcceptanceCriterion,
        "context_entries": models.ContextEntry,
        "questions": models.Question,
        "blockers": models.Blocker,
        "decisions": models.Decision,
        "implementation_runs": models.ImplementationRun,
        "evidence": models.Evidence,
        "reviews": models.Review,
    }
    for name, model in collections.items():
        rows = session.scalars(select(model).where(model.task_id == task_id)).all()
        result[name] = [
            {
                column.name: getattr(row, column.key)
                if not isinstance(getattr(row, column.key), UUID)
                else str(getattr(row, column.key))
                for column in model.__table__.columns
            }
            for row in rows
        ]
    active = list_epic_context(session, epic.id)
    pending = list_epic_context(
        session,
        epic.id,
        include_proposed=True,
        authority=ContextAuthority.PROPOSED,
    )
    result["epic_context"] = {
        "active": [
            schemas.EpicContextRead.model_validate(row).model_dump(mode="json") for row in active
        ],
        "pending_proposals": [
            schemas.EpicContextRead.model_validate(row).model_dump(mode="json") for row in pending
        ],
    }
    conflicts = session.scalars(
        select(models.ContextConflict).where(models.ContextConflict.task_id == task.id)
    )
    result["context_conflicts"] = [
        {
            "epic_context_id": str(item.epic_context_id),
            "task_context_id": str(item.task_context_id),
            "reason": item.reason,
        }
        for item in conflicts
    ]
    return result


def utcnow() -> datetime:
    return datetime.now(UTC)
