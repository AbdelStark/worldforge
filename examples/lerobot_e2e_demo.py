"""Compatibility wrapper for the packaged LeRobot provider-surface demo."""

from __future__ import annotations

from worldforge.demos.lerobot_e2e import main, run_demo

__all__ = ["main", "run_demo"]


if __name__ == "__main__":
    raise SystemExit(main())
