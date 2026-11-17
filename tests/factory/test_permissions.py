"""The permission matrix is enforced in code -- by the tools, not by the prompts."""

import pytest

from factory_app.permissions import MATRIX, PermissionDenied, check_read, check_write, require
from factory_app.tools import list_repo_files, read_repo_file, search_repo

EXPECTED = {  # agent: (read, search, edit src, edit tests, exec)
    "intake": (True, True, False, False, False),
    "planner": (True, True, False, False, False),
    "coder": (True, True, True, True, True),
    "test_analyst": (True, True, False, True, True),
    "reviewer": (True, True, False, False, False),
    "security": (True, True, False, False, True),
}


@pytest.mark.parametrize("agent", EXPECTED)
def test_permission_matrix(agent):
    read, search, src, tests, exec_ = EXPECTED[agent]
    actions = MATRIX[agent]
    assert ("read" in actions) == read
    assert ("search" in actions) == search
    assert ("write_src" in actions) == src
    assert ("write_tests" in actions) == tests
    assert bool(actions & {"exec_verify", "exec_scan"}) == exec_
    if agent == "security":
        assert "exec_verify" not in actions  # scanners only


def test_no_agent_can_merge_or_push():
    for actions in MATRIX.values():
        assert not actions & {"merge", "push"}
    with pytest.raises(PermissionDenied):
        require("coder", "merge")


@pytest.mark.parametrize("path", [
    "docs/REQUIREMENTS.md", "docs/SPEC.md", "change_requests/CR-001-waitlist.md",
    "AGENTS.md", ".github/workflows/verify.yml", "factory_app/permissions.py",
    "scripts/factory.py", ".env", "pyproject.toml", "runs/CR-001/factory-state.json",
])
@pytest.mark.parametrize("agent", list(MATRIX))
def test_protected_paths_are_never_writable(agent, path):
    with pytest.raises(PermissionDenied):
        check_write(agent, path, [path])  # even if a plan listed it


@pytest.mark.parametrize("path", ["../outside.py", "/etc/passwd", "C:/Windows/x.py",
                                  "campusflow/../docs/REQUIREMENTS.md"])
def test_path_escapes_are_rejected(path):
    with pytest.raises(PermissionDenied):
        check_write("coder", path, [path])


def test_coder_writes_only_files_in_the_approved_plan():
    plan = ["campusflow/service.py", "tests/product/test_waitlist.py"]
    assert check_write("coder", "campusflow/service.py", plan) == "campusflow/service.py"
    with pytest.raises(PermissionDenied, match="approved plan"):
        check_write("coder", "campusflow/repository.py", plan)


def test_test_analyst_writes_tests_only():
    assert check_write("test_analyst", "tests/product/test_x.py", None)
    with pytest.raises(PermissionDenied):
        check_write("test_analyst", "campusflow/service.py", ["campusflow/service.py"])


@pytest.mark.parametrize("agent", ["intake", "planner", "reviewer", "security", "evidence"])
def test_read_only_agents_cannot_write_anything(agent):
    for path in ("campusflow/service.py", "tests/product/test_x.py"):
        with pytest.raises(PermissionDenied):
            check_write(agent, path, [path])


def test_run_artifacts_readable_only_when_in_contract():
    allowed = ["runs/CR-001/00-change-request.md"]
    assert check_read("reviewer", "runs/CR-001/00-change-request.md", allowed)
    with pytest.raises(PermissionDenied):
        check_read("reviewer", "runs/CR-001/05-coder-report.md", allowed)


# --- the tools themselves enforce it -------------------------------------------------

class FakeToolContext:
    def __init__(self, agent_name, **state):
        self.agent_name = agent_name
        self.state = {"context_log": [], **state}


def test_read_tool_denies_and_logs_secrets_and_factory_code():
    ctx = FakeToolContext("IntakeAgent")
    for path in (".env", "factory_app/permissions.py", "../.env"):
        result = read_repo_file(path, tool_context=ctx)
        assert not result["ok"] and result["error"].startswith("DENIED")
    assert [e["ok"] for e in ctx.state["context_log"]] == [False, False, False]


def test_read_tool_reads_allowed_file_and_logs_it():
    ctx = FakeToolContext("PlannerAgent")
    result = read_repo_file("docs/REQUIREMENTS.md", tool_context=ctx)
    assert result["ok"] and "FR-03" in result["content"]
    assert ctx.state["context_log"][-1] == {"agent": "planner", "tool": "read_repo_file",
                                            "target": "docs/REQUIREMENTS.md", "ok": True}


def test_reviewer_tool_cannot_read_coder_report(tmp_path):
    (tmp_path / "CR-001").mkdir()
    (tmp_path / "CR-001" / "05-coder-report.md").write_text("I am sure it works")
    ctx = FakeToolContext("ReviewerAgent", runs_dir=str(tmp_path),
                          run_files=["runs/CR-001/00-change-request.md"])
    result = read_repo_file("runs/CR-001/05-coder-report.md", tool_context=ctx)
    assert not result["ok"] and "DENIED" in result["error"]


def test_search_tool_finds_code_and_refuses_runs_and_factory():
    ctx = FakeToolContext("PlannerAgent")
    hits = search_repo("def register", "campusflow", tool_context=ctx)
    assert hits["ok"] and any(h["file"] == "campusflow/service.py" for h in hits["hits"])
    for path in ("runs", "factory_app", ".github"):
        assert not search_repo("x", path, tool_context=ctx)["ok"]


def test_list_tool_never_lists_factory_or_dotfiles():
    files = list_repo_files("", tool_context=FakeToolContext("IntakeAgent"))["files"]
    assert files and not any(f.startswith(("factory_app/", "runs/", ".")) for f in files)
