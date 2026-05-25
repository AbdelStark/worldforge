"""Refresh provider documentation generated from the provider catalog."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PROVIDER_INDEX = ROOT / "docs" / "src" / "providers" / "README.md"
PROVIDER_CONFIG_INDEX = ROOT / "docs" / "src" / "provider-configuration-index.md"
README = ROOT / "README.md"
README_DOCS_LINK_PREFIX = "https://abdelstark.github.io/worldforge/providers/"


@dataclass(frozen=True, slots=True)
class GeneratedBlock:
    path: Path
    start_marker: str
    end_marker: str
    render: Callable[[], str]


def _replace_block(content: str, *, block: GeneratedBlock) -> str:
    start = content.index(block.start_marker)
    end = content.index(block.end_marker, start)
    return (
        content[: start + len(block.start_marker)]
        + "\n"
        + block.render().rstrip()
        + "\n"
        + content[end:]
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if generated provider docs are out of date.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    from worldforge.providers.catalog import (
        render_provider_catalog_markdown,
        render_provider_configuration_index_markdown,
    )

    args = _parser().parse_args(argv)
    blocks = (
        GeneratedBlock(
            path=PROVIDER_INDEX,
            start_marker="<!-- provider-catalog:start -->",
            end_marker="<!-- provider-catalog:end -->",
            render=render_provider_catalog_markdown,
        ),
        GeneratedBlock(
            path=README,
            start_marker="<!-- provider-catalog-readme:start -->",
            end_marker="<!-- provider-catalog-readme:end -->",
            render=lambda: render_provider_catalog_markdown(
                docs_link_prefix=README_DOCS_LINK_PREFIX
            ),
        ),
        GeneratedBlock(
            path=PROVIDER_CONFIG_INDEX,
            start_marker="<!-- provider-config-index:start -->",
            end_marker="<!-- provider-config-index:end -->",
            render=render_provider_configuration_index_markdown,
        ),
    )

    updates: list[tuple[GeneratedBlock, str, str]] = []
    for block in blocks:
        current = block.path.read_text(encoding="utf-8")
        updates.append((block, current, _replace_block(current, block=block)))

    if args.check:
        stale = [
            block.path.relative_to(ROOT)
            for block, current, updated in updates
            if updated != current
        ]
        if stale:
            stale_paths = ", ".join(str(path) for path in stale)
            print(
                f"{stale_paths} out of date; run "
                "`uv run python scripts/generate_provider_docs.py`.",
                file=sys.stderr,
            )
            return 1
        return 0

    changed: list[str] = []
    for block, current, updated in updates:
        if updated != current:
            block.path.write_text(updated, encoding="utf-8")
            changed.append(str(block.path.relative_to(ROOT)))
    if changed:
        print("updated " + ", ".join(changed))
    else:
        print("provider docs already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
