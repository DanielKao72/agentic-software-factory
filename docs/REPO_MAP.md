# Repository Map

| Path | Purpose |
|---|---|
| `campusflow/domain.py` | Product entities |
| `campusflow/repository.py` | SQLite persistence |
| `campusflow/service.py` | Business rules |
| `campusflow/api.py` | HTTP adapter |
| `campusflow/errors.py` | Product error types |
| `factory_app/orchestrator.py` | Deterministic state machine driver; only writer of run state |
| `factory_app/state.py` | Statuses, legal transitions, human-gate enforcement |
| `factory_app/contracts/*.yaml` | Per-agent contract: context, allowed/denied tools, output, stop conditions |
| `factory_app/prompts.py` | Agent prompts generated from the contracts |
| `factory_app/agents.py` | Builds each ADK agent with only its contract's tools |
| `factory_app/tools.py` | Bounded tools (read/list/search...), permission-checked and logged |
| `factory_app/permissions.py` | Least-privilege permission matrix |
| `factory_app/reports.py` | Parses `VERDICT:` + JSON agent reports |
| `factory_app/llm.py` | Single model-call wrapper (429/503 backoff, fresh session per agent) |
| `factory_app/config.py` | Models, limits, API-key handling |
| `factory_app/agent.py` | ADK root agent (Intake -> Planner pipeline for `adk web` / evals) |
| `change_requests/` | Work input |
| `scripts/factory.py` | Factory CLI: start, clarify, approve, decide, release, resume, status, rework |
| `scripts/` | Other deterministic run/gate helpers |
| `tests/product/` | CampusFlow tests |
| `tests/factory/` | Deterministic factory tests (gates, permissions, state machine) |
| `tests/eval/` | Agent evaluation datasets |
| `runs/` | Generated evidence (one folder per Change Request, not versioned) |
| `docs/TEAM.md` | Human roles, gate owners and agent responsibilities |
| `docs/evidence/` | Versioned copies of selected run evidence |
