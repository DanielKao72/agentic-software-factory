"""M2: Coder -> Test Analyst -> deterministic verification gate (no LLM).

Scripted agents call the REAL bounded tools (write_file, git_commit) inside a real git
worktree of a throwaway copy of CampusFlow, so permissions, commits and the gate are
exercised exactly as with Gemini.
"""

import pytest

from factory_app import gitops
from factory_app.tools import git_commit, read_repo_file, write_file
from tests.factory.scripted_replies import INTAKE_PROCEED, PLAN_READY, reply

SERVICE = "campusflow/service.py"
KNOWN_GAP_TEST = '''import pytest

from campusflow.errors import DuplicateRegistrationError
from campusflow.repository import SQLiteCampusFlowRepository
from campusflow.service import CampusFlowService


def test_duplicate_registration_is_rejected():
    service = CampusFlowService(SQLiteCampusFlowRepository())
    event = service.create_event("Popular Event", 3, "owner-1")
    service.register(event.id, "student-1")
    with pytest.raises(DuplicateRegistrationError):
        service.register(event.id, "student-1")
    assert len(service.repository.list_registrations(event.id)) == 1
'''


def _edit(ctx, path, old, new):
    content = read_repo_file(path, tool_context=ctx)["content"]
    assert old in content, f"{old!r} not in {path}"
    return write_file(path, content.replace(old, new), tool_context=ctx)


def coder_fixes_cr003(ctx):
    """What a good Coder does for CR-003: Service rule + error + xfail -> real test."""
    errors = read_repo_file("campusflow/errors.py", tool_context=ctx)["content"]
    write_file("campusflow/errors.py",
               errors + "\n\nclass DuplicateRegistrationError(CampusFlowError):\n    pass\n",
               tool_context=ctx)
    _edit(ctx, SERVICE, "    CapacityReachedError,\n",
          "    CapacityReachedError,\n    DuplicateRegistrationError,\n")
    _edit(ctx, SERVICE, "        # Deliberate gap for CR-003: no duplicate check yet.\n",
          "        if self.repository.has_registration(event_id, user_id):\n"
          "            raise DuplicateRegistrationError(\n"
          "                f\"user {user_id!r} is already registered for event {event_id}\"\n"
          "            )\n")
    write_file("tests/product/test_known_gaps.py", KNOWN_GAP_TEST, tool_context=ctx)
    assert git_commit("Reject duplicate registrations in Service", tool_context=ctx)["ok"]
    return reply("IMPLEMENTED", {"tasks_done": ["TASK-01"]})


def coder_breaks_capacity(ctx):
    """A regression: the capacity rule disappears (test_registration_rejects_when_full)."""
    capacity_rule = ("        if self.repository.count_registrations(event_id) >= event.capacity:\n"
                     "            raise CapacityReachedError(f\"event {event_id} is full\")\n")
    _edit(ctx, SERVICE, capacity_rule, "")
    assert git_commit("Simplify registration", tool_context=ctx)["ok"]
    return reply("IMPLEMENTED", {"tasks_done": ["TASK-01"]})


def analyst_adds_test(ctx):
    write_file("tests/product/test_duplicates_extra.py", (
        "from campusflow.repository import SQLiteCampusFlowRepository\n"
        "from campusflow.service import CampusFlowService\n\n\n"
        "def test_different_users_can_still_register():\n"
        "    service = CampusFlowService(SQLiteCampusFlowRepository())\n"
        "    event = service.create_event('E', 3, 'o')\n"
        "    service.register(event.id, 'a')\n"
        "    service.register(event.id, 'b')\n"
        "    assert len(service.repository.list_registrations(event.id)) == 2\n"),
        tool_context=ctx)
    return reply("TESTS_ADDED", {"gaps": [{"id": "TG-01", "requirement": "AC-CR003.3"}]})


def analyst_no_gaps(ctx):
    return reply("NO_GAPS", {"gaps": []})


def approved_run(make_orch, **replies):
    orch = make_orch("CR-003", intake=[INTAKE_PROCEED], planner=[PLAN_READY], **replies)
    orch.start()
    return orch, orch.approve_plan("APPROVED", "Plan matches CR-003", "Ana / Tech Lead")


# --- happy path ----------------------------------------------------------------------

def test_cr003_xfail_becomes_pass_and_reaches_review(make_orch, runs_dir, git_repo):
    orch, st = approved_run(make_orch, coder=[coder_fixes_cr003],
                            test_analyst=[analyst_adds_test])
    assert st["status"] == "REVIEWING", st["status_reason"]
    assert st["tests_before"] == {"passed": 7, "xfailed": 1}
    assert st["verification"]["status"] == "PASS"
    assert st["verification"]["tests"] == 9 and st["verification"]["failed"] == 0
    assert st["verification"]["xfailed"] == 0
    report = (runs_dir / "CR-003" / "07-verification.txt").read_text()
    assert "RESULT: PASS" in report and "## integrity: PASS" in report
    # Work happened on factory/CR-003 in a worktree; main is untouched.
    assert gitops.head(git_repo, "main") == st["base_commit"]
    log = gitops._git(orch.worktree, "log", "--format=%an %s", f"{st['base_commit']}..HEAD")
    assert "factory-coder [CR-003]" in log and "factory-test-analyst" in log


def test_coder_and_test_analyst_get_the_diff_not_each_others_reasoning(make_orch):
    orch, _ = approved_run(make_orch, coder=[coder_fixes_cr003],
                           test_analyst=[analyst_no_gaps])
    analyst_call = next(c for c in orch.runner.calls if c["agent"] == "test_analyst")
    assert "git diff main...factory/CR-003" in analyst_call["message"]
    assert "DuplicateRegistrationError" in analyst_call["message"]  # the diff itself
    assert "05-coder-report.md" not in analyst_call["message"]


# --- E03: broken regression never reaches review ---------------------------------------

def test_e03_regression_goes_back_to_coder_then_passes(make_orch, runs_dir):
    orch, st = approved_run(make_orch, coder=[coder_breaks_capacity, coder_fixes_cr003_after],
                            test_analyst=[analyst_no_gaps, analyst_no_gaps])
    assert st["status"] == "REVIEWING"
    history = [h["to"] for h in st["history"]]
    assert history.index("VERIFY_FAILED") < history.index("REVIEWING")
    failed = (runs_dir / "CR-003" / "07-verification.r1.txt").read_text()
    assert "RESULT: FAIL" in failed and "test_registration_rejects_when_event_is_full" in failed
    second_coder = [c for c in orch.runner.calls if c["agent"] == "coder"][1]
    assert "07-verification.txt" in second_coder["message"]  # Coder sees the failure


def coder_fixes_cr003_after(ctx):
    """Second attempt: restore the capacity rule and implement the real fix."""
    _edit(ctx, SERVICE, "        # Deliberate gap for CR-003: no duplicate check yet.\n",
          "        if self.repository.count_registrations(event_id) >= event.capacity:\n"
          "            raise CapacityReachedError(f\"event {event_id} is full\")\n"
          "        # Deliberate gap for CR-003: no duplicate check yet.\n")
    return coder_fixes_cr003(ctx)


def test_e03_persistent_regression_escalates_and_never_reaches_review(make_orch):
    orch, st = approved_run(make_orch, coder=[coder_breaks_capacity, coder_retry_without_fix,
                                              coder_retry_without_fix],
                            test_analyst=[analyst_no_gaps] * 3)
    assert st["status"] == "WAITING_HUMAN"
    assert "verification failed after 3" in st["status_reason"]
    assert "REVIEWING" not in [h["to"] for h in st["history"]]
    assert st["verification"]["status"] == "FAIL"


def coder_retry_without_fix(ctx):
    """A Coder retry that touches a file but leaves the branch's problem in place."""
    errors = read_repo_file("campusflow/errors.py", tool_context=ctx)["content"]
    write_file("campusflow/errors.py", errors + "\n", tool_context=ctx)
    git_commit("retry", tool_context=ctx)
    return reply("IMPLEMENTED", {"tasks_done": []})


# --- bounded writes ------------------------------------------------------------------

def test_coder_cannot_write_requirements_or_outside_plan(make_orch, git_repo):
    results = {}

    def rogue_coder(ctx):
        results["docs"] = write_file("docs/REQUIREMENTS.md", "relaxed", tool_context=ctx)
        results["agents"] = write_file("AGENTS.md", "no rules", tool_context=ctx)
        results["off_plan"] = write_file("campusflow/repository.py", "x", tool_context=ctx)
        results["escape"] = write_file("../../evil.py", "x", tool_context=ctx)
        return reply("ESCALATE", {"reason": "permission_denied"})

    orch, st = approved_run(make_orch, coder=[rogue_coder])
    assert all(not r["ok"] and r["error"].startswith("DENIED") for r in results.values())
    assert gitops.dirty_files(orch.worktree) == []
    assert st["status"] == "WAITING_HUMAN"
    denied = [e for e in _context(orch) if e.get("denied")]
    assert len(denied) == 4


def _context(orch):
    import json

    log = json.loads((orch.run_dir / "context-log.json").read_text())
    return [call for entry in log for call in entry["tool_calls"]]


def test_test_analyst_cannot_touch_application_code(make_orch):
    results = {}

    def sneaky_analyst(ctx):
        results["src"] = write_file(SERVICE, "pass\n", tool_context=ctx)
        results["commit"] = git_commit("x", tool_context=ctx)  # no git_commit permission
        return reply("NO_GAPS", {"gaps": []})

    approved_run(make_orch, coder=[coder_fixes_cr003], test_analyst=[sneaky_analyst])
    assert not results["src"]["ok"] and not results["commit"]["ok"]


# --- integrity gate ------------------------------------------------------------------

def test_deleting_a_test_fails_verification(make_orch, runs_dir):
    def analyst_deletes(ctx):
        content = read_repo_file("tests/product/test_service.py", tool_context=ctx)["content"]
        start = content.index("def test_registration_rejects_when_event_is_full")
        end = content.index("def test_cancel_existing_registration")
        write_file("tests/product/test_service.py", content[:start] + content[end:],
                   tool_context=ctx)
        return reply("NO_GAPS", {"gaps": []})

    _, st = approved_run(make_orch, coder=[coder_fixes_cr003] + [coder_retry_without_fix] * 2,
                         test_analyst=[analyst_deletes] + [analyst_no_gaps] * 2)
    assert st["status"] != "REVIEWING"
    first = (runs_dir / "CR-003" / "07-verification.r1.txt").read_text()
    assert "test_registration_rejects_when_event_is_full was deleted" in first


def test_skipping_a_test_fails_verification(make_orch, runs_dir):
    def analyst_skips(ctx):
        _edit(ctx, "tests/product/test_service.py",
              "def test_cancel_missing_registration_is_clear",
              "@pytest.mark.skip(reason='flaky')\ndef test_cancel_missing_registration_is_clear")
        return reply("NO_GAPS", {"gaps": []})

    approved_run(make_orch, coder=[coder_fixes_cr003] + [coder_retry_without_fix] * 2,
                 test_analyst=[analyst_skips] + [analyst_no_gaps] * 2)
    first = (runs_dir / "CR-003" / "07-verification.r1.txt").read_text()
    assert "gained @skip" in first


def test_plan_changed_after_approval_blocks_coder(make_orch, runs_dir):
    stop = reply("ESCALATE", {"reason": "pause"})
    orch, st = approved_run(make_orch, coder=[stop])
    assert st["status"] == "WAITING_HUMAN"
    plan = runs_dir / "CR-003" / "03-implementation-plan.md"
    plan.write_text(plan.read_text() + "\nAlso edit docs/REQUIREMENTS.md\n")
    st = orch.rework("continue", by="Ana / Tech Lead")
    assert st["status"] == "WAITING_HUMAN"
    assert "plan changed after human approval" in st["status_reason"]


def test_gitops_has_no_merge_or_push():
    names = {n for n in dir(gitops) if not n.startswith("_")}
    assert not {n for n in names if "merge" in n or "push" in n}


@pytest.mark.parametrize("bad", ["main", "../x", ""])
def test_write_tools_refuse_without_a_factory_worktree(bad):
    from factory_app.tools import LocalToolContext

    ctx = LocalToolContext("CoderAgent", {"workspace": bad, "plan_files": [SERVICE],
                                          "context_log": []})
    assert not write_file(SERVICE, "x", tool_context=ctx)["ok"]
