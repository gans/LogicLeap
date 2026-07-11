from dataclasses import dataclass, field

from logicleap.domain.enums import EvidenceKind, TaskState


@dataclass(frozen=True)
class ReadinessFacts:
    objective_exists: bool = False
    architect_assigned: bool = False
    actor_count: int = 0
    open_blocking_questions: int = 0
    open_blocking_questions_for_architect: int = 0
    open_blockers: int = 0
    confirmed_requirements: int = 0
    acceptance_criteria: int = 0
    required_decisions_unapproved: int = 0
    evidence_kinds: frozenset[EvidenceKind] = field(default_factory=frozenset)
    preproduction_validation_passed: bool = False
    approved_review_exists: bool = False
    unresolved_blocking_review_findings: int = 0
    unresolved_critical_issues: int = 0
    performed_by_architect: bool = False


@dataclass(frozen=True)
class MissingFact:
    code: str
    message: str


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    target_state: TaskState
    missing: tuple[MissingFact, ...]


def evaluate_readiness(target: TaskState, facts: ReadinessFacts) -> ReadinessResult:
    checks: dict[TaskState, tuple[tuple[bool, str, str], ...]] = {
        TaskState.READY_FOR_ANALYSIS: (
            (facts.objective_exists, "OBJECTIVE_REQUIRED", "Task objective is required"),
            (facts.architect_assigned, "ARCHITECT_REQUIRED", "An architect must be assigned"),
            (facts.actor_count > 0, "ACTOR_REQUIRED", "At least one task actor is required"),
            (
                facts.open_blocking_questions_for_architect == 0,
                "ARCHITECT_BLOCKING_QUESTION",
                "Resolve blocking questions assigned to the architect",
            ),
            (facts.open_blockers == 0, "OPEN_BLOCKERS", "Resolve all open blockers"),
        ),
        TaskState.READY_FOR_IMPLEMENTATION: (
            (
                facts.confirmed_requirements > 0,
                "REQUIREMENT_REQUIRED",
                "At least one confirmed requirement is required",
            ),
            (
                facts.acceptance_criteria > 0,
                "ACCEPTANCE_CRITERION_REQUIRED",
                "At least one acceptance criterion is required",
            ),
            (
                facts.open_blocking_questions == 0,
                "OPEN_BLOCKING_QUESTIONS",
                "Resolve all blocking questions",
            ),
            (facts.open_blockers == 0, "OPEN_BLOCKERS", "Resolve all open blockers"),
            (
                facts.required_decisions_unapproved == 0,
                "REQUIRED_DECISIONS",
                "Approve all required decisions",
            ),
        ),
        TaskState.READY_FOR_REVIEW: (
            (
                EvidenceKind.IMPLEMENTATION in facts.evidence_kinds,
                "IMPLEMENTATION_EVIDENCE",
                "Implementation evidence is required",
            ),
            (
                facts.acceptance_criteria > 0,
                "ACCEPTANCE_CRITERION_REQUIRED",
                "At least one acceptance criterion is required",
            ),
            (facts.open_blockers == 0, "OPEN_BLOCKERS", "Resolve all open blockers"),
        ),
        TaskState.READY_FOR_ARCHITECT_APPROVAL: (
            (facts.approved_review_exists, "APPROVED_REVIEW", "An approved review is required"),
            (
                facts.unresolved_blocking_review_findings == 0,
                "BLOCKING_REVIEW_FINDINGS",
                "Resolve blocking review findings",
            ),
            (facts.open_blockers == 0, "OPEN_BLOCKERS", "Resolve all open blockers"),
        ),
        TaskState.READY_FOR_PRODUCTION: (
            (
                EvidenceKind.PREPRODUCTION_VALIDATION in facts.evidence_kinds,
                "PREPRODUCTION_EVIDENCE",
                "Pre-production validation evidence is required",
            ),
            (
                facts.preproduction_validation_passed,
                "PREPRODUCTION_FAILED",
                "Pre-production validation must pass",
            ),
            (facts.open_blockers == 0, "OPEN_BLOCKERS", "Resolve all open blockers"),
        ),
        TaskState.COMPLETED: (
            (
                EvidenceKind.PRODUCTION_DEPLOYMENT in facts.evidence_kinds,
                "DEPLOYMENT_EVIDENCE",
                "Production deployment evidence is required",
            ),
            (
                EvidenceKind.OBSERVATION in facts.evidence_kinds,
                "OBSERVATION_EVIDENCE",
                "Observation evidence is required",
            ),
            (
                facts.unresolved_critical_issues == 0,
                "CRITICAL_ISSUES",
                "Resolve all critical issues",
            ),
            (
                facts.performed_by_architect,
                "ARCHITECT_REQUIRED",
                "The architect must complete the task",
            ),
        ),
    }
    missing = tuple(
        MissingFact(code, message) for ok, code, message in checks.get(target, ()) if not ok
    )
    return ReadinessResult(not missing, target, missing)
