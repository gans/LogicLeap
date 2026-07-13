from typing import Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from sqlalchemy.orm import Session

from logicleap.application import schemas, services
from logicleap.database import create_database_engine
from logicleap.domain.enums import TaskState

mcp = FastMCP(
    "LogicLeap",
    instructions="Typed tools for human-controlled SDLC coordination.",
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    port=8001,
)


def _session() -> Session:
    return Session(create_database_engine())


def _compact_agent_working_context(context: dict[str, Any]) -> dict[str, Any]:
    pending = context.get("epic_context", {}).get("pending_proposals", [])
    context["epic_context"]["pending_proposals"] = [
        {
            "id": item["id"],
            "kind": item["kind"],
            "title": item["title"],
            "authority": item["authority"],
            "status": item["status"],
            "supersedes_context_id": item.get("supersedes_context_id"),
            "source_task_id": item.get("source_task_id"),
        }
        for item in pending
    ]
    return context


@mcp.tool()
def get_task_working_context(task_id: UUID) -> dict[str, Any]:
    """Return the complete coordinated working context for a task."""
    with _session() as session:
        return _compact_agent_working_context(services.get_task_working_context(session, task_id))


@mcp.tool()
def get_epic_context(epic_id: UUID) -> list[dict[str, Any]]:
    """Return full active approved epic context for use as agent instructions."""
    with _session() as session:
        return [
            schemas.EpicContextRead.model_validate(item).model_dump(mode="json")
            for item in services.list_epic_context(session, epic_id)
        ]


@mcp.tool()
def list_epic_context_history(epic_id: UUID) -> list[dict[str, Any]]:
    """Return compact epic context history; inactive content is intentionally omitted."""
    with _session() as session:
        return [
            {
                "id": str(item.id),
                "kind": item.kind,
                "title": item.title,
                "authority": item.authority,
                "status": item.status,
                "supersedes_context_id": (
                    str(item.supersedes_context_id) if item.supersedes_context_id else None
                ),
                "source_task_id": str(item.source_task_id) if item.source_task_id else None,
                "created_at": item.created_at.isoformat(),
            }
            for item in services.list_epic_context(session, epic_id, include_history=True)
        ]


@mcp.tool()
def propose_epic_context(epic_id: UUID, command: schemas.EpicContextCreate) -> dict[str, str]:
    """Propose epic context; only an architect may explicitly request immediate approval."""
    with _session() as session:
        entry = services.create_epic_context(session, epic_id, command)
        return {"id": str(entry.id), "authority": entry.authority, "status": entry.status}


@mcp.tool()
def propose_epic_context_improvement(
    epic_id: UUID, context_id: UUID, command: schemas.EpicContextReplacement
) -> dict[str, str]:
    """Propose a historical replacement without overwriting approved context."""
    with _session() as session:
        entry = services.propose_epic_context_replacement(session, epic_id, context_id, command)
        return {"id": str(entry.id), "authority": entry.authority, "status": entry.status}


@mcp.tool()
def propose_epic_context_from_task(
    epic_id: UUID, command: schemas.PromoteTaskLearning
) -> dict[str, str]:
    """Promote a participating actor's task learning into the epic review workflow."""
    with _session() as session:
        entry = services.promote_task_learning(session, epic_id, command)
        return {"id": str(entry.id), "authority": entry.authority, "status": entry.status}


@mcp.tool()
def approve_epic_context(
    epic_id: UUID, context_id: UUID, command: schemas.EpicContextReview
) -> dict[str, str]:
    """Approve proposed context as the epic architect."""
    with _session() as session:
        entry = services.approve_epic_context(session, epic_id, context_id, command)
        return {"id": str(entry.id), "authority": entry.authority, "status": entry.status}


@mcp.tool()
def reject_epic_context(
    epic_id: UUID, context_id: UUID, command: schemas.EpicContextReview
) -> dict[str, str]:
    """Reject proposed context as the epic architect, preserving history."""
    with _session() as session:
        entry = services.reject_epic_context(session, epic_id, context_id, command)
        return {"id": str(entry.id), "authority": entry.authority, "status": entry.status}


@mcp.tool()
def deprecate_epic_context(
    epic_id: UUID, context_id: UUID, command: schemas.EpicContextDeprecate
) -> dict[str, str]:
    """Deprecate active approved context as the epic architect."""
    with _session() as session:
        entry = services.deprecate_epic_context(session, epic_id, context_id, command)
        return {"id": str(entry.id), "authority": entry.authority, "status": entry.status}


@mcp.tool()
def create_epic(command: schemas.EpicCreate) -> dict[str, str]:
    """Create an epic through the typed application command."""
    with _session() as session:
        epic = services.create_epic(session, command)
        return {"id": str(epic.id)}


@mcp.tool()
def create_task(epic_id: UUID, command: schemas.TaskCreate) -> dict[str, str]:
    """Create a task, inheriting the epic architect unless explicitly supplied."""
    with _session() as session:
        task = services.create_task(session, epic_id, command)
        return {"id": str(task.id), "architect_actor_id": str(task.architect_actor_id)}


@mcp.tool()
def add_actor_to_task(task_id: UUID, command: schemas.ActorAssignment) -> dict[str, str]:
    """Assign a participant and role to a task."""
    with _session() as session:
        services.assign_actor(session, task_id, command)
        return {"status": "created"}


@mcp.tool()
def add_context(task_id: UUID, command: schemas.ContextCreate) -> dict[str, str]:
    """Add an authority- and lifecycle-qualified context entry."""
    with _session() as session:
        return {"id": str(services.add_context(session, task_id, command).id)}


@mcp.tool()
def add_requirement(task_id: UUID, command: schemas.RequirementCreate) -> dict[str, str]:
    """Add a typed task requirement."""
    with _session() as session:
        return {"id": str(services.add_requirement(session, task_id, command).id)}


@mcp.tool()
def add_acceptance_criterion(
    task_id: UUID, command: schemas.AcceptanceCriterionCreate
) -> dict[str, str]:
    """Add a task acceptance criterion."""
    with _session() as session:
        return {"id": str(services.add_acceptance_criterion(session, task_id, command).id)}


@mcp.tool()
def ask_question(task_id: UUID, command: schemas.QuestionCreate) -> dict[str, str]:
    """Register a typed task question."""
    with _session() as session:
        return {"id": str(services.ask_question(session, task_id, command).id)}


@mcp.tool()
def answer_question(question_id: UUID, command: schemas.AnswerCreate) -> dict[str, str]:
    """Answer a registered question without overwriting answer history."""
    with _session() as session:
        return {"id": str(services.answer_question(session, question_id, command).id)}


@mcp.tool()
def create_blocker(task_id: UUID, command: schemas.BlockerCreate) -> dict[str, str]:
    """Register an open task blocker."""
    with _session() as session:
        return {"id": str(services.create_blocker(session, task_id, command).id)}


@mcp.tool()
def resolve_blocker(blocker_id: UUID, command: schemas.ResolveBlocker) -> dict[str, str]:
    """Resolve a blocker with an explicit resolution."""
    with _session() as session:
        return {"id": str(services.resolve_blocker(session, blocker_id, command).id)}


@mcp.tool()
def propose_decision(task_id: UUID, command: schemas.DecisionCreate) -> dict[str, str]:
    """Propose a task decision."""
    with _session() as session:
        return {"id": str(services.propose_decision(session, task_id, command).id)}


@mcp.tool()
def approve_decision(decision_id: UUID, command: schemas.ApproveDecision) -> dict[str, str]:
    """Approve a decision as the assigned architect."""
    with _session() as session:
        return {"id": str(services.approve_decision(session, decision_id, command).id)}


@mcp.tool()
def request_task_transition(task_id: UUID, command: schemas.TransitionRequest) -> dict[str, str]:
    """Request a policy-validated task-state transition."""
    with _session() as session:
        task = services.transition_task(session, task_id, command)
        return {"id": str(task.id), "state": task.state}


@mcp.tool()
def get_allowed_transitions(task_id: UUID, actor_id: UUID | None = None) -> list[dict[str, Any]]:
    """Return policy- and readiness-qualified transitions."""
    with _session() as session:
        return services.allowed_for_task(session, services._task(session, task_id), actor_id)


@mcp.tool()
def get_task_readiness(
    task_id: UUID, target_state: TaskState, actor_id: UUID | None = None
) -> dict[str, Any]:
    """Evaluate centralized readiness policy for a target state."""
    with _session() as session:
        result = services.get_readiness(
            session, services._task(session, task_id), target_state, actor_id
        )
        return {
            "ready": result.ready,
            "target_state": result.target_state,
            "missing": [item.__dict__ for item in result.missing],
        }


def run_streamable_http() -> None:
    """Run container transport; STDIO can be wired independently later."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    run_streamable_http()
