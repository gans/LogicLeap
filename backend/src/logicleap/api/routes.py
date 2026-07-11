from collections.abc import Iterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from logicleap.application import schemas, services
from logicleap.database import create_database_engine
from logicleap.domain.enums import ContextStatus, TaskState
from logicleap.infrastructure.persistence import models

router = APIRouter(prefix="/api/v1")


def session_scope() -> Iterator[Session]:
    with Session(create_database_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(session_scope)]


def _run(operation: object) -> object:
    try:
        return operation
    except services.NotFoundError as exc:
        raise HTTPException(404, detail={"code": "not_found", "message": str(exc)}) from exc
    except services.ConflictError as exc:
        raise HTTPException(409, detail={"code": "version_conflict", "message": str(exc)}) from exc
    except services.PolicyError as exc:
        raise HTTPException(409, detail={"code": "policy_rejected", "message": str(exc)}) from exc


@router.post("/actors", response_model=schemas.ActorRead, status_code=201)
def create_actor(command: schemas.ActorCreate, session: SessionDep) -> models.Actor:
    return services.create_actor(session, command)


@router.get("/actors", response_model=list[schemas.ActorRead])
def list_actors(session: SessionDep) -> list[models.Actor]:
    return list(session.scalars(select(models.Actor).order_by(models.Actor.display_name)))


@router.post("/epics", response_model=schemas.EpicRead, status_code=201)
def create_epic(command: schemas.EpicCreate, session: SessionDep) -> models.Epic:
    return _run(services.create_epic(session, command))  # type: ignore[return-value]


@router.get("/epics", response_model=list[schemas.EpicRead])
def list_epics(session: SessionDep) -> list[models.Epic]:
    return list(session.scalars(select(models.Epic).order_by(models.Epic.created_at.desc())))


@router.get("/epics/{epic_id}", response_model=schemas.EpicRead)
def get_epic(epic_id: UUID, session: SessionDep) -> models.Epic:
    return _run(services._get(session, models.Epic, epic_id))  # type: ignore[return-value]


@router.post("/epics/{epic_id}/tasks", response_model=schemas.TaskRead, status_code=201)
def create_task(epic_id: UUID, command: schemas.TaskCreate, session: SessionDep) -> models.Task:
    return _run(services.create_task(session, epic_id, command))  # type: ignore[return-value]


@router.get("/epics/{epic_id}/tasks", response_model=list[schemas.TaskRead])
def list_tasks(epic_id: UUID, session: SessionDep) -> list[models.Task]:
    return list(
        session.scalars(
            select(models.Task)
            .where(models.Task.epic_id == epic_id)
            .order_by(models.Task.created_at)
        )
    )


@router.get("/tasks/{task_id}", response_model=schemas.TaskRead)
def get_task(task_id: UUID, session: SessionDep) -> models.Task:
    return _run(services._task(session, task_id))  # type: ignore[return-value]


@router.post("/tasks/{task_id}/actors", status_code=201)
def add_actor(
    task_id: UUID, command: schemas.ActorAssignment, session: SessionDep
) -> dict[str, str]:
    task = services._task(session, task_id, command.expected_version)
    services._get(session, models.Actor, command.actor_id)
    session.add(
        models.TaskActor(
            task_id=task_id,
            actor_id=command.actor_id,
            role=command.role,
            added_by_actor_id=command.acting_actor_id,
        )
    )
    services._mutate_task(
        session,
        task,
        "ActorAddedToTask",
        command.acting_actor_id,
        {"actor_id": str(command.actor_id), "role": command.role},
    )
    session.commit()
    return {"status": "created"}


@router.post("/tasks/{task_id}/contexts", status_code=201)
def add_context(
    task_id: UUID, command: schemas.ContextCreate, session: SessionDep
) -> dict[str, str]:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity = models.ContextEntry(
        task_id=task_id,
        **data,
        status=ContextStatus.ACTIVE,
        created_by_actor_id=command.acting_actor_id,
    )
    result = services.add_task_entity(session, task_id, command, entity, "ContextAdded")
    return {"id": str(result.id)}


@router.post("/tasks/{task_id}/requirements", status_code=201)
def add_requirement(
    task_id: UUID, command: schemas.RequirementCreate, session: SessionDep
) -> dict[str, str]:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity = models.Requirement(
        task_id=task_id, **data, created_by_actor_id=command.acting_actor_id
    )
    result = services.add_task_entity(session, task_id, command, entity, "RequirementAdded")
    return {"id": str(result.id)}


@router.post("/tasks/{task_id}/acceptance-criteria", status_code=201)
def add_acceptance(
    task_id: UUID, command: schemas.AcceptanceCriterionCreate, session: SessionDep
) -> dict[str, str]:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity = models.AcceptanceCriterion(
        task_id=task_id, **data, status="ACTIVE", created_by_actor_id=command.acting_actor_id
    )
    result = services.add_task_entity(session, task_id, command, entity, "AcceptanceCriterionAdded")
    return {"id": str(result.id)}


@router.post("/tasks/{task_id}/questions", status_code=201)
def ask_question(
    task_id: UUID, command: schemas.QuestionCreate, session: SessionDep
) -> dict[str, str]:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity = models.Question(
        task_id=task_id, **data, status="OPEN", asked_by_actor_id=command.acting_actor_id
    )
    result = services.add_task_entity(session, task_id, command, entity, "QuestionAsked")
    return {"id": str(result.id)}


@router.post("/tasks/{task_id}/blockers", status_code=201)
def create_blocker(
    task_id: UUID, command: schemas.BlockerCreate, session: SessionDep
) -> dict[str, str]:
    entity = models.Blocker(
        task_id=task_id,
        description=command.description,
        status="OPEN",
        created_by_actor_id=command.acting_actor_id,
    )
    result = services.add_task_entity(session, task_id, command, entity, "BlockerCreated")
    return {"id": str(result.id)}


@router.post("/tasks/{task_id}/decisions", status_code=201)
def propose_decision(
    task_id: UUID, command: schemas.DecisionCreate, session: SessionDep
) -> dict[str, str]:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity = models.Decision(
        task_id=task_id, **data, status="PROPOSED", proposed_by_actor_id=command.acting_actor_id
    )
    result = services.add_task_entity(session, task_id, command, entity, "DecisionProposed")
    return {"id": str(result.id)}


@router.post("/tasks/{task_id}/implementation-runs", status_code=201)
def add_implementation_run(
    task_id: UUID, command: schemas.ImplementationRunCreate, session: SessionDep
) -> dict[str, str]:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity = models.ImplementationRun(
        task_id=task_id, **data, registered_by_actor_id=command.acting_actor_id
    )
    result = services.add_task_entity(
        session, task_id, command, entity, "ImplementationRunRegistered"
    )
    return {"id": str(result.id)}


@router.post("/tasks/{task_id}/evidence", status_code=201)
def add_evidence(
    task_id: UUID, command: schemas.EvidenceCreate, session: SessionDep
) -> dict[str, str]:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity = models.Evidence(
        task_id=task_id, **data, registered_by_actor_id=command.acting_actor_id
    )
    result = services.add_task_entity(session, task_id, command, entity, "EvidenceRegistered")
    return {"id": str(result.id)}


@router.post("/tasks/{task_id}/reviews", status_code=201)
def add_review(task_id: UUID, command: schemas.ReviewCreate, session: SessionDep) -> dict[str, str]:
    data = command.model_dump(exclude={"expected_version", "acting_actor_id"})
    entity = models.Review(task_id=task_id, **data)
    result = services.add_task_entity(session, task_id, command, entity, "ReviewRegistered")
    return {"id": str(result.id)}


@router.post("/tasks/{task_id}/transition-requests", response_model=schemas.TaskRead)
def request_transition(
    task_id: UUID, command: schemas.TransitionRequest, session: SessionDep
) -> models.Task:
    return _run(services.transition_task(session, task_id, command))  # type: ignore[return-value]


@router.get("/tasks/{task_id}/readiness")
def readiness(
    task_id: UUID,
    target: Annotated[TaskState, Query()],
    session: SessionDep,
    actor_id: UUID | None = None,
) -> object:
    task = services._task(session, task_id)
    return services.get_readiness(session, task, target, actor_id)


@router.get("/tasks/{task_id}/allowed-transitions")
def transitions(
    task_id: UUID,
    session: SessionDep,
    x_actor_id: Annotated[UUID | None, Header()] = None,
) -> list[dict[str, object]]:
    task = services._task(session, task_id)
    return services.allowed_for_task(session, task, x_actor_id)


@router.get("/tasks/{task_id}/timeline")
def timeline(task_id: UUID, session: SessionDep) -> list[dict[str, object]]:
    events = session.scalars(
        select(models.DomainEvent)
        .where(models.DomainEvent.aggregate_id == task_id)
        .order_by(models.DomainEvent.aggregate_sequence)
    )
    return [
        {
            "id": event.id,
            "sequence": event.aggregate_sequence,
            "type": event.event_type,
            "actor_id": event.actor_id,
            "payload": event.payload,
            "occurred_at": event.occurred_at,
        }
        for event in events
    ]


@router.get("/tasks/{task_id}/working-context")
def working_context(task_id: UUID, session: SessionDep) -> dict[str, object]:
    task = services._task(session, task_id)
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
    result: dict[str, object] = {
        "task": schemas.TaskRead.model_validate(task).model_dump(mode="json")
    }
    for name, model in collections.items():
        rows = session.scalars(select(model).where(model.task_id == task_id)).all()
        result[name] = [
            {column.name: getattr(row, column.key) for column in model.__table__.columns}
            for row in rows
        ]
    result["allowed_transitions"] = services.allowed_for_task(session, task)
    return result
