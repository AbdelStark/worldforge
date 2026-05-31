"""Textual-free log view contracts for TheWorldHarness screens."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_RICH_LOG_MAX_LINES = 5000


@dataclass(frozen=True, slots=True)
class RichLogSpec:
    widget_id: str
    max_lines: int = DEFAULT_RICH_LOG_MAX_LINES

    def __post_init__(self) -> None:
        if self.max_lines <= 0:
            raise ValueError("RichLog max_lines must be positive.")

    @property
    def selector(self) -> str:
        return f"#{self.widget_id}"
