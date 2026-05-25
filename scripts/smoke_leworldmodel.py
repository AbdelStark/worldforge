#!/usr/bin/env python3
"""Compatibility wrapper for the packaged real LeWorldModel checkpoint smoke."""

from __future__ import annotations

from worldforge.smoke.leworldmodel import DEFAULT_STABLEWM_HOME, _parser, main

__all__ = ["DEFAULT_STABLEWM_HOME", "_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
