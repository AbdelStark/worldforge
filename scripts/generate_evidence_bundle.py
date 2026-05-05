"""Generate a safe-to-attach WorldForge evidence bundle from preserved runs."""

from __future__ import annotations

import argparse
import sys
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from worldforge.evidence_bundle import generate_evidence_bundle  # noqa: E402


def _default_output() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return ROOT / ".worldforge" / "evidence-bundles" / timestamp


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-dir",
        type=Path,
        default=ROOT / ".worldforge",
        help="WorldForge workspace directory containing runs/. Defaults to .worldforge.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Bundle output directory. Defaults to .worldforge/evidence-bundles/<timestamp>.",
    )
    parser.add_argument(
        "--run-id",
        action="append",
        default=[],
        help="Run id to include. Can be repeated. Defaults to every run in workspace-dir.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output directory.",
    )
    parser.add_argument(
        "--no-fixture-digests",
        action="store_true",
        help="Omit fixture digest inventory from the evidence manifest.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = generate_evidence_bundle(
        workspace_dir=args.workspace_dir,
        output_dir=args.output or _default_output(),
        run_ids=tuple(args.run_id),
        overwrite=args.overwrite,
        include_fixture_digests=not args.no_fixture_digests,
    )
    display = result.output_dir
    with suppress(ValueError):
        display = display.relative_to(ROOT)
    print(f"wrote {display}")
    print(f"manifest: {result.manifest_path}")
    print(f"summary: {result.summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
