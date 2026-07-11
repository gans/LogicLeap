# Task state machine

The executable transition matrix is defined in
`logicleap.domain.policies.transitions`. Enum ordering has no workflow meaning.

Entering `BLOCKED` records the source in `blocked_from_state`. A blocked task must
request an explicit valid target; the recorded source is only a suggestion.
`COMPLETED` and `CANCELLED` are terminal.

Readiness is centralized in `logicleap.domain.policies.readiness`. HTTP, UI, and
MCP consume the same evaluation. Completion additionally requires the assigned
task architect to perform the transition.

