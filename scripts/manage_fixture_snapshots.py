"""Manage fixture snapshot manifests for source-controlled JSON fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from worldforge.testing import (  # noqa: E402
    build_fixture_snapshot_manifest,
    default_fixture_snapshot_paths,
    load_fixture_snapshot_manifest,
    validate_fixture_snapshot_manifest,
)

DEFAULT_MANIFEST = ROOT / "tests" / "fixtures" / "fixture-snapshots.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Fixture snapshot manifest path.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root for resolving manifest entries.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Rewrite the manifest from the default fixture path set.",
    )
    parser.add_argument(
        "--allow-intended-updates",
        action="store_true",
        help="Treat changed entries marked review_status=intended-update as review-passing.",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Review output format for check mode.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    manifest_path = args.manifest.resolve()
    if args.write:
        manifest = build_fixture_snapshot_manifest(
            default_fixture_snapshot_paths(root),
            root=root,
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        try:
            display_path = manifest_path.relative_to(root)
        except ValueError:
            display_path = manifest_path
        print(f"Wrote {display_path} with {len(manifest.entries)} entries.")
        return 0

    manifest = load_fixture_snapshot_manifest(manifest_path)
    report = validate_fixture_snapshot_manifest(
        manifest,
        root=root,
        allow_intended_updates=args.allow_intended_updates,
    )
    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(report.to_markdown())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
