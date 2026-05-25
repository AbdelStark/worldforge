"""Generate candidate benchmark budgets from preserved benchmark JSON reports."""

from __future__ import annotations

import argparse
import shutil
import sys
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from worldforge.benchmark_calibration import calibrate_benchmark_budgets  # noqa: E402


def _default_output() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / ".worldforge" / "benchmark-calibration" / timestamp


def _display(path: Path) -> Path:
    with suppress(ValueError):
        return path.relative_to(ROOT)
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        action="append",
        required=True,
        help="Preserved benchmark JSON report to calibrate from. Can be repeated.",
    )
    parser.add_argument(
        "--current-budget",
        type=Path,
        default=None,
        help="Current budget JSON file to diff against. It is read only and never modified.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory. Defaults to .worldforge/benchmark-calibration/<timestamp>.",
    )
    parser.add_argument(
        "--headroom-ratio",
        type=float,
        default=0.25,
        help="Relative headroom for latency and throughput thresholds. Defaults to 0.25.",
    )
    parser.add_argument(
        "--machine-class",
        default=None,
        help=(
            "Machine class label to record in baseline context. Defaults to "
            "WORLDFORGE_MACHINE_CLASS or 'unknown'."
        ),
    )
    parser.add_argument(
        "--rationale",
        default="review required before applying candidate budget",
        help="Rationale copied into each threshold diff row.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = args.output or _default_output()
    if output.exists():
        if not args.overwrite:
            parser = _parser()
            parser.error(f"output directory already exists: {output}")
        shutil.rmtree(output)

    result = calibrate_benchmark_budgets(
        tuple(args.report),
        current_budget_path=args.current_budget,
        output_dir=output,
        headroom_ratio=args.headroom_ratio,
        machine_class=args.machine_class,
        rationale=args.rationale,
    )
    assert result.output_dir is not None
    assert result.calibration_path is not None
    assert result.candidate_budget_path is not None
    assert result.markdown_path is not None
    print(f"wrote {_display(result.output_dir)}")
    print(f"calibration: {_display(result.calibration_path)}")
    print(f"candidate budgets: {_display(result.candidate_budget_path)}")
    print(f"review report: {_display(result.markdown_path)}")
    print("review required before replacing any release budget file")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
