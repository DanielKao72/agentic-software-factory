"""Single place for models, limits and environment handling.

Change a model here (or via env var) and every agent, the eval judge and the
wrapper pick it up. The factory only supports the Gemini Developer API
(Google AI Studio key); Vertex / enterprise settings are refused.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env", override=False)

# --- Models -----------------------------------------------------------------
# Verified with models.list on 2026-11-17. The Gemini free tier caps each model at a
# small number of requests per day (gemini-3.8-flash: 20/day), and one full CR run
# needs ~25-40. Each model has its OWN daily quota on the same key, so roles are
# split across Flash models (decision by the project owner, 2026-11-17):
#   independent judgment (Reviewer, Security, eval judge) -> newest Flash
#   requirements/planning                                 -> previous Flash
#   implementation/test analysis                          -> older Flash
#   evidence consolidation                                -> Flash-Lite
# The contracts name these symbols; the IDs live only here.
FLASH_MODEL = os.getenv("FACTORY_MODEL", "gemini-3.8-flash")
PLANNING_MODEL = os.getenv("FACTORY_PLANNING_MODEL", "gemini-3.7-flash")
CODING_MODEL = os.getenv("FACTORY_CODING_MODEL", "gemini-3.5-flash")
LITE_MODEL = os.getenv("FACTORY_LITE_MODEL", "gemini-3.5-flash-lite")
JUDGE_MODEL = FLASH_MODEL  # keep in sync with tests/eval/eval_config.yaml

AGENT_MODELS: dict[str, str] = {
    "intake": PLANNING_MODEL,
    "planner": PLANNING_MODEL,
    "coder": CODING_MODEL,
    "test_analyst": CODING_MODEL,
    "reviewer": FLASH_MODEL,
    "security": FLASH_MODEL,
    "evidence": LITE_MODEL,  # consolidation only
}

# --- Rate-limit wrapper (factory_app/llm.py) --------------------------------
RETRY_MAX_ATTEMPTS = int(os.getenv("FACTORY_RETRY_MAX_ATTEMPTS", "6"))
RETRY_BASE_DELAY_S = float(os.getenv("FACTORY_RETRY_BASE_DELAY_S", "2"))
RETRY_MAX_DELAY_S = float(os.getenv("FACTORY_RETRY_MAX_DELAY_S", "60"))

# --- Loop limits --------------------------------------------------------------
MAX_FIX_ROUNDS = 2  # Gate 2 fix -> reverify -> re-review rounds, then NOT_READY
MAX_VERIFY_ATTEMPTS = 3  # VERIFY_FAILED -> Coder retries before escalating
MAX_AGENT_STEPS = 15  # tool-call cap per agent invocation (free-tier budget)

# --- Git ----------------------------------------------------------------------
BASE_BRANCH = os.getenv("FACTORY_BASE_BRANCH", "main")
BRANCH_PREFIX = "factory/"

_FORBIDDEN_ENV = ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_GENAI_USE_ENTERPRISE")


def ensure_api_key() -> None:
    """Accept GOOGLE_API_KEY (starter) or GEMINI_API_KEY; refuse Vertex/enterprise.

    Never returns or logs the key itself.
    """
    for var in _FORBIDDEN_ENV:
        if os.getenv(var, "").strip().lower() in {"1", "true", "yes"}:
            raise RuntimeError(f"{var} is enabled; the factory only uses the Gemini Developer API")
    if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("Set GOOGLE_API_KEY or GEMINI_API_KEY in .env (Google AI Studio key)")
