"""Textual-free provider-event helpers for TheWorldHarness TUI screens."""

from __future__ import annotations

import time

from rich.text import Text

from worldforge.models import ProviderEvent


def format_provider_event(event: ProviderEvent, *, timestamp: str | None = None) -> Text:
    phase_styles = {
        "success": "bold green",
        "failure": "bold red",
        "retry": "bold yellow",
        "cancelled": "bold yellow",
    }
    duration = f"{event.duration_ms:.1f} ms" if event.duration_ms is not None else "n/a"
    rendered_timestamp = timestamp if timestamp is not None else time.strftime("%H:%M:%S")
    text = Text()
    text.append(f"{rendered_timestamp} ", style="dim")
    text.append(f"{event.phase:<9}", style=phase_styles.get(event.phase, "bold"))
    text.append(f" {event.provider}.{event.operation} ")
    text.append(f"({duration})", style="dim")
    return text


def provider_event_failure(provider: str, operation: str, exc: Exception) -> ProviderEvent:
    return ProviderEvent(
        provider=provider,
        operation=operation,
        phase="failure",
        message=str(exc),
    )


def provider_event_summary(event: ProviderEvent) -> dict[str, object]:
    return {
        "phase": event.phase,
        "latency_ms": event.duration_ms,
        "retries": max(0, event.attempt - 1),
    }
