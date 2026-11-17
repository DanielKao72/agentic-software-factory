"""Create a run folder only (copy CR, initial factory-state.json) without calling any agent.

Use `scripts/factory.py start CR-001` to create AND run Intake -> Planner.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from factory_app.orchestrator import GateError, Orchestrator  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/start_run.py CR-001")
    try:
        state = Orchestrator(sys.argv[1]).create_run()
    except GateError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Created runs/{state['change_id']} ({state['status']}); "
          f"continue with: factory resume {state['change_id']}")


if __name__ == "__main__":
    main()
