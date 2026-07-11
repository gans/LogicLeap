import pytest

from logicleap.domain.enums import TaskState
from logicleap.domain.policies.transitions import (
    TRANSITIONS,
    allowed_transitions,
    validate_transition,
)


def test_terminal_states_have_no_transitions() -> None:
    assert TRANSITIONS[TaskState.COMPLETED] == frozenset()
    assert TRANSITIONS[TaskState.CANCELLED] == frozenset()


@pytest.mark.parametrize("source,targets", TRANSITIONS.items())
def test_matrix_accepts_every_configured_edge(
    source: TaskState, targets: frozenset[TaskState]
) -> None:
    for target in targets:
        assert validate_transition(source, target).allowed


def test_blocked_requires_an_explicit_valid_target() -> None:
    assert TaskState.IMPLEMENTING in allowed_transitions(TaskState.BLOCKED, TaskState.IMPLEMENTING)
    assert not validate_transition(TaskState.BLOCKED, TaskState.COMPLETED).allowed
