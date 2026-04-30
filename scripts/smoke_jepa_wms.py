#!/usr/bin/env python3
"""Compatibility wrapper for the packaged JEPA-WMS prepared-host smoke."""

from __future__ import annotations

from worldforge.smoke.jepa_wms import _parser, main

__all__ = ["_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
