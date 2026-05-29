"""Reject network-egress calls from TheWorldHarness code."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS_DIR = ROOT / "src" / "worldforge" / "harness"
PATTERNS = (
    re.compile(r"\bhttpx\.(post|put|patch|delete)\b"),
    re.compile(r"\brequests\.(post|put|patch|delete)\b"),
    re.compile(r"\bsocket\.send(?:all)?\b"),
)


def find_violations() -> list[str]:
    violations: list[str] = []
    for path in sorted(HARNESS_DIR.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in PATTERNS):
                violations.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Network egress is not allowed in TheWorldHarness:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
