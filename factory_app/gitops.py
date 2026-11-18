"""The only git operations the factory can perform. Fixed argv, no shell, and
deliberately NO merge and NO push: a human merges `factory/<CR>` into main.

Each run works in its own worktree (.factory/worktrees/<CR>) on branch
factory/<CR>, so agents never touch the human's checkout or the factory code.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

AGENT_AUTHORS = {  # commits on the feature branch say which agent wrote them
    "coder": ("factory-coder", "factory-coder@factory.invalid"),
    "test_analyst": ("factory-test-analyst", "factory-test-analyst@factory.invalid"),
}


class GitError(RuntimeError):
    pass


def _git(repo: Path, *args: str, env: dict | None = None) -> str:
    import os

    done = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True,
                          timeout=120, check=False, env={**os.environ, **(env or {})})
    if done.returncode != 0:
        raise GitError(f"git {args[0]} failed: {done.stderr.strip()[:500]}")
    return done.stdout


def head(repo: Path, ref: str = "HEAD") -> str:
    return _git(repo, "rev-parse", ref).strip()


def create_worktree(repo: Path, worktree: Path, branch: str, base: str) -> str:
    """Create (or reuse) the run's worktree on `branch` cut from `base`. Returns base sha."""
    base_sha = head(repo, base)
    if worktree.exists():
        return base_sha
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "-b", branch, str(worktree), base_sha)
    return base_sha


def changed_files(worktree: Path, base_sha: str) -> list[str]:
    """Committed changes on the branch since base (renames shown as delete + add)."""
    out = _git(worktree, "diff", "--name-only", "--no-renames", f"{base_sha}...HEAD")
    return [line for line in out.splitlines() if line]


def dirty_files(worktree: Path) -> list[str]:
    out = _git(worktree, "status", "--porcelain", "--untracked-files=all")
    return [line[3:].strip().strip('"') for line in out.splitlines() if line]


def diff(worktree: Path, base_sha: str, max_chars: int = 30_000) -> str:
    text = _git(worktree, "diff", "--no-color", "--no-renames", f"{base_sha}...HEAD")
    return text if len(text) <= max_chars else text[:max_chars] + "\n...[DIFF TRUNCATED]..."


def show(worktree: Path, ref: str, path: str) -> str | None:
    """File content at a commit, or None if it did not exist there."""
    try:
        return _git(worktree, "show", f"{ref}:{path}")
    except GitError:
        return None


def commit(worktree: Path, paths: list[str], message: str, agent: str) -> str:
    """Stage exactly `paths` and commit as the agent. Returns the new sha."""
    if not paths:
        raise GitError("nothing to commit")
    name, email = AGENT_AUTHORS[agent]
    _git(worktree, "add", "--all", "--", *paths)
    _git(worktree, "commit", "--quiet", "-m", message,
         env={"GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email})
    return head(worktree)
