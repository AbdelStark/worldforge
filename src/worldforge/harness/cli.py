"""Command-line entry point for TheWorldHarness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from worldforge.framework import WorldForge
from worldforge.harness.connectors import (
    provider_connector_summaries,
    provider_connector_summary_markdown,
)
from worldforge.harness.flows import available_flows, flow_to_dicts


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worldforge-harness",
        description="Launch TheWorldHarness visual E2E integration harness.",
    )
    parser.add_argument(
        "--flow",
        choices=[flow.id for flow in available_flows()] + ["eval", "benchmark"],
        default=None,
        help=(
            "Harness flow or screen to open. When omitted the harness opens on the Home screen; "
            "eval and benchmark open those screens directly."
        ),
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Directory for persisted demo worlds. Defaults to a temporary directory.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available harness flows without launching the TUI.",
    )
    parser.add_argument(
        "--connectors",
        action="store_true",
        help="List provider connector readiness without launching the TUI.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format for --list and --connectors.",
    )
    parser.add_argument(
        "--no-animation",
        action="store_true",
        help="Disable step reveal delays.",
    )
    return parser


def print_flow_index(*, output_format: str = "markdown") -> None:
    """Print available harness flows."""

    if output_format == "json":
        print(json.dumps(flow_to_dicts(), indent=2))
        return

    print("# TheWorldHarness Flows")
    print()
    print("| Flow | Focus | Provider | Command |")
    print("| --- | --- | --- | --- |")
    for flow in available_flows():
        print(f"| `{flow.id}` | {flow.focus} | {flow.provider} | `{flow.command}` |")


def print_connector_index(
    *,
    state_dir: Path | None = None,
    output_format: str = "markdown",
) -> None:
    """Print provider connector readiness metadata."""

    forge = WorldForge(state_dir=state_dir, auto_register_remote=True)
    rows = provider_connector_summaries(forge)
    if output_format == "json":
        print(json.dumps([row.to_dict() for row in rows], indent=2))
        return
    print(provider_connector_summary_markdown(rows))


def launch_harness(
    *,
    flow_id: str | None = None,
    state_dir: Path | None = None,
    animate: bool = True,
) -> int:
    """Launch the Textual harness, returning a process exit code.

    ``flow_id=None`` means the user did not pass ``--flow`` — the harness
    opens on the Home screen. Any explicit flow id pushes the Run Inspector
    screen with that flow pre-selected.
    """

    try:
        from worldforge.harness.tui import TheWorldHarnessApp
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("textual"):
            print(
                "TheWorldHarness requires the optional Textual dependency. "
                "Install with `uv run --extra harness worldforge-harness` "
                "or `pip install 'worldforge-ai[harness]'`.",
                file=sys.stderr,
            )
            return 2
        raise

    if flow_id in {"eval", "benchmark"}:
        initial_screen = flow_id
        resolved_flow_id = "leworldmodel"
    else:
        initial_screen = "run-inspector" if flow_id is not None else "home"
        resolved_flow_id = flow_id if flow_id is not None else "leworldmodel"
    app = TheWorldHarnessApp(
        initial_flow_id=resolved_flow_id,
        initial_screen=initial_screen,
        state_dir=state_dir,
        step_delay=0.0 if not animate else 0.18,
    )
    app.run()
    return 0


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


def run_from_args(
    *,
    flow_id: str | None,
    state_dir: Path | None,
    list_only: bool,
    connectors: bool,
    output_format: str,
    animate: bool,
) -> int:
    """Run harness behavior from an already-parsed command namespace."""

    if list_only:
        print_flow_index(output_format=output_format)
        return 0
    if connectors:
        print_connector_index(state_dir=state_dir, output_format=output_format)
        return 0
    return launch_harness(flow_id=flow_id, state_dir=state_dir, animate=animate)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return run_from_args(
        flow_id=args.flow,
        state_dir=args.state_dir,
        list_only=args.list,
        connectors=args.connectors,
        output_format=args.format,
        animate=not args.no_animation,
    )


if __name__ == "__main__":
    raise SystemExit(main())
