"""Canned agent replies for ScriptedRunner (deterministic tests and evals)."""

import json


def reply(verdict: str, data: dict, body: str = "Human-readable report.") -> str:
    return f"VERDICT: {verdict}\n```json\n{json.dumps(data)}\n```\n{body}\n"


INTAKE_PROCEED = reply("PROCEED", {"requirements": ["FR-03", "AC-03.3"], "questions": [],
                                   "likely_areas": ["campusflow/service.py"]})
INTAKE_CLARIFY = reply("HUMAN_CLARIFICATION_REQUIRED", {
    "requirements": ["FR-03"], "ambiguities": ["who is priority", "what is popular"],
    "questions": ["Which users receive priority?", "What makes an event popular?"]})
PLAN_READY = reply("PLAN_READY", {
    "tasks": [{"id": "TASK-01", "description": "reject duplicates in Service",
               "requirements": ["AC-CR003.2"], "files": ["campusflow/service.py"],
               "tests": ["tests/product/test_known_gaps.py"]}],
    "files_to_touch": ["campusflow/service.py", "campusflow/errors.py",
                       "tests/product/test_known_gaps.py"],
    "open_questions": []})
PLAN_TOUCHING_DOCS = reply("PLAN_READY", {
    "tasks": [{"id": "TASK-01", "description": "relax the requirement"}],
    "files_to_touch": ["docs/REQUIREMENTS.md"]})
