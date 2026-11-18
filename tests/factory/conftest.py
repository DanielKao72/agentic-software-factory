"""Shared fixtures: an isolated runs/ dir, a throwaway git repo holding a copy of
CampusFlow, and a ScriptedRunner (no LLM). Tests never touch the real repository."""

import shutil
import subprocess
from pathlib import Path

import pytest

from factory_app.orchestrator import Orchestrator, ScriptedRunner

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_COPY = ["campusflow", "tests/product", "docs", "AGENTS.md", ".gitignore",
                "pyproject.toml"]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture(scope="session")
def repo_template(tmp_path_factory) -> Path:
    template = tmp_path_factory.mktemp("template") / "repo"
    for rel in PRODUCT_COPY:
        src, dst = ROOT / rel, template / rel
        if src.is_dir():
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return template


@pytest.fixture
def git_repo(tmp_path, repo_template) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(repo_template, repo)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "factory-test")
    _git(repo, "config", "user.email", "factory-test@example.invalid")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "baseline")
    return repo


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Factory tests are deterministic: any attempt to reach Gemini is a test bug."""
    def refuse(*_args, **_kwargs):
        raise AssertionError("factory tests must not call Gemini (use ScriptedRunner)")

    monkeypatch.setattr("factory_app.orchestrator.GeminiRunner.run", refuse)


@pytest.fixture
def runs_dir(tmp_path, monkeypatch, git_repo):
    """Isolated runs/ and, for code that uses defaults (the CLI), a throwaway repo."""
    path = tmp_path / "runs"
    path.mkdir()
    monkeypatch.setattr("factory_app.orchestrator.RUNS_DIR", path)
    monkeypatch.setattr("factory_app.config.REPO_ROOT", git_repo)
    return path


@pytest.fixture
def make_orch(runs_dir, git_repo):
    def _make(cr: str, **replies) -> Orchestrator:
        return Orchestrator(cr, runner=ScriptedRunner(replies), runs_dir=runs_dir,
                            repo_root=git_repo)

    return _make
