"""Reject raw hex color literals from Textual widget CSS."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TUI_PATH = ROOT / "src" / "worldforge" / "harness" / "tui.py"
HEX_PATTERN = re.compile(r"#[0-9a-fA-F]{3,8}")


def find_violations() -> list[str]:
    violations: list[str] = []
    for line_number, line in enumerate(TUI_PATH.read_text(encoding="utf-8").splitlines(), start=1):
        matches = HEX_PATTERN.findall(line)
        if matches:
            violations.append(f"{TUI_PATH.relative_to(ROOT)}:{line_number}: {', '.join(matches)}")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Hex color literals are not allowed in widget CSS:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
