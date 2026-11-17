"""The CLI is the human interface to the gates; it must refuse to skip them."""

import pytest

from factory_app.orchestrator import Orchestrator, ScriptedRunner
from scripts.approve_gate import main as approve_gate_main
from scripts.factory import main as factory_main
from tests.factory.scripted_replies import INTAKE_CLARIFY, INTAKE_PROCEED, PLAN_READY


@pytest.fixture
def waiting_plan(runs_dir):
    Orchestrator("CR-003", runner=ScriptedRunner(
        {"intake": [INTAKE_PROCEED], "planner": [PLAN_READY]}), runs_dir=runs_dir).start()
    return runs_dir


def test_resume_refuses_at_a_human_gate(waiting_plan, capsys):
    assert factory_main(["resume", "CR-003"]) == 1
    assert "human decision is required" in capsys.readouterr().err


def test_approve_without_name_is_rejected(waiting_plan):
    with pytest.raises(SystemExit):  # argparse: --by is required
        factory_main(["approve", "CR-003", "plan", "APPROVED", "ok"])


def test_starter_approve_gate_script_now_requires_by_and_uses_orchestrator(waiting_plan):
    with pytest.raises(SystemExit):
        approve_gate_main(["CR-003", "plan", "APPROVED", "Plan reviewed"])
    assert approve_gate_main(["CR-003", "plan", "APPROVED", "Plan reviewed",
                              "--by", "Ana / Tech Lead"]) == 0
    assert (waiting_plan / "CR-003" / "04-human-plan-approval.md").exists()


def test_clarify_is_refused_when_not_waiting_for_clarification(waiting_plan, capsys):
    assert factory_main(["clarify", "CR-003", "policy", "--by", "PO"]) == 1
    assert "not WAITING_CLARIFICATION" in capsys.readouterr().err


def test_status_prints_next_human_action(runs_dir, capsys):
    Orchestrator("CR-005", runner=ScriptedRunner({"intake": [INTAKE_CLARIFY]}),
                 runs_dir=runs_dir).start()
    assert factory_main(["status", "CR-005"]) == 0
    out = capsys.readouterr().out
    assert "WAITING_CLARIFICATION" in out and "factory clarify CR-005" in out


def test_unknown_or_malformed_change_id(capsys):
    assert factory_main(["status", "../../etc"]) == 1
    assert "invalid change id" in capsys.readouterr().err
