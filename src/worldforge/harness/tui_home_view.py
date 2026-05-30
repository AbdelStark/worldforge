"""Textual-free Home-screen view helpers for TheWorldHarness."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from worldforge.harness.tui_app_view import AppScreenName

HOME_NO_RECENT_MESSAGE = (
    "No recent worlds or runs — press [b]n[/] to create a world or [b]e[/] to run an eval."
)


class SupportsRunId(Protocol):
    run_id: str


@dataclass(frozen=True, slots=True)
class HomeJumpSpec:
    target: AppScreenName
    title: str
    binding: str
    description: str
    widget_id: str


@dataclass(frozen=True, slots=True)
class HomeBindingSpec:
    key: str
    action: str
    description: str
    show: bool = True


@dataclass(frozen=True, slots=True)
class HomeTextSpec:
    widget_id: str
    text: str

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(frozen=True, slots=True)
class HomeScreenSpec:
    root_id: str
    intro: HomeTextSpec
    cards_id: str
    recent: HomeTextSpec


HOME_JUMP_SPECS: tuple[HomeJumpSpec, ...] = (
    HomeJumpSpec(
        target="worlds",
        title="Create a world",
        binding="n",
        description="Open the Worlds screen — create, edit, save, fork.",
        widget_id="jump-create-world",
    ),
    HomeJumpSpec(
        target="providers",
        title="Run a provider",
        binding="p",
        description="Stream live provider events with cancellable workers.",
        widget_id="jump-run-provider",
    ),
    HomeJumpSpec(
        target="eval",
        title="Run an eval",
        binding="e",
        description="Execute a deterministic evaluation suite against a provider.",
        widget_id="jump-run-eval",
    ),
    HomeJumpSpec(
        target="runs",
        title="Review runs",
        binding="u",
        description="Filter preserved runs and open recovery actions.",
        widget_id="jump-review-runs",
    ),
)
HOME_JUMP_CARD_BINDING_SPECS: tuple[HomeBindingSpec, ...] = (
    HomeBindingSpec("enter", "activate", "Activate", show=False),
)
HOME_SCREEN_BINDING_SPECS: tuple[HomeBindingSpec, ...] = tuple(
    HomeBindingSpec(spec.binding, f"jump('{spec.target}')", spec.title) for spec in HOME_JUMP_SPECS
)
HOME_INITIAL_FOCUS_WIDGET_ID = HOME_JUMP_SPECS[0].widget_id
HOME_INTRO_MARKUP = (
    "[bold]TheWorldHarness[/] is the visual integration reference for "
    "WorldForge.\n"
    "It runs the same provider, planning, evaluation, and persistence APIs "
    "you would use in a script — wired into a keyboard-first workspace so "
    "you can see every boundary as it executes.\n\n"
    "Pick a jump target below, press [bold]Ctrl+P[/] to search every action, "
    "or [bold]?[/] to see this screen's bindings."
)
HOME_INITIAL_RECENT_TEXT = "No recent items yet — jump targets will appear here once you open them."
HOME_SCREEN_SPEC = HomeScreenSpec(
    root_id="home-root",
    intro=HomeTextSpec("home-intro", HOME_INTRO_MARKUP),
    cards_id="home-cards",
    recent=HomeTextSpec("home-recent", HOME_INITIAL_RECENT_TEXT),
)
HOME_RECENT_SELECTOR = HOME_SCREEN_SPEC.recent.selector


def home_jump_target_screen(target: str) -> AppScreenName | None:
    for spec in HOME_JUMP_SPECS:
        if spec.target == target:
            return spec.target
    return None


def recent_world_ids(
    world_ids: Iterable[str],
    *,
    state_dir: Path,
    limit: int = 5,
) -> list[str]:
    return sorted(
        world_ids,
        key=lambda world_id: _world_state_mtime(state_dir, world_id),
        reverse=True,
    )[:limit]


def home_recent_text(
    *,
    world_ids: Sequence[str],
    report_paths: Sequence[Path],
    run_records: Sequence[SupportsRunId],
) -> str:
    if not world_ids and not report_paths and not run_records:
        return HOME_NO_RECENT_MESSAGE
    lines = ["Recent"]
    lines.append("Worlds: " + ", ".join(world_ids) if world_ids else "Worlds: none yet")
    lines.append(
        "Reports: " + ", ".join(path.name for path in report_paths)
        if report_paths
        else "Reports: none yet"
    )
    lines.append(
        "Runs: " + ", ".join(record.run_id for record in run_records)
        if run_records
        else "Runs: none yet"
    )
    return "\n".join(lines)


def _world_state_mtime(state_dir: Path, world_id: str) -> float:
    path = state_dir / f"{world_id}.json"
    if not path.exists():
        return 0.0
    return path.stat().st_mtime
