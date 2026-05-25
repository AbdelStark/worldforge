#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
state_dir="${WORLDFORGE_HARNESS_SCREENSHOT_STATE:-"$repo_root/.worldforge/screenshot-state/worlds"}"
output="${1:-"$repo_root/docs/assets/img/theworldharness-run-inspector-score-planning.png"}"

if ! command -v rsvg-convert >/dev/null 2>&1; then
  cat >&2 <<EOF
rsvg-convert is required to render Textual's SVG screenshot to PNG.

Install librsvg, then re-run:
  brew install librsvg
  $0 ${1:-}
EOF
  exit 1
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
svg_path="$tmp_dir/theworldharness-run-inspector-score-planning.svg"

mkdir -p "$(dirname "$output")" "$state_dir"

cd "$repo_root"

uv run --extra harness python - "$state_dir" "$svg_path" <<'PY'
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from worldforge import WorldForge
from worldforge.harness.tui import TheWorldHarnessApp


async def main() -> None:
    state_dir = Path(sys.argv[1])
    svg_path = Path(sys.argv[2])

    forge = WorldForge(state_dir=state_dir)
    world = forge.create_world(
        "showcase lab",
        provider="mock",
        description="Deterministic README screenshot state.",
    )
    world.id = "showcase-lab"
    forge.save_world(world)

    app = TheWorldHarnessApp(
        initial_screen="run-inspector",
        state_dir=state_dir,
        step_delay=0.0,
    )
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("r")
        for _ in range(12):
            await pilot.pause()
            if getattr(app.screen, "last_run", None) is not None and not getattr(
                app.screen, "running", False
            ):
                break
        svg_path.write_text(
            app.export_screenshot(title="TheWorldHarness run inspector", simplify=True),
            encoding="utf-8",
        )


asyncio.run(main())
PY

rsvg-convert "$svg_path" -o "$output"

cat <<EOF
TheWorldHarness screenshot refreshed.

State dir:
  $state_dir

Output:
  $output
EOF
