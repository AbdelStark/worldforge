#!/usr/bin/env python3
"""Regenerate ``tests/fixtures/public_api/exports.json`` from the live package.

Run this script in the same commit as an intentional public-API change:

```bash
uv run python scripts/update_public_api_snapshot.py
```

The snapshot test (``tests/test_public_api_snapshot.py``) will fail otherwise.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

MODULES: tuple[str, ...] = (
    "worldforge",
    "worldforge.testing",
    "worldforge.observability",
    "worldforge.providers",
    "worldforge.capabilities",
)

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "public_api" / "exports.json"
)


def _module_exports(name: str) -> list[str]:
    module = importlib.import_module(name)
    raw = getattr(module, "__all__", None)
    if raw is not None:
        return sorted({str(item) for item in raw})
    return sorted(item for item in dir(module) if not item.startswith("_"))


def main() -> int:
    snapshot = {
        "schema_version": 1,
        "modules": {name: _module_exports(name) for name in MODULES},
    }
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if SNAPSHOT_PATH.is_relative_to(Path.cwd()):
        relative = SNAPSHOT_PATH.relative_to(Path.cwd())
    else:
        relative = SNAPSHOT_PATH
    print(f"Wrote public-API snapshot to {relative} ({len(snapshot['modules'])} modules).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
