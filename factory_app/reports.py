"""Parse agent reports: line 1 `VERDICT: X`, then one fenced ```json block.

Anything that does not parse becomes INSUFFICIENT_EVIDENCE -- never success.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
_VERDICT = re.compile(r"^\**\s*VERDICT\s*:\s*\**\s*([A-Z_]+)\b")
_JSON_BLOCK = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


@dataclass
class Report:
    verdict: str
    data: dict = field(default_factory=dict)
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict != INSUFFICIENT


def parse_report(text: str, allowed: tuple[str, ...]) -> Report:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return Report(INSUFFICIENT, error="empty report")
    match = _VERDICT.match(lines[0])
    if not match:
        return Report(INSUFFICIENT, error="first line is not 'VERDICT: <value>'")
    verdict = match.group(1)
    if verdict not in allowed:
        return Report(INSUFFICIENT, error=f"verdict {verdict!r} not in {allowed}")
    block = _JSON_BLOCK.search(text)
    if not block:
        return Report(INSUFFICIENT, error="missing ```json block")
    try:
        data = json.loads(block.group(1))
    except json.JSONDecodeError as exc:
        return Report(INSUFFICIENT, error=f"invalid JSON: {exc}")
    if not isinstance(data, dict):
        return Report(INSUFFICIENT, error="JSON block must be an object")
    return Report(verdict, data)
