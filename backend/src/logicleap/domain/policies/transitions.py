from dataclasses import dataclass

from logicleap.domain.enums import TaskState

TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.DRAFT: frozenset(
        {TaskState.NEEDS_CONTEXT, TaskState.READY_FOR_ANALYSIS, TaskState.CANCELLED}
    ),
    TaskState.NEEDS_CONTEXT: frozenset(
        {TaskState.READY_FOR_ANALYSIS, TaskState.BLOCKED, TaskState.CANCELLED}
    ),
    TaskState.READY_FOR_ANALYSIS: frozenset(
        {TaskState.ANALYZING, TaskState.NEEDS_CONTEXT, TaskState.BLOCKED, TaskState.CANCELLED}
    ),
    TaskState.ANALYZING: frozenset(
        {
            TaskState.NEEDS_CONTEXT,
            TaskState.READY_FOR_IMPLEMENTATION,
            TaskState.BLOCKED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.READY_FOR_IMPLEMENTATION: frozenset(
        {TaskState.IMPLEMENTING, TaskState.NEEDS_CONTEXT, TaskState.BLOCKED, TaskState.CANCELLED}
    ),
    TaskState.IMPLEMENTING: frozenset(
        {
            TaskState.READY_FOR_REVIEW,
            TaskState.NEEDS_CONTEXT,
            TaskState.BLOCKED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.READY_FOR_REVIEW: frozenset(
        {
            TaskState.CHANGES_REQUESTED,
            TaskState.READY_FOR_ARCHITECT_APPROVAL,
            TaskState.BLOCKED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.CHANGES_REQUESTED: frozenset(
        {TaskState.IMPLEMENTING, TaskState.BLOCKED, TaskState.CANCELLED}
    ),
    TaskState.READY_FOR_ARCHITECT_APPROVAL: frozenset(
        {
            TaskState.APPROVED_FOR_PREPRODUCTION,
            TaskState.CHANGES_REQUESTED,
            TaskState.BLOCKED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.APPROVED_FOR_PREPRODUCTION: frozenset(
        {TaskState.VALIDATING_PREPRODUCTION, TaskState.BLOCKED, TaskState.CANCELLED}
    ),
    TaskState.VALIDATING_PREPRODUCTION: frozenset(
        {
            TaskState.READY_FOR_PRODUCTION,
            TaskState.PREPRODUCTION_FAILED,
            TaskState.BLOCKED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.PREPRODUCTION_FAILED: frozenset(
        {TaskState.IMPLEMENTING, TaskState.READY_FOR_REVIEW, TaskState.BLOCKED, TaskState.CANCELLED}
    ),
    TaskState.READY_FOR_PRODUCTION: frozenset(
        {
            TaskState.PRODUCTION_APPROVED,
            TaskState.CHANGES_REQUESTED,
            TaskState.BLOCKED,
            TaskState.CANCELLED,
        }
    ),
    TaskState.PRODUCTION_APPROVED: frozenset(
        {TaskState.DEPLOYING, TaskState.BLOCKED, TaskState.CANCELLED}
    ),
    TaskState.DEPLOYING: frozenset({TaskState.OBSERVING, TaskState.ROLLED_BACK, TaskState.BLOCKED}),
    TaskState.OBSERVING: frozenset({TaskState.COMPLETED, TaskState.ROLLED_BACK, TaskState.BLOCKED}),
    TaskState.ROLLED_BACK: frozenset(
        {TaskState.IMPLEMENTING, TaskState.READY_FOR_REVIEW, TaskState.CANCELLED}
    ),
    TaskState.COMPLETED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class TransitionDecision:
    allowed: bool
    reason: str | None = None


def allowed_transitions(
    state: TaskState, blocked_from_state: TaskState | None = None
) -> frozenset[TaskState]:
    if state is not TaskState.BLOCKED:
        return TRANSITIONS[state]
    # Explicit target is mandatory. Previous state is a suggestion, not an automatic restoration.
    candidates = {source for source, targets in TRANSITIONS.items() if TaskState.BLOCKED in targets}
    if blocked_from_state in candidates:
        return frozenset(candidates)
    return frozenset(candidates)


def validate_transition(
    current: TaskState, target: TaskState, blocked_from_state: TaskState | None = None
) -> TransitionDecision:
    if target not in allowed_transitions(current, blocked_from_state):
        return TransitionDecision(False, f"{current} cannot transition to {target}")
    return TransitionDecision(True)
