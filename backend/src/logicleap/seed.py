from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from logicleap.application import schemas, services
from logicleap.database import create_database_engine
from logicleap.domain.enums import ActorKind, EpicContextKind
from logicleap.infrastructure.persistence import models


def seed() -> None:
    with Session(create_database_engine()) as session:
        existing = session.scalar(
            select(models.Epic).where(models.Epic.title == "Legacy Commerce Platform Migration")
        )
        architect = session.scalar(
            select(models.Actor).where(models.Actor.external_ref == "seed:architect")
        )
        if architect is None:
            architect = services.create_actor(
                session,
                schemas.ActorCreate(
                    display_name="Alex Morgan — Architect",
                    kind=ActorKind.HUMAN,
                    external_ref="seed:architect",
                ),
            )
        agent = session.scalar(
            select(models.Actor).where(models.Actor.external_ref == "seed:analysis-agent")
        )
        if agent is None:
            agent = services.create_actor(
                session,
                schemas.ActorCreate(
                    display_name="Migration Analysis Agent",
                    kind=ActorKind.AGENT,
                    external_ref="seed:analysis-agent",
                ),
            )
        epic = existing
        if epic is None:
            epic = services.create_epic(
                session,
                schemas.EpicCreate(
                    title="Legacy Commerce Platform Migration",
                    summary="Coordinate the safe replacement of the unsupported commerce platform.",
                    problem_statement=(
                        "The current commerce platform is unsupported and difficult "
                        "to change safely."
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
        seeded_tasks: list[models.Task] = []
        for title, objective in tasks:
            task = session.scalar(
                select(models.Task).where(
                    models.Task.epic_id == epic.id, models.Task.title == title
                )
            )
            if task is None:
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
            if session.get(models.TaskActor, (task.id, agent.id)) is None:
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
            seeded_tasks.append(task)
        if not session.scalar(
            select(models.EpicContextEntry.id).where(models.EpicContextEntry.epic_id == epic.id)
        ):

            def add(
                kind: EpicContextKind, title: str, content: str, **extra: Any
            ) -> models.EpicContextEntry:
                session.refresh(epic)
                return services.create_epic_context(
                    session,
                    epic.id,
                    schemas.EpicContextCreate(
                        kind=kind,
                        title=title,
                        content=content,
                        acting_actor_id=architect.id,
                        expected_epic_version=epic.version,
                        approve_immediately=True,
                        **extra,
                    ),
                )

            add(
                EpicContextKind.ARCHITECTURE,
                "Incremental migration architecture",
                "Use a strangler migration with observable, reversible releases.",
                is_required_for_implementation=True,
            )
            add(
                EpicContextKind.BUSINESS,
                "Customer continuity rule",
                "Customer-facing commerce flows must remain available throughout migration.",
            )
            old = add(
                EpicContextKind.TESTING,
                "Migration test procedure v1",
                "Run record-count checks after each batch.",
            )
            add(
                EpicContextKind.TESTING,
                "Migration test procedure v2",
                "Run record counts, referential-integrity checks, and replay validation "
                "after each batch.",
                supersedes_context_id=old.id,
            )
            deprecated = add(
                EpicContextKind.DEPLOYMENT,
                "Legacy big-bang deployment note",
                "The retired plan used a single cutover window.",
            )
            session.refresh(epic)
            services.deprecate_epic_context(
                session,
                epic.id,
                deprecated.id,
                schemas.EpicContextDeprecate(
                    acting_actor_id=architect.id,
                    expected_epic_version=epic.version,
                    reason="Replaced by incremental delivery strategy",
                ),
            )
            session.refresh(epic)
            services.promote_task_learning(
                session,
                epic.id,
                schemas.PromoteTaskLearning(
                    task_id=seeded_tasks[0].id,
                    kind=EpicContextKind.LESSON_LEARNED,
                    title="Legacy events may arrive out of order",
                    content="Consumers must tolerate and reconcile out-of-order legacy events.",
                    acting_actor_id=agent.id,
                    expected_epic_version=epic.version,
                ),
            )
        print(f"Seeded epic: {epic.id}")


if __name__ == "__main__":
    seed()
