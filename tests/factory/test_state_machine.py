import pytest

from factory_app.state import (
    TERMINAL,
    WAITING,
    HumanDecisionRequired,
    IllegalTransition,
    Status,
    new_state,
    transition,
)

S = Status
HUMAN = {"gate": "plan", "decision": "APPROVED", "reason": "ok", "by": "TL", "at": "now"}


def test_happy_path_is_legal_with_human_decisions_at_gates():
    st = new_state("CR-001", "main", 2)
    transition(st, S.PLANNING)
    transition(st, S.WAITING_PLAN_APPROVAL)
    transition(st, S.IMPLEMENTING, decision=HUMAN)
    for to in (S.TEST_ANALYSIS, S.VERIFYING, S.REVIEWING, S.CONSOLIDATING_EVIDENCE,
               S.WAITING_RELEASE_DECISION):
        transition(st, to)
    transition(st, S.READY_FOR_HUMAN_MERGE, decision=HUMAN)
    assert st["status"] == "READY_FOR_HUMAN_MERGE"
    assert st["metrics"]["human_interventions"] == 2
    assert len(st["history"]) == 9


@pytest.mark.parametrize("to", [S.IMPLEMENTING, S.REVIEWING, S.READY_FOR_HUMAN_MERGE])
def test_skipping_stages_is_illegal(to):
    st = new_state("CR-001", "main", 2)
    with pytest.raises(IllegalTransition):
        transition(st, to)


@pytest.mark.parametrize("waiting", sorted(WAITING))
def test_no_waiting_gate_can_be_left_without_a_human_decision(waiting):
    st = new_state("CR-001", "main", 2)
    st["status"] = waiting.value
    from factory_app.state import TRANSITIONS

    for to in TRANSITIONS[waiting]:
        with pytest.raises(HumanDecisionRequired):
            transition(st, to)


def test_verification_failure_never_reaches_review():
    st = new_state("CR-001", "main", 2)
    st["status"] = S.VERIFY_FAILED.value
    with pytest.raises(IllegalTransition):
        transition(st, S.REVIEWING)


@pytest.mark.parametrize("terminal", sorted(TERMINAL))
def test_terminal_states_never_change(terminal):
    st = new_state("CR-001", "main", 2)
    st["status"] = terminal.value
    with pytest.raises(IllegalTransition):
        transition(st, S.IMPLEMENTING, decision=HUMAN)


def test_nothing_can_reach_ready_except_the_release_gate():
    from factory_app.state import TRANSITIONS

    sources = [s for s, targets in TRANSITIONS.items() if S.READY_FOR_HUMAN_MERGE in targets]
    assert sources == [S.WAITING_RELEASE_DECISION]


def test_escalation_remembers_where_it_came_from():
    st = new_state("CR-001", "main", 2)
    transition(st, S.WAITING_HUMAN, "unparseable report")
    assert st["escalated_from"] == "INTAKE_PENDING"
