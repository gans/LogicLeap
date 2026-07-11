from sqlalchemy import select
from sqlalchemy.orm import Session

from logicleap.application import schemas, services
from logicleap.database import create_database_engine
from logicleap.domain.enums import ActorKind
from logicleap.infrastructure.persistence import models


def seed() -> None:
    with Session(create_database_engine()) as session:
        existing = session.scalar(
            select(models.Epic).where(models.Epic.title == "Legacy Commerce Platform Migration")
        )
        if existing:
            print(f"Seed already present: {existing.id}")
            return

        architect = services.create_actor(
            session,
            schemas.ActorCreate(
                display_name="Alex Morgan — Architect",
                kind=ActorKind.HUMAN,
                external_ref="seed:architect",
            ),
        )
        agent = services.create_actor(
            session,
            schemas.ActorCreate(
                display_name="Migration Analysis Agent",
                kind=ActorKind.AGENT,
                external_ref="seed:analysis-agent",
            ),
        )
        epic = services.create_epic(
            session,
            schemas.EpicCreate(
                title="Legacy Commerce Platform Migration",
                summary="Coordinate the safe replacement of the unsupported commerce platform.",
                problem_statement=(
                    "The current commerce platform is unsupported and difficult to change safely."
                ),
                desired_outcome=(
                    "A supported, observable platform migrated without customer disruption."
                ),
                architect_actor_id=architect.id,
                acting_actor_id=architect.id,
            ),
        )
        tasks = [
            (
                "Inventory integrations",
                "Create a verified inventory of upstream and downstream integrations.",
            ),
            (
                "Design migration architecture",
                "Approve the target architecture and incremental migration path.",
            ),
            ("Build catalog migration", "Implement and validate catalog data migration."),
        ]
        for title, objective in tasks:
            task = services.create_task(
                session,
                epic.id,
                schemas.TaskCreate(
                    title=title,
                    summary=objective,
                    objective=objective,
                    acting_actor_id=architect.id,
                ),
            )
            services.assign_actor(
                session,
                task.id,
                schemas.ActorAssignment(
                    actor_id=agent.id,
                    role="CONTRIBUTOR",
                    acting_actor_id=architect.id,
                    expected_version=task.version,
                ),
            )
        print(f"Seeded epic: {epic.id}")


if __name__ == "__main__":
    seed()
