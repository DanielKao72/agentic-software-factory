"""Standard validation (AGENTS.md): python scripts/verify_repo.py

  (default)     repo contract + pytest + ruff
  --contract    repo contract only (used by the factory's verification gate)
  --root PATH   check another checkout, e.g. a factory worktree
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "AGENTS.md", "docs/REQUIREMENTS.md", "docs/SPEC.md", "docs/ARCHITECTURE.md",
    "docs/REPO_MAP.md", "campusflow/service.py", "campusflow/repository.py",
    "campusflow/api.py",
]
FACTORY_IMPORT = re.compile(r"^\s*(from|import)\s+(factory_app|scripts)\b", re.MULTILINE)


def contract_problems(root: Path) -> list[str]:
    problems = [f"missing required file: {p}" for p in REQUIRED if not (root / p).is_file()]
    for py in sorted((root / "campusflow").rglob("*.py")):
        if FACTORY_IMPORT.search(py.read_text(encoding="utf-8")):
            problems.append(f"product code imports factory code: {py.relative_to(root)}")
    tracked = subprocess.run(["git", "ls-files", ".env"], cwd=root, text=True,
                             capture_output=True, check=False).stdout.strip()
    if tracked:
        problems.append(".env is tracked by git")
    if ".env" not in (root / ".gitignore").read_text(encoding="utf-8").split():
        problems.append(".env is not gitignored")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", action="store_true", help="repo contract only")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.root.resolve()

    problems = contract_problems(root)
    for problem in problems:
        print(f"CONTRACT: {problem}")
    failed = bool(problems)
    print(f"REPO_CONTRACT: {'FAIL' if problems else 'PASS'}")

    if not args.contract:
        for command in (
            [sys.executable, "-m", "pytest", "-q"],
            [sys.executable, "-m", "ruff", "check", "campusflow", "tests", "factory_app",
             "scripts"],
        ):
            print(f"\n$ {' '.join(command)}")
            failed = subprocess.run(command, cwd=root, check=False).returncode != 0 or failed
    print("\nVERIFY_REPO:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
