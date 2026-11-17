"""Least-privilege permission matrix, enforced by every tool (not by prompts).

| Agent        | read | search | edit src | edit tests | exec            | merge |
|--------------|------|--------|----------|------------|-----------------|-------|
| intake       |  ✓   |   ✓    |    –     |     –      |       –         |   –   |
| planner      |  ✓   |   ✓    |    –     |     –      |       –         |   –   |
| coder        |  ✓   |   ✓    |    ✓     |     ✓      | verify allowlist|   –   |
| test_analyst |  ✓   |   ✓    |    –     |     ✓      | verify allowlist|   –   |
| reviewer     |  ✓   |   ✓    |    –     |     –      |       –         |   –   |
| security     |  ✓   |   ✓    |    –     |     –      | scanners only   |   –   |
| evidence     |  ✓   |   –    |    –     |     –      |       –         |   –   |

Nobody can merge or push: no such action exists anywhere in the factory.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import PurePosixPath

ACTIONS = {
    "read", "search", "write_src", "write_tests", "exec_verify", "exec_scan",
    "git_diff", "git_commit", "write_evidence",
}

MATRIX: dict[str, set[str]] = {
    "intake": {"read", "search"},
    "planner": {"read", "search"},
    "coder": {"read", "search", "write_src", "write_tests", "exec_verify", "git_commit"},
    "test_analyst": {"read", "search", "write_tests", "exec_verify"},
    "reviewer": {"read", "search", "git_diff"},
    "security": {"read", "search", "git_diff", "exec_scan"},
    "evidence": {"read", "write_evidence"},
}

READ_ROOTS = ("docs", "change_requests", "campusflow", "tests", "runs")
# No agent may ever write these, whatever the plan says.
PROTECTED = (
    "docs/", "change_requests/", "factory_app/", "scripts/", ".github/", "runs/",
    "AGENTS.md", "GEMINI.md", "README.md", "pyproject.toml", "uv.lock", ".env",
)

# ADK agent names -> contract names.
ADK_NAMES = {
    "IntakeAgent": "intake", "PlannerAgent": "planner", "CoderAgent": "coder",
    "TestAnalystAgent": "test_analyst", "ReviewerAgent": "reviewer",
    "SecurityAgent": "security", "EvidenceAgent": "evidence",
}


class PermissionDenied(PermissionError):
    pass


def normalize(rel_path: str) -> str:
    """Repo-relative POSIX path; rejects absolute paths and '..' escapes."""
    raw = rel_path.replace("\\", "/").strip()
    path = PurePosixPath(raw)
    if not raw or path.is_absolute() or ":" in raw or ".." in path.parts:
        raise PermissionDenied(f"path not allowed: {rel_path!r}")
    return "" if str(path) == "." else str(path)  # PurePosixPath already drops "./"


def require(agent: str, action: str) -> None:
    if action not in ACTIONS:
        raise PermissionDenied(f"unknown action {action!r}")
    if action not in MATRIX.get(agent, set()):
        raise PermissionDenied(f"{agent} is not allowed to {action}")


def check_read(agent: str, rel_path: str, run_files: list[str] | None = None) -> str:
    """Reads are limited to READ_ROOTS; under runs/ only the agent's contract files.

    `run_files` are the runs/<CR>/... paths listed in the agent's contract context.
    This is what keeps Reviewer/Security from reading the Coder's report.
    """
    require(agent, "read")
    rel = normalize(rel_path)
    top = rel.split("/", 1)[0]
    if top not in READ_ROOTS:
        raise PermissionDenied(f"read not allowed under {top!r}")
    if top == "runs" and not any(fnmatch(rel, pattern) for pattern in run_files or []):
        raise PermissionDenied(f"{agent} may not read run artifact {rel!r}")
    return rel


def check_write(agent: str, rel_path: str, plan_files: list[str] | None) -> str:
    """Writes: tests/ (coder, test_analyst) and campusflow/ (coder only),
    and for the Coder only files listed in the human-approved plan."""
    rel = normalize(rel_path)
    if any(rel == p.rstrip("/") or rel.startswith(p) for p in PROTECTED if p.endswith("/")) or (
        rel in PROTECTED
    ):
        raise PermissionDenied(f"{rel!r} is protected; no agent may write it")
    if rel.startswith("tests/"):
        require(agent, "write_tests")
    elif rel.startswith("campusflow/"):
        require(agent, "write_src")
    else:
        raise PermissionDenied(f"writes allowed only under campusflow/ or tests/, not {rel!r}")
    if agent == "coder" and rel not in set(plan_files or []):
        raise PermissionDenied(f"{rel!r} is not in the approved plan's files_to_touch")
    return rel
