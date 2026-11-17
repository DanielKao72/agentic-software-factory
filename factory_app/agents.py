"""Builds each ADK agent from its contract: model, instruction and ONLY the allowed tools."""

from __future__ import annotations

from google.adk.agents.llm_agent import LlmAgent

from . import config
from .prompts import AGENTS, instruction_for, load_contract
from .tools import TOOL_REGISTRY

ADK_NAME = {
    "intake": "IntakeAgent", "planner": "PlannerAgent", "coder": "CoderAgent",
    "test_analyst": "TestAnalystAgent", "reviewer": "ReviewerAgent",
    "security": "SecurityAgent", "evidence": "EvidenceAgent",
}


def model_for(agent: str) -> str:
    """Contract names a config symbol (FLASH_MODEL / LITE_MODEL); config holds the ID."""
    return getattr(config, load_contract(agent)["model"])


def build_agent(agent: str) -> LlmAgent:
    contract = load_contract(agent)
    missing = [t for t in contract["allow"] if t not in TOOL_REGISTRY]
    if missing:
        raise NotImplementedError(f"{agent}: tools not implemented yet: {missing}")
    text = instruction_for(agent)
    return LlmAgent(
        name=ADK_NAME[agent],
        model=model_for(agent),
        description=contract["role"],
        # A callable instruction is used verbatim (no {state} templating of JSON braces).
        instruction=lambda _ctx, _text=text: _text,
        tools=[TOOL_REGISTRY[t] for t in contract["allow"]],
        output_key=f"{agent}_report",
    )


__all__ = ["AGENTS", "ADK_NAME", "build_agent", "model_for"]
