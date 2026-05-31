"""Compatibility wrapper for the packaged SO-101 replay trace demo."""

from __future__ import annotations

from worldforge.demos.so101_replay_trace import main, run_demo

__all__ = ["main", "run_demo"]


if __name__ == "__main__":
    raise SystemExit(main())
