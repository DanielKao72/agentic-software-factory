"""Factory CLI. Every human gate is a command; nothing continues past a WAITING_* status
without one.

  factory start   CR-001
  factory clarify CR-005 "<policy>" --by "<name / Product Owner>" [--decision MODIFIED]
  factory approve CR-001 plan APPROVED "<reason>" --by "<name / Tech Lead>"
  factory decide  CR-001 RF-01 ACCEPTED "<reason>" --by "<name / Human Reviewer>"   (M3)
  factory release CR-001 READY "<reason>" --by "<name / Release Manager>"          (M4)
  factory resume  CR-001
  factory status  CR-001
  factory rework  CR-001 "<note>" --by "<name / role>"

Run as: uv run python scripts/factory.py <command> ...
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from factory_app.llm import RateLimitExhausted  # noqa: E402
from factory_app.orchestrator import GateError, Orchestrator, next_action  # noqa: E402
from factory_app.state import IllegalTransition  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="factory", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    for name in ("start", "resume"):
        sub.add_parser(name).add_argument("cr")
    s = sub.add_parser("status")
    s.add_argument("cr")
    s.add_argument("--json", action="store_true", help="print the full factory-state.json")

    c = sub.add_parser("clarify", help="Gate 0: Product Owner policy for an ambiguous CR")
    c.add_argument("cr")
    c.add_argument("text")
    c.add_argument("--by", required=True)
    c.add_argument("--decision", default="APPROVED", choices=["APPROVED", "MODIFIED", "REJECTED"])

    a = sub.add_parser("approve", help="Gate 1: plan decision")
    a.add_argument("cr")
    a.add_argument("gate", choices=["plan"])
    a.add_argument("decision", choices=["APPROVED", "MODIFIED", "REJECTED"])
    a.add_argument("reason")
    a.add_argument("--by", required=True)

    d = sub.add_parser("decide", help="Gate 2: decision on one review/security finding")
    d.add_argument("cr")
    d.add_argument("finding")
    d.add_argument("decision", choices=["ACCEPTED", "REJECTED", "MODIFIED", "DEFERRED"])
    d.add_argument("reason")
    d.add_argument("--by", required=True)

    r = sub.add_parser("release", help="Gate 3: release decision")
    r.add_argument("cr")
    r.add_argument("decision", choices=["READY", "NOT_READY"])
    r.add_argument("reason")
    r.add_argument("--by", required=True)

    w = sub.add_parser("rework", help="send the job back after an escalation")
    w.add_argument("cr")
    w.add_argument("note")
    w.add_argument("--by", required=True)
    return p


def print_summary(st: dict) -> None:
    print(f"RUN:     {st['change_id']}  (branch {st['branch']})")
    print(f"STATUS:  {st['status']}")
    if st.get("status_reason"):
        print(f"REASON:  {st['status_reason']}")
    gates = ", ".join(f"{k}={v}" for k, v in st["human_gates"].items())
    print(f"GATES:   {gates}")
    m = st["metrics"]
    print(f"METRICS: llm_calls={m['llm_calls']} rate_limit_retries={m['rate_limit_retries']} "
          f"overload_retries={m.get('overload_retries', 0)} "
          f"human_interventions={m['human_interventions']}")
    print(f"NEXT:    {next_action(st)}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # ADK logs every failed model attempt with a full stack trace; our wrapper already
    # records each retry in runs/<CR>/run-log.jsonl, so keep the console readable.
    logging.getLogger("google_adk").setLevel(logging.CRITICAL)
    try:
        orch = Orchestrator(args.cr)
        if args.command == "start":
            st = orch.start()
        elif args.command == "resume":
            st = orch.resume()
        elif args.command == "status":
            orch._require_run()
            st = orch.state
            if args.json:
                print(json.dumps(st, indent=2))
                return 0
        elif args.command == "clarify":
            st = orch.clarify(args.text, args.by, args.decision)
        elif args.command == "approve":
            st = orch.approve_plan(args.decision, args.reason, args.by)
        elif args.command == "rework":
            st = orch.rework(args.note, args.by)
        else:  # decide / release arrive with M3 / M4
            raise GateError(f"'{args.command}' is not available yet in this milestone")
    except RateLimitExhausted as exc:
        print(f"PAUSED: {exc}. State is checkpointed; continue with: "
              f"factory resume {args.cr.upper()}", file=sys.stderr)
        return 75
    except (GateError, IllegalTransition, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print_summary(st)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
