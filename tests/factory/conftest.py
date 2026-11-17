"""Shared fixtures: an isolated runs/ directory and a ScriptedRunner (no LLM)."""

import pytest

from factory_app.orchestrator import Orchestrator, ScriptedRunner


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    path = tmp_path / "runs"
    path.mkdir()
    monkeypatch.setattr("factory_app.orchestrator.RUNS_DIR", path)
    return path


@pytest.fixture
def make_orch(runs_dir):
    def _make(cr: str, **replies: list[str]) -> Orchestrator:
        return Orchestrator(cr, runner=ScriptedRunner(replies), runs_dir=runs_dir)

    return _make
