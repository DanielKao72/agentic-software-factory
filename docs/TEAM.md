# Team and Agents

## Human roles

Agents propose; people decide. Every gate decision is recorded with a name and a reason.

| Role | Assigned to | Responsibility | Decides at |
|---|---|---|---|
| Product Owner | _pending_ | Owns requirements and resolves ambiguity | Gate 0, Gate 1 |
| Tech Lead | _pending_ | Checks that the plan is technically sound and in scope | Gate 1 |
| Human Reviewer | _pending_ | Accepts, rejects, modifies or defers each finding | Gate 2 |
| Release Manager | _pending_ | Decides READY or NOT_READY; a person performs any merge | Gate 3 |

## Agents

Models are symbols resolved in `factory_app/config.py`. The authoritative definition of each agent is its contract in `factory_app/contracts/`.

| Agent | Responsibility | Model symbol | Tools allowed | Output in `runs/<CR>/` |
|---|---|---|---|---|
| Intake | Analyzes the Change Request against requirements; stops on ambiguity | `PLANNING_MODEL` | Read, list, search | `01-intake-report.md` |
| Planner | Produces the implementation plan for human approval | `PLANNING_MODEL` | Read, list, search | `03-implementation-plan.md` |
| Coder | Implements the approved plan within its bounds | `CODING_MODEL` | Read, list, search, write file, run verification, git commit | `05-coder-report.md`, `11-fix-report.md` in fix rounds |
| Test Analyst | Finds test gaps in the change; cannot declare PASS | `CODING_MODEL` | Read, list, search, write file, run verification | `06-test-analysis.md` |
| Reviewer | Independently reviews the diff against requirements and evidence | `FLASH_MODEL` | Read, list, search, git diff | `08-review-report.md` |
| Security | Independently reviews the diff and scanner results | `FLASH_MODEL` | Read, list, search, git diff, run security scans | `09-security-report.md` |
| Evidence | Consolidates run evidence; reports missing evidence as missing | `LITE_MODEL` | Read, write run evidence | `14-evidence-summary.md` |

No agent can run a shell, merge, or change requirements.
