"""Starter gate script, extended: it now goes through the orchestrator, so a decision
is only accepted at the matching WAITING_* status, needs a reason and a name/role,
and is written as numbered evidence (02-/04-...).

  python scripts/approve_gate.py CR-001 plan APPROVED "Plan reviewed" --by "Ana / Tech Lead"
  python scripts/approve_gate.py CR-005 requirements APPROVED "<policy>" --by "Luis / PO"

Equivalent to `scripts/factory.py approve|clarify`; review/release use `factory decide|release`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.factory import main as factory_main  # noqa: E402

VALID_GATES = {"requirements", "plan", "review", "release"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    by = ""
    if "--by" in argv:
        i = argv.index("--by")
        by = " ".join(argv[i + 1:i + 2])
        del argv[i:i + 2]
    if len(argv) < 4 or not by:
        raise SystemExit('Usage: python scripts/approve_gate.py CR-001 plan APPROVED "reason" '
                         '--by "<name / role>"')
    change_id, gate, decision, reason = argv[0], argv[1].lower(), argv[2].upper(), \
        " ".join(argv[3:])
    if gate not in VALID_GATES:
        raise SystemExit(f"Invalid gate: {sorted(VALID_GATES)}")
    if gate == "plan":
        return factory_main(["approve", change_id, "plan", decision, reason, "--by", by])
    if gate == "requirements":
        return factory_main(["clarify", change_id, reason, "--by", by, "--decision", decision])
    raise SystemExit(f"Gate '{gate}': use `factory decide` / `factory release`")


if __name__ == "__main__":
    raise SystemExit(main())
