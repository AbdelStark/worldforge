"""Textual-free app and command-palette helpers for TheWorldHarness."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, cast

AppScreenName = Literal[
    "home",
    "run-inspector",
    "worlds",
    "providers",
    "eval",
    "benchmark",
    "runs",
]
SystemCommandAction = Literal[
    "home",
    "run-inspector",
    "worlds",
    "providers",
    "eval",
    "benchmark",
    "runs",
    "new-world",
    "help",
    "theme",
]
PaletteTargetKind = Literal["world", "provider", "report", "run-workspace"]


class SupportsRunWorkspace(Protocol):
    run_id: str
    path: Path


@dataclass(frozen=True, slots=True)
class SystemCommandSpec:
    title: str
    help_text: str
    action: SystemCommandAction


@dataclass(frozen=True, slots=True)
class AppBindingSpec:
    key: str
    action: str
    description: str
    show: bool = True


@dataclass(frozen=True, slots=True)
class AppScreenRouteSpec:
    name: AppScreenName
    system_title: str
    system_help: str
    binding_key: str
    binding_description: str


@dataclass(frozen=True, slots=True)
class PaletteItemSpec:
    title: str
    help_text: str
    kind: PaletteTargetKind
    value: str | Path


APP_SCREEN_ROUTE_SPECS: tuple[AppScreenRouteSpec, ...] = (
    AppScreenRouteSpec("home", "Jump: Home", "Open the Home screen", "g,h", "Jump: Home"),
    AppScreenRouteSpec(
        "run-inspector",
        "Jump: Run Inspector",
        "Open the Run Inspector screen",
        "g,r",
        "Jump: Run Inspector",
    ),
    AppScreenRouteSpec("worlds", "Jump: Worlds", "Open the Worlds screen", "g,w", "Jump: Worlds"),
    AppScreenRouteSpec(
        "providers",
        "Jump: Providers",
        "Open the Providers screen",
        "g,p",
        "Jump: Providers",
    ),
    AppScreenRouteSpec("eval", "Run eval suite", "Open the Eval screen", "g,e", "Jump: Eval"),
    AppScreenRouteSpec(
        "benchmark",
        "Run benchmark",
        "Open the Benchmark screen",
        "g,b",
        "Jump: Benchmark",
    ),
    AppScreenRouteSpec("runs", "Jump: Runs", "Open preserved run history", "g,u", "Jump: Runs"),
)
APP_SCREEN_NAMES: tuple[AppScreenName, ...] = tuple(spec.name for spec in APP_SCREEN_ROUTE_SPECS)
SYSTEM_COMMAND_SPECS: tuple[SystemCommandSpec, ...] = (
    *(
        SystemCommandSpec(spec.system_title, spec.system_help, spec.name)
        for spec in APP_SCREEN_ROUTE_SPECS
    ),
    SystemCommandSpec("New world", "Open the Worlds screen and start a new world", "new-world"),
    SystemCommandSpec("Open Help", "Show the bindings on the active screen", "help"),
    SystemCommandSpec(
        "Switch theme",
        "Cycle worldforge-dark, worldforge-light, and worldforge-high-contrast",
        "theme",
    ),
)
APP_BINDING_SPECS: tuple[AppBindingSpec, ...] = (
    AppBindingSpec("?", "show_help", "Help"),
    AppBindingSpec("q", "quit", "Quit"),
    AppBindingSpec("ctrl+t", "toggle_theme", "Theme", show=False),
    *(
        AppBindingSpec(
            spec.binding_key,
            f"switch_screen('{spec.name}')",
            spec.binding_description,
            show=False,
        )
        for spec in APP_SCREEN_ROUTE_SPECS
    ),
)


def palette_item_specs(
    *,
    world_ids: Iterable[str],
    providers: Iterable[str],
    report_paths: Iterable[Path],
    run_records: Iterable[SupportsRunWorkspace],
) -> tuple[PaletteItemSpec, ...]:
    items: list[PaletteItemSpec] = []
    items.extend(
        PaletteItemSpec(
            title=f"World: {world_id}",
            help_text="Open the Worlds screen",
            kind="world",
            value=world_id,
        )
        for world_id in world_ids
    )
    items.extend(
        PaletteItemSpec(
            title=f"Provider: {provider}",
            help_text="Open the Providers screen",
            kind="provider",
            value=provider,
        )
        for provider in providers
    )
    items.extend(
        PaletteItemSpec(
            title=f"Run: {path.name}",
            help_text="Open the preserved report",
            kind="report",
            value=path,
        )
        for path in report_paths
    )
    items.extend(
        PaletteItemSpec(
            title=f"Run workspace: {record.run_id}",
            help_text="Open the preserved run workspace",
            kind="run-workspace",
            value=record.path,
        )
        for record in run_records
    )
    return tuple(items)


def flow_system_command_title(flow_title: str) -> str:
    return f"Run flow: {flow_title}"


def flow_system_command_help(short_title: str) -> str:
    return f"Switch the Run Inspector to {short_title} and run it"


def app_screen_name(value: object) -> AppScreenName | None:
    if value in APP_SCREEN_NAMES:
        return cast(AppScreenName, value)
    return None


def initial_screen_name(value: object) -> AppScreenName:
    screen_name = app_screen_name(value)
    if screen_name is not None:
        return screen_name
    return "home"


def screen_needs_run_inspector_refresh(
    screen_name: str,
    *,
    is_run_inspector: bool,
    can_run_flows: bool,
) -> bool:
    return screen_name == "run-inspector" and is_run_inspector and not can_run_flows
