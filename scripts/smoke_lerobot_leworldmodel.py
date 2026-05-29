#!/usr/bin/env python3
"""Compatibility wrapper for the packaged LeRobot + LeWorldModel smoke."""

from __future__ import annotations

from worldforge.smoke.lerobot_leworldmodel import (
    DEFAULT_LEROBOT_POLICY,
    DEFAULT_LEWORLDMODEL_POLICY,
    _parser,
    main,
)

__all__ = ["DEFAULT_LEROBOT_POLICY", "DEFAULT_LEWORLDMODEL_POLICY", "_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
