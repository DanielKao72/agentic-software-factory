"""Contracts, prompts and agents must agree (contract = source of truth)."""

import pytest

from factory_app import config
from factory_app.permissions import MATRIX
from factory_app.prompts import AGENTS, CONTRACT_KEYS, VERDICTS, instruction_for, load_contract

# Contract tool name -> permission action it requires.
TOOL_ACTION = {
    "read_repo_file": "read", "list_repo_files": "read", "search_repo": "search",
    "git_diff": "git_diff", "write_file": None, "run_verification": "exec_verify",
    "run_security_scans": "exec_scan", "git_commit": "git_commit",
    "write_run_evidence": "write_evidence",
}
BUILDABLE_NOW = ("intake", "planner")  # later milestones add their tools


@pytest.mark.parametrize("agent", AGENTS)
def test_contract_has_exactly_the_required_keys(agent):
    assert tuple(load_contract(agent)) == CONTRACT_KEYS


@pytest.mark.parametrize("agent", AGENTS)
def test_contract_model_comes_from_config(agent):
    symbol = load_contract(agent)["model"]
    assert getattr(config, symbol) == config.AGENT_MODELS[agent]


@pytest.mark.parametrize("agent", AGENTS)
def test_allowed_tools_match_permission_matrix(agent):
    contract = load_contract(agent)
    assert not set(contract["allow"]) & set(contract["deny"])
    for tool in contract["allow"]:
        action = TOOL_ACTION[tool]
        if action:
            assert action in MATRIX[agent], f"{agent} allows {tool} but lacks {action}"
    assert "merge" in contract["deny"]


@pytest.mark.parametrize("agent", AGENTS)
def test_prompt_is_generated_from_contract(agent):
    contract, text = load_contract(agent), instruction_for(agent)
    assert contract["role"] in text and contract["output"] in text
    for item in [*contract["allow"], *contract["deny"], *contract["stop_conditions"]]:
        assert item in text
    assert "VERDICT: <" + " | ".join(VERDICTS[agent]) + ">" in text
    assert "<untrusted_data>" in text


@pytest.mark.parametrize("agent", BUILDABLE_NOW)
def test_built_agent_gets_only_contract_tools(agent):
    from factory_app.agents import build_agent

    built = build_agent(agent)
    assert [t.__name__ for t in built.tools] == load_contract(agent)["allow"]
    assert built.model == config.AGENT_MODELS[agent]


def test_reviewer_and_security_cannot_read_coder_or_each_other():
    for agent, forbidden in (("reviewer", ("05-", "06-", "09-")),
                             ("security", ("05-", "06-", "08-"))):
        context = " ".join(load_contract(agent)["context"])
        for prefix in forbidden:
            assert prefix not in context, f"{agent} contract exposes {prefix}*"
