# Architecture

## Product

```text
FastAPI adapter
      |
      v
CampusFlowService        <- business rules
      |
      v
SQLiteCampusFlowRepository
      |
      v
SQLite
```

Rules: API does not implement business policy; Repository does not decide business policy; Service coordinates behavior.

## Factory

```text
Change Request -> Intake -> Planner -> HUMAN GATE -> Coder -> Verification
                                                   -> Reviewer + Security
                                                   -> HUMAN REVIEW
                                                   -> Fix / Re-review
                                                   -> HUMAN RELEASE
                                                   -> PR Evidence
```

The Reviewer must inspect requirements, architecture, changed code, tests, verification evidence and actual APIs/dependencies. It must not treat the Coder's own claims as proof.

### Control model

`factory_app/orchestrator.py` is deterministic code and the only writer of `runs/<CR>/factory-state.json`. Agents return reports; they do not choose the next step. `factory_app/state.py` rejects any transition that is not declared, and a `WAITING_*` status can only be left through a recorded human decision.

| Gate | Status | Decided by | Purpose |
|---|---|---|---|
| Gate 0 | `WAITING_CLARIFICATION` | Product Owner | Resolve ambiguous requirements |
| Gate 1 | `WAITING_PLAN_APPROVAL` | Product Owner + Tech Lead | Approve, modify or reject the plan |
| Gate 2 | `WAITING_FINDING_DECISIONS` | Human Reviewer | Decide each review and security finding |
| Gate 3 | `WAITING_RELEASE_DECISION` | Release Manager | Decide READY or NOT_READY |

`WAITING_HUMAN` is the escalation path when an agent hits a stop condition. `READY_FOR_HUMAN_MERGE` is the furthest the factory can go; it never merges. Roles and agents are listed in `docs/TEAM.md`.
