from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from logicleap.application import schemas, services
from logicleap.database import create_database_engine
from logicleap.domain.enums import ActorKind, ContextAuthority, EpicContextKind, EpicContextStatus
from logicleap.infrastructure.persistence import models
from logicleap.main import app


def actor(session: Session, name: str, kind: ActorKind = ActorKind.HUMAN) -> models.Actor:
    return services.create_actor(
        session,
        schemas.ActorCreate(display_name=f"{name} {uuid4()}", kind=kind),
    )


def epic(session: Session, architect: models.Actor) -> models.Epic:
    return services.create_epic(
        session,
        schemas.EpicCreate(
            title=f"Epic {uuid4()}",
            summary="Summary",
            problem_statement="Problem",
            desired_outcome="Outcome",
            architect_actor_id=architect.id,
            acting_actor_id=architect.id,
        ),
    )


def create_context(
    session: Session,
    item: models.Epic,
    acting_actor: models.Actor,
    *,
    immediate: bool = False,
    supersedes: UUID | None = None,
) -> models.EpicContextEntry:
    session.refresh(item)
    return services.create_epic_context(
        session,
        item.id,
        schemas.EpicContextCreate(
            kind=EpicContextKind.ARCHITECTURE,
            title=f"Architecture {uuid4()}",
            content="Shared architecture context",
            acting_actor_id=acting_actor.id,
            expected_epic_version=item.version,
            approve_immediately=immediate,
            supersedes_context_id=supersedes,
        ),
    )


def test_context_authority_approval_rejection_and_deprecation() -> None:
    with Session(create_database_engine()) as session:
        architect = actor(session, "Architect")
        coder = actor(session, "Coder", ActorKind.AGENT)
        item = epic(session, architect)
        proposal = create_context(session, item, coder)
        assert proposal.authority is ContextAuthority.PROPOSED
        assert proposal.status is EpicContextStatus.ACTIVE

        session.refresh(item)
        with pytest.raises(services.PolicyError, match="architect"):
            services.approve_epic_context(
                session,
                item.id,
                proposal.id,
                schemas.EpicContextReview(
                    acting_actor_id=coder.id, expected_epic_version=item.version
                ),
            )
        session.rollback()

        session.refresh(item)
        approved = services.approve_epic_context(
            session,
            item.id,
            proposal.id,
            schemas.EpicContextReview(
                acting_actor_id=architect.id, expected_epic_version=item.version
            ),
        )
        assert approved.approved_by_actor_id == architect.id
        assert approved.approved_at is not None

        rejected = create_context(session, item, coder)
        session.refresh(item)
        rejected = services.reject_epic_context(
            session,
            item.id,
            rejected.id,
            schemas.EpicContextReview(
                acting_actor_id=architect.id,
                expected_epic_version=item.version,
                reason="Not sufficiently evidenced",
            ),
        )
        assert rejected.status is EpicContextStatus.REJECTED
        assert rejected.rejection_reason == "Not sufficiently evidenced"

        session.refresh(item)
        deprecated = services.deprecate_epic_context(
            session,
            item.id,
            approved.id,
            schemas.EpicContextDeprecate(
                acting_actor_id=architect.id,
                expected_epic_version=item.version,
                reason="No longer applies",
            ),
        )
        assert deprecated.status is EpicContextStatus.DEPRECATED


def test_approving_replacement_supersedes_previous_and_appends_epic_events() -> None:
    with Session(create_database_engine()) as session:
        architect = actor(session, "Architect")
        coder = actor(session, "Coder", ActorKind.AGENT)
        item = epic(session, architect)
        previous = create_context(session, item, architect, immediate=True)
        replacement = create_context(session, item, coder, supersedes=previous.id)
        before = item.version
        session.refresh(item)
        replacement = services.approve_epic_context(
            session,
            item.id,
            replacement.id,
            schemas.EpicContextReview(
                acting_actor_id=architect.id, expected_epic_version=item.version
            ),
        )
        session.refresh(previous)
        session.refresh(item)
        assert previous.status is EpicContextStatus.SUPERSEDED
        assert replacement.authority is ContextAuthority.APPROVED
        assert item.version == before + 2
        event_types = list(
            session.scalars(
                select(models.DomainEvent.event_type)
                .where(models.DomainEvent.aggregate_id == item.id)
                .order_by(models.DomainEvent.aggregate_sequence)
            )
        )
        assert event_types[-2:] == ["EpicContextSuperseded", "EpicContextApproved"]


def test_cross_epic_replacement_and_cycle_are_rejected() -> None:
    with Session(create_database_engine()) as session:
        architect = actor(session, "Architect")
        first = epic(session, architect)
        second = epic(session, architect)
        other = create_context(session, second, architect, immediate=True)
        session.refresh(first)
        with pytest.raises(services.PolicyError, match="does not belong"):
            create_context(session, first, architect, supersedes=other.id)
        session.rollback()

        one = create_context(session, first, architect, immediate=True)
        two = create_context(session, first, architect, supersedes=one.id)
        one.supersedes_context_id = two.id
        session.flush()
        with pytest.raises(services.PolicyError, match="cycle"):
            services._validate_supersedes(session, first.id, one.id)
        session.rollback()


def test_task_learning_and_working_context_inheritance() -> None:
    with Session(create_database_engine()) as session:
        architect = actor(session, "Architect")
        coder = actor(session, "Coder", ActorKind.AGENT)
        item = epic(session, architect)
        task = services.create_task(
            session,
            item.id,
            schemas.TaskCreate(
                title="Task", summary="Summary", objective="Objective", acting_actor_id=architect.id
            ),
        )
        approved = create_context(session, item, architect, immediate=True)
        session.refresh(item)
        with pytest.raises(services.PolicyError, match="participate"):
            services.promote_task_learning(
                session,
                item.id,
                schemas.PromoteTaskLearning(
                    task_id=task.id,
                    kind=EpicContextKind.LESSON_LEARNED,
                    title="Learning",
                    content="Learning content",
                    acting_actor_id=coder.id,
                    expected_epic_version=item.version,
                ),
            )
        session.rollback()
        session.refresh(task)
        services.assign_actor(
            session,
            task.id,
            schemas.ActorAssignment(
                actor_id=coder.id,
                role="CODER",
                acting_actor_id=architect.id,
                expected_version=task.version,
            ),
        )
        session.refresh(item)
        proposal = services.promote_task_learning(
            session,
            item.id,
            schemas.PromoteTaskLearning(
                task_id=task.id,
                kind=EpicContextKind.LESSON_LEARNED,
                title="Ordering",
                content="Events arrive out of order",
                acting_actor_id=coder.id,
                expected_epic_version=item.version,
            ),
        )
        assert proposal.authority is ContextAuthority.PROPOSED
        context = services.get_task_working_context(session, task.id)
        assert context["epic_version"] == item.version
        assert context["task_version"] == task.version
        assert [entry["id"] for entry in context["epic_context"]["active"]] == [str(approved.id)]
        assert [entry["id"] for entry in context["epic_context"]["pending_proposals"]] == [
            str(proposal.id)
        ]


def test_api_context_endpoints_and_typed_version_conflict() -> None:
    client = TestClient(app)
    architect = client.post(
        "/api/v1/actors", json={"display_name": f"Architect {uuid4()}", "kind": "HUMAN"}
    ).json()
    item = client.post(
        "/api/v1/epics",
        json={
            "title": f"Epic {uuid4()}",
            "summary": "Summary",
            "problem_statement": "Problem",
            "desired_outcome": "Outcome",
            "architect_actor_id": architect["id"],
            "acting_actor_id": architect["id"],
        },
    ).json()
    response = client.post(
        f"/api/v1/epics/{item['id']}/contexts",
        json={
            "kind": "BUSINESS",
            "title": "Rules",
            "content": "Preserve identifiers",
            "acting_actor_id": architect["id"],
            "expected_epic_version": item["version"],
            "approve_immediately": True,
        },
    )
    assert response.status_code == 201
    assert client.get(f"/api/v1/epics/{item['id']}/contexts").json()[0]["title"] == "Rules"
    assert client.get(f"/api/v1/epics/{item['id']}/context-history").status_code == 200
    assert (
        client.get(f"/api/v1/epics/{item['id']}/timeline").json()[-1]["type"]
        == "EpicContextApproved"
    )
    conflict = client.post(
        f"/api/v1/epics/{item['id']}/contexts",
        json={
            "kind": "OTHER",
            "title": "Stale",
            "content": "Stale",
            "acting_actor_id": architect["id"],
            "expected_epic_version": item["version"],
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "version_conflict"


def test_failed_context_command_does_not_append_event() -> None:
    with Session(create_database_engine()) as session:
        architect = actor(session, "Architect")
        coder = actor(session, "Coder")
        item = epic(session, architect)
        proposal = create_context(session, item, coder)
        before = session.scalar(
            select(func.count())
            .select_from(models.DomainEvent)
            .where(models.DomainEvent.aggregate_id == item.id)
        )
        session.refresh(item)
        with pytest.raises(services.PolicyError):
            services.approve_epic_context(
                session,
                item.id,
                proposal.id,
                schemas.EpicContextReview(
                    acting_actor_id=coder.id, expected_epic_version=item.version
                ),
            )
        session.rollback()
        after = session.scalar(
            select(func.count())
            .select_from(models.DomainEvent)
            .where(models.DomainEvent.aggregate_id == item.id)
        )
        assert after == before
