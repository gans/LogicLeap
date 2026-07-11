from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from logicleap.application import schemas
from logicleap.domain.enums import ActorKind, EvidenceKind, ReviewStatus, Severity, TaskState
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
        session, "Epic", epic.id, 1, "EpicCreated", command.acting_actor_id, {"title": epic.title}
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
    result: dict[str, Any] = {
        "task": schemas.TaskRead.model_validate(task).model_dump(mode="json"),
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
    return result


def utcnow() -> datetime:
    return datetime.now(UTC)
