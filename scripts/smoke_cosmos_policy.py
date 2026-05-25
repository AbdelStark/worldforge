#!/usr/bin/env python
"""Compatibility wrapper for ``uv run worldforge-smoke-cosmos-policy``."""

from __future__ import annotations

from worldforge.smoke.cosmos_policy import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
