"""Factory state machine + runs/<CR>/factory-state.json (written only by the orchestrator).

Rules enforced here, in code:
- only transitions listed in TRANSITIONS are legal (anything else raises);
- leaving a WAITING_* status requires a recorded human decision;
- terminal statuses never change.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path


class Status(StrEnum):
    INTAKE_PENDING = "INTAKE_PENDING"
    WAITING_CLARIFICATION = "WAITING_CLARIFICATION"  # Gate 0 (Product Owner)
    PLANNING = "PLANNING"
    WAITING_PLAN_APPROVAL = "WAITING_PLAN_APPROVAL"  # Gate 1 (PO + Tech Lead)
    IMPLEMENTING = "IMPLEMENTING"
    TEST_ANALYSIS = "TEST_ANALYSIS"
    VERIFYING = "VERIFYING"
    VERIFY_FAILED = "VERIFY_FAILED"
    REVIEWING = "REVIEWING"
    WAITING_FINDING_DECISIONS = "WAITING_FINDING_DECISIONS"  # Gate 2 (Human Reviewer)
    FIXING = "FIXING"
    REVERIFYING = "REVERIFYING"
    REREVIEWING = "REREVIEWING"
    CONSOLIDATING_EVIDENCE = "CONSOLIDATING_EVIDENCE"
    WAITING_RELEASE_DECISION = "WAITING_RELEASE_DECISION"  # Gate 3 (Release Manager)
    WAITING_HUMAN = "WAITING_HUMAN"  # an agent hit a stop condition
    READY_FOR_HUMAN_MERGE = "READY_FOR_HUMAN_MERGE"  # maximum automated state
    NOT_READY = "NOT_READY"
    REJECTED = "REJECTED"


S = Status
TERMINAL = {S.READY_FOR_HUMAN_MERGE, S.NOT_READY, S.REJECTED}
WAITING = {s for s in Status if s.startswith("WAITING_")}
# Statuses from which an agent may escalate to WAITING_HUMAN.
AGENT_STAGES = {S.INTAKE_PENDING, S.PLANNING, S.IMPLEMENTING, S.TEST_ANALYSIS, S.REVIEWING,
                S.FIXING, S.REREVIEWING, S.CONSOLIDATING_EVIDENCE, S.VERIFYING, S.REVERIFYING,
                S.VERIFY_FAILED}

TRANSITIONS: dict[Status, set[Status]] = {
    S.INTAKE_PENDING: {S.WAITING_CLARIFICATION, S.PLANNING},
    S.WAITING_CLARIFICATION: {S.INTAKE_PENDING, S.REJECTED},
    S.PLANNING: {S.WAITING_PLAN_APPROVAL, S.WAITING_CLARIFICATION},
    S.WAITING_PLAN_APPROVAL: {S.IMPLEMENTING, S.PLANNING, S.REJECTED},
    S.IMPLEMENTING: {S.TEST_ANALYSIS},
    S.TEST_ANALYSIS: {S.VERIFYING},
    S.VERIFYING: {S.REVIEWING, S.VERIFY_FAILED},
    S.VERIFY_FAILED: {S.IMPLEMENTING, S.NOT_READY},
    S.REVIEWING: {S.WAITING_FINDING_DECISIONS, S.CONSOLIDATING_EVIDENCE},
    S.WAITING_FINDING_DECISIONS: {S.FIXING, S.CONSOLIDATING_EVIDENCE, S.IMPLEMENTING,
                                  S.NOT_READY},
    S.FIXING: {S.REVERIFYING},
    S.REVERIFYING: {S.REREVIEWING, S.FIXING, S.NOT_READY},
    S.REREVIEWING: {S.WAITING_FINDING_DECISIONS, S.CONSOLIDATING_EVIDENCE},
    S.CONSOLIDATING_EVIDENCE: {S.WAITING_RELEASE_DECISION},
    S.WAITING_RELEASE_DECISION: {S.READY_FOR_HUMAN_MERGE, S.NOT_READY, S.IMPLEMENTING},
    # A human resolves an escalation by sending the work back to a stage or stopping it.
    S.WAITING_HUMAN: AGENT_STAGES | {S.NOT_READY, S.REJECTED},
}
for _stage in AGENT_STAGES:
    TRANSITIONS[_stage] = TRANSITIONS.get(_stage, set()) | {S.WAITING_HUMAN}


class IllegalTransition(RuntimeError):
    pass


class HumanDecisionRequired(IllegalTransition):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_state(change_id: str, base_branch: str, max_fix_rounds: int) -> dict:
    """Starter keys kept (change_id, created_at, status, human_gates, verification,
    review, security, iterations), extended as specified for the factory."""
    return {
        "change_id": change_id,
        "created_at": now(),
        "updated_at": now(),
        "branch": f"factory/{change_id}",
        "base_branch": base_branch,
        "status": S.INTAKE_PENDING.value,
        "status_reason": "",
        "escalated_from": None,
        "fix_round": 0,
        "max_fix_rounds": max_fix_rounds,
        "iterations": 0,
        "requirements": "PENDING",
        "plan": "PENDING",
        "implementation": "PENDING",
        "test_analysis": "PENDING",
        "verification": {"status": "NOT_RUN"},
        "review": {"status": "pending", "must_fix": 0, "should_fix": 0},
        "security": {"status": "pending", "high": 0, "medium": 0},
        "human_gates": {"requirements": "PENDING", "plan": "PENDING",
                        "review": "PENDING", "release": "PENDING"},
        "decisions": [],
        "metrics": {"llm_calls": 0, "rate_limit_retries": 0, "overload_retries": 0,
                    "human_interventions": 0, "coder_review_iterations": 0},
        "history": [],
    }


def transition(state: dict, to: Status, reason: str = "", *, decision: dict | None = None) -> None:
    """The only way `status` changes. Mutates `state`; caller persists it."""
    current = Status(state["status"])
    if current in TERMINAL:
        raise IllegalTransition(f"{current} is terminal")
    if to not in TRANSITIONS.get(current, set()):
        raise IllegalTransition(f"{current} -> {to} is not a legal transition")
    if current in WAITING and decision is None:
        raise HumanDecisionRequired(f"{current} can only be left by a recorded human decision")
    if decision is not None:
        state["decisions"].append(decision)
        state["metrics"]["human_interventions"] += 1
    if to == S.WAITING_HUMAN:
        state["escalated_from"] = current.value
    state["history"].append({"at": now(), "from": current.value, "to": to.value,
                             "reason": reason})
    state["status"] = to.value
    state["status_reason"] = reason


def save(run_dir: Path, state: dict) -> None:
    """Atomic write (checkpoint). Also refreshes runs/index.json for the dashboard."""
    state["updated_at"] = now()
    path = run_dir / "factory-state.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    _update_index(run_dir.parent, state)


def load(run_dir: Path) -> dict:
    path = run_dir / "factory-state.json"
    if not path.exists():
        raise FileNotFoundError(f"run not found: {run_dir.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _update_index(runs_dir: Path, state: dict) -> None:
    index_path = runs_dir / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        index = {"runs": {}}
    index["runs"][state["change_id"]] = {"status": state["status"],
                                         "updated_at": state["updated_at"]}
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
