"""Textual-free modal view helpers for TheWorldHarness."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class HelpTextSpec:
    widget_id: str
    text: str


@dataclass(frozen=True, slots=True)
class HelpBindingSpec:
    key: str
    action: str
    description: str
    show: bool = True


@dataclass(frozen=True, slots=True)
class HelpTableSpec:
    widget_id: str
    columns: tuple[str, ...]

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"


@dataclass(frozen=True, slots=True)
class HelpModalSpec:
    card_id: str
    title: HelpTextSpec
    table: HelpTableSpec
    footnote: HelpTextSpec


HELP_MODAL_SPEC = HelpModalSpec(
    card_id="help-card",
    title=HelpTextSpec("help-title", "Bindings on this screen"),
    table=HelpTableSpec("help-table", ("Key", "Description", "Action")),
    footnote=HelpTextSpec(
        "help-footnote",
        "Press [bold]Esc[/] or [bold]q[/] to close. [bold]Ctrl+P[/] opens the command palette.",
    ),
)
HELP_TABLE_SELECTOR = HELP_MODAL_SPEC.table.selector
HELP_BINDING_SPECS: tuple[HelpBindingSpec, ...] = (
    HelpBindingSpec("escape", "dismiss", "Close"),
    HelpBindingSpec("q", "dismiss", "Close", show=False),
)


@dataclass(frozen=True, slots=True)
class PlaceholderTextSpec:
    widget_id: str
    text: str


@dataclass(frozen=True, slots=True)
class PlaceholderModalSpec:
    card_id: str
    title_id: str
    title_prefix: str
    body_id: str
    footnote: PlaceholderTextSpec


PLACEHOLDER_MODAL_SPEC = PlaceholderModalSpec(
    card_id="placeholder-card",
    title_id="placeholder-title",
    title_prefix="Coming in milestone",
    body_id="placeholder-body",
    footnote=PlaceholderTextSpec(
        "placeholder-footnote",
        "Press [bold]Esc[/], [bold]q[/], or [bold]Enter[/] to close.",
    ),
)
PLACEHOLDER_BINDING_SPECS: tuple[HelpBindingSpec, ...] = (
    HelpBindingSpec("escape", "dismiss", "Close"),
    HelpBindingSpec("q", "dismiss", "Close", show=False),
    HelpBindingSpec("enter", "dismiss", "Close", show=False),
)


def placeholder_title(target_milestone: str) -> str:
    return f"{PLACEHOLDER_MODAL_SPEC.title_prefix} {target_milestone}"


class SupportsBinding(Protocol):
    key: str
    action: str
    description: str | None


@dataclass(frozen=True, slots=True)
class HelpBindingRow:
    key: str
    description: str
    action: str


def help_binding_rows(source_screen: object | None) -> tuple[HelpBindingRow, ...]:
    if source_screen is None:
        return ()
    seen: set[tuple[str, str]] = set()
    rows: list[HelpBindingRow] = []
    for source in (source_screen, getattr(source_screen, "app", None)):
        for binding in _source_bindings(source):
            fingerprint = (binding.key, binding.action)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            rows.append(
                HelpBindingRow(
                    key=binding.key,
                    description=binding.description or "",
                    action=binding.action,
                )
            )
    return tuple(rows)


def _source_bindings(source: object | None) -> Iterable[SupportsBinding]:
    bindings = getattr(source, "_bindings", None)
    key_to_bindings = getattr(bindings, "key_to_bindings", None)
    items = getattr(key_to_bindings, "items", None)
    if not callable(items):
        return ()
    return (binding for _key, binding_list in items() for binding in binding_list)
