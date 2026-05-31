"""Launch helpers for the robotics showcase Textual report."""

from __future__ import annotations

import sys
from pathlib import Path


def launch_robotics_showcase_report(
    *,
    summary: dict[str, object],
    summary_path: Path | None = None,
    stage_delay: float = 0.35,
    animate_arm: bool = True,
) -> int:
    """Launch the Textual robotics showcase report for a completed real run."""

    try:
        from worldforge.harness.tui import RoboticsShowcaseApp
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("textual"):
            print(
                "The robotics showcase TUI requires the optional Textual dependency. "
                "Run `scripts/robotics-showcase`, `uv run --extra harness ...`, "
                "or pass `--no-tui` for the plain terminal report.",
                file=sys.stderr,
            )
            return 2
        raise

    app = RoboticsShowcaseApp(
        summary=summary,
        summary_path=summary_path,
        stage_delay=stage_delay,
        animate_arm=animate_arm,
    )
    app.run()
    return 0
