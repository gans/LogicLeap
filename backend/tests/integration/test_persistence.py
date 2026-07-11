from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from logicleap.database import create_database_engine
from logicleap.domain.enums import ActorKind
from logicleap.infrastructure.persistence.models import Actor, DomainEvent


def test_uuid4_actor_round_trip() -> None:
    engine = create_database_engine()
    actor = Actor(kind=ActorKind.HUMAN, display_name="Integration Architect")
    with Session(engine) as session:
        session.add(actor)
        session.commit()
        actor_id = actor.id

    assert actor_id.version == 4
    with Session(engine) as session:
        assert session.scalar(select(Actor).where(Actor.id == actor_id)) is not None


def test_domain_event_sequence_is_unique_per_aggregate() -> None:
    engine = create_database_engine()
    aggregate_id = uuid4()
    with Session(engine) as session:
        session.add_all(
            [
                DomainEvent(
                    aggregate_type="Task",
                    aggregate_id=aggregate_id,
                    aggregate_sequence=1,
                    event_type="TaskCreated",
                    payload={},
                ),
                DomainEvent(
                    aggregate_type="Task",
                    aggregate_id=aggregate_id,
                    aggregate_sequence=1,
                    event_type="TaskUpdated",
                    payload={},
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            session.commit()
