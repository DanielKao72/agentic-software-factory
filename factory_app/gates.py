"""Deterministic verification gate. LLM output is never verification; this is.

Checks (all must pass; a failing change NEVER reaches review):
  pytest      any failure/error blocks (before/after counts recorded)
  ruff        any violation blocks
  contract    scripts/verify_repo.py --contract (the factory's copy, not the branch's)
  integrity   AST + git diff: tests deleted or weakened, skip/xfail added, an xfail
              removed from a test that still fails, paths outside campusflow/ and
              tests/ modified, uncommitted changes
Security scanners join this gate in M3.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from . import gitops
from .config import REPO_ROOT

WRITABLE_ROOTS = ("campusflow/", "tests/")
LINT_PATHS = ("campusflow", "tests", "factory_app", "scripts")


@dataclass
class Check:
    name: str
    ok: bool
    summary: str
    output: str = ""


@dataclass
class GateResult:
    passed: bool
    checks: list[Check]
    counts: dict = field(default_factory=dict)

    def summary(self) -> dict:
        by = {c.name: c for c in self.checks}
        return {
            "status": "PASS" if self.passed else "FAIL",
            "tests": self.counts.get("passed", 0),
            "failed": self.counts.get("failed", 0) + self.counts.get("errors", 0),
            "xfailed": self.counts.get("xfailed", 0),
            "lint": "PASS" if by.get("ruff") and by["ruff"].ok else "FAIL",
            "integrity": "PASS" if by.get("integrity") and by["integrity"].ok else "FAIL",
            "failing_checks": [c.name for c in self.checks if not c.ok],
        }


def _run(argv: list[str], cwd: Path, timeout: int = 600) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, cwd=cwd, text=True, capture_output=True,
                              timeout=timeout, check=False)
    except FileNotFoundError as exc:
        return 127, f"TOOL_UNAVAILABLE: {exc}"
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {timeout}s"
    return done.returncode, (done.stdout + done.stderr)


# --- pytest -------------------------------------------------------------------------

def run_pytest(workspace: Path, junit: Path) -> tuple[Check, dict, dict[str, str]]:
    code, out = _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                      f"--junitxml={junit}"], workspace)
    counts = pytest_counts(out)
    outcomes = junit_outcomes(junit)
    ok = code == 0 and counts.get("failed", 0) == 0 and counts.get("errors", 0) == 0
    return Check("pytest", ok, summary_line(out) or f"exit {code}", out), counts, outcomes


def pytest_counts(output: str) -> dict:
    counts = {}
    for n, kind in re.findall(r"(\d+) (passed|failed|errors?|xfailed|xpassed|skipped)",
                              summary_line(output)):
        counts["errors" if kind.startswith("error") else kind] = int(n)
    return counts


def summary_line(output: str) -> str:
    lines = [ln.strip("= ").strip() for ln in output.splitlines()
             if re.search(r"\d+ (passed|failed|error|xfailed|skipped)", ln)]
    return lines[-1] if lines else ""


def junit_outcomes(junit: Path) -> dict[str, str]:
    """'tests/product/test_x.py::test_name' -> passed | failed | skipped | xfailed."""
    if not junit.exists():
        return {}
    outcomes = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        path = case.get("classname", "").replace(".", "/") + ".py"
        key = f"{path}::{case.get('name')}"
        if case.find("failure") is not None or case.find("error") is not None:
            outcomes[key] = "failed"
        elif (skip := case.find("skipped")) is not None:
            outcomes[key] = "xfailed" if "xfail" in (skip.get("type", "") +
                                                      skip.get("message", "")) else "skipped"
        else:
            outcomes[key] = "passed"
    return outcomes


# --- ruff / repo contract ------------------------------------------------------------

def run_ruff(workspace: Path) -> Check:
    paths = [p for p in LINT_PATHS if (workspace / p).exists()]
    code, out = _run([sys.executable, "-m", "ruff", "check", *paths], workspace)
    return Check("ruff", code == 0, "clean" if code == 0 else f"exit {code}", out)


def run_contract(workspace: Path) -> Check:
    code, out = _run([sys.executable, str(REPO_ROOT / "scripts" / "verify_repo.py"),
                      "--contract", "--root", str(workspace)], workspace)
    return Check("contract", code == 0, out.strip().splitlines()[-1] if out.strip() else "",
                 out)


# --- integrity ------------------------------------------------------------------------

def _test_profile(source: str | None) -> dict[str, dict]:
    """test function name -> {'asserts': n, 'markers': {...}} (AST, no execution)."""
    if source is None:
        return {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"<syntax-error>": {"asserts": 0, "markers": set()}}
    profile = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and \
                node.name.startswith("test"):
            asserts = sum(isinstance(n, ast.Assert) or (
                isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "raises")
                for n in ast.walk(node))
            markers = {getattr(d.func if isinstance(d, ast.Call) else d, "attr", "")
                       for d in node.decorator_list}
            profile[node.name] = {"asserts": asserts,
                                  "markers": markers & {"skip", "skipif", "xfail"}}
    return profile


def check_integrity(workspace: Path, base_sha: str, outcomes: dict[str, str]) -> Check:
    problems: list[str] = []
    dirty = gitops.dirty_files(workspace)
    if dirty:
        problems.append(f"uncommitted changes: {dirty}")
    changed = gitops.changed_files(workspace, base_sha)
    for path in changed:
        if not path.startswith(WRITABLE_ROOTS):
            problems.append(f"modified protected path: {path}")
    for path in (p for p in changed if p.startswith("tests/") and p.endswith(".py")):
        before = _test_profile(gitops.show(workspace, base_sha, path))
        after = _test_profile(gitops.show(workspace, "HEAD", path))
        if "<syntax-error>" in after:
            problems.append(f"{path}: syntax error")
        for name, old in before.items():
            new = after.get(name)
            if new is None:
                problems.append(f"{path}::{name} was deleted")
                continue
            if new["asserts"] < old["asserts"]:
                problems.append(f"{path}::{name} assertions reduced "
                                f"{old['asserts']} -> {new['asserts']}")
            for marker in new["markers"] - old["markers"]:
                problems.append(f"{path}::{name} gained @{marker}")
            if "xfail" in old["markers"] - new["markers"] and \
                    outcomes.get(f"{path}::{name}") != "passed":
                problems.append(f"{path}::{name} xfail removed but test does not pass")
        for name, new in after.items():
            if name not in before and new["markers"]:
                problems.append(f"{path}::{name} new test is marked {sorted(new['markers'])}")
    summary = "clean" if not problems else f"{len(problems)} violation(s)"
    return Check("integrity", not problems, summary, "\n".join(problems) or "no violations")


# --- the gate ---------------------------------------------------------------------------

def verification_gate(workspace: Path, base_sha: str, junit: Path) -> GateResult:
    pytest_check, counts, outcomes = run_pytest(workspace, junit)
    checks = [pytest_check, run_ruff(workspace), run_contract(workspace),
              check_integrity(workspace, base_sha, outcomes)]
    return GateResult(all(c.ok for c in checks), checks, counts)


def render(result: GateResult, header: str) -> str:
    """Raw evidence for 07-verification.txt (tool output, before any review)."""
    parts = [header, ""]
    for c in result.checks:
        parts += [f"## {c.name}: {'PASS' if c.ok else 'FAIL'} ({c.summary})", c.output.rstrip(),
                  ""]
    parts.append(f"RESULT: {'PASS' if result.passed else 'FAIL'}")
    return "\n".join(parts) + "\n"
