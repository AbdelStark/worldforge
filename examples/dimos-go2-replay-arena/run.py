"""Run the checkout-safe DimOS Go2 replay decision arena."""

from __future__ import annotations

import argparse
from pathlib import Path

from worldforge.demos.dimos_go2_replay_arena import (
    DEFAULT_FIXTURE_PATH,
    run_dimos_go2_replay_arena_workflow,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
        help="Replay fixture JSON path.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(".worldforge/dimos-go2-replay-arena"),
        help="Directory for decision trace and report artifacts.",
    )
    args = parser.parse_args()
    summary = run_dimos_go2_replay_arena_workflow(args.fixture, args.out)
    print(f"selected_action={summary['selected_action_id']}")
    print(f"score_margin={summary['score_margin']:.6f}")
    print(f"baseline_regret={summary['baseline_regret']:.6f}")
    print(f"trace={summary['decision_trace_path']}")
    print(f"report={summary['report_path']}")


if __name__ == "__main__":
    main()
