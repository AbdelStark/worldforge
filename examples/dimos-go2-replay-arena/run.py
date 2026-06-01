"""Run the checkout-safe DimOS Go2 replay decision arena."""

from __future__ import annotations

import argparse
from pathlib import Path

from worldforge.demos.dimos_go2_replay_arena import (
    DEFAULT_FIXTURE_PATH,
    run_dimos_go2_replay_arena_workflow,
    run_dimos_go2_replay_batch,
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
    parser.add_argument(
        "--all-fixtures",
        action="store_true",
        help="Run every bundled replay fixture and emit a batch report.",
    )
    args = parser.parse_args()
    if args.all_fixtures:
        fixtures = sorted(DEFAULT_FIXTURE_PATH.parent.glob("*.json"))
        summary = run_dimos_go2_replay_batch(fixtures, args.out)
        print(f"fixture_count={summary['fixture_count']}")
        for row in summary["rows"]:
            print(
                f"{row['scenario_id']}: selected={row['selected_action_id']} "
                f"baseline={row['baseline_action_id']} "
                f"score_margin={row['score_margin']:.6f} "
                f"baseline_regret={row['baseline_regret']:.6f}"
            )
        print(f"batch_report={summary['batch_report_path']}")
        print(f"batch_markdown={summary['batch_markdown_path']}")
        return

    summary = run_dimos_go2_replay_arena_workflow(args.fixture, args.out)
    print(f"selected_action={summary['selected_action_id']}")
    print(f"score_margin={summary['score_margin']:.6f}")
    print(f"baseline_regret={summary['baseline_regret']:.6f}")
    print(f"trace={summary['decision_trace_path']}")
    print(f"report={summary['report_path']}")


if __name__ == "__main__":
    main()
