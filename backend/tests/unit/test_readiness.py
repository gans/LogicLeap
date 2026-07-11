from logicleap.domain.enums import EvidenceKind, TaskState
from logicleap.domain.policies.readiness import ReadinessFacts, evaluate_readiness


def test_analysis_readiness_reports_all_missing_information() -> None:
    result = evaluate_readiness(TaskState.READY_FOR_ANALYSIS, ReadinessFacts())

    assert not result.ready
    assert {item.code for item in result.missing} == {
        "OBJECTIVE_REQUIRED",
        "ARCHITECT_REQUIRED",
        "ACTOR_REQUIRED",
    }


def test_implementation_readiness_requires_approved_required_decisions() -> None:
    facts = ReadinessFacts(
        confirmed_requirements=1, acceptance_criteria=1, required_decisions_unapproved=1
    )

    result = evaluate_readiness(TaskState.READY_FOR_IMPLEMENTATION, facts)

    assert [item.code for item in result.missing] == ["REQUIRED_DECISIONS"]


def test_completion_requires_delivery_evidence_and_architect() -> None:
    facts = ReadinessFacts(
        evidence_kinds=frozenset({EvidenceKind.PRODUCTION_DEPLOYMENT, EvidenceKind.OBSERVATION}),
        performed_by_architect=True,
    )

    assert evaluate_readiness(TaskState.COMPLETED, facts).ready
