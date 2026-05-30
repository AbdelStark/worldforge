#!/usr/bin/env python3
"""Generate a WorldForge provider scaffold."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main(argv: list[str] | None = None) -> int:
    from worldforge.provider_scaffold import main as scaffold_main

    return scaffold_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
