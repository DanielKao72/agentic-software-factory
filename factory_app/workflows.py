"""ADK pipelines for interactive use (`adk web`, `agents-cli eval run`).

The real factory loop is NOT here: it is the deterministic state machine in
factory_app/orchestrator.py, which runs each agent in its own fresh session and
stops at human gates. This pipeline only lets you poke at Intake -> Planner.
"""

from google.adk.agents.sequential_agent import SequentialAgent

from .agents import build_agent

planning_pipeline = SequentialAgent(
    name="PlanningPipeline",
    description="Read-only Intake -> Planning phase (stops before any human gate).",
    sub_agents=[build_agent("intake"), build_agent("planner")],
)
