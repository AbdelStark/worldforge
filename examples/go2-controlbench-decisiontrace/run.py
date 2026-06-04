"""Compatibility wrapper for the Go2 Air ControlBench DecisionTrace demo."""

from __future__ import annotations

from worldforge.demos.go2_controlbench_decisiontrace import (
    main,
    run_demo,
    run_go2_controlbench_decisiontrace,
)

__all__ = ["main", "run_demo", "run_go2_controlbench_decisiontrace"]


if __name__ == "__main__":
    raise SystemExit(main())
