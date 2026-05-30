"""Textual-free report completion contracts for TheWorldHarness."""

from __future__ import annotations

from dataclasses import dataclass


def report_saved_message(path: object) -> str:
    return f"Report saved: {path}"


@dataclass(frozen=True, slots=True)
class ReportCompletionSpec:
    kind: str
    export_widget_id: str
    status_widget_id: str

    @property
    def export_selector(self) -> str:
        return f"#{self.export_widget_id}"

    @property
    def status_selector(self) -> str:
        return f"#{self.status_widget_id}"

    def saved_message(self, path: object) -> str:
        return report_saved_message(path)


@dataclass(frozen=True, slots=True)
class ReportRunControlSpec:
    worker_group: str
    worker_name: str
    notify_title: str
    cancel_message: str
    mismatch_title: str
    mismatch_log_style: str = "bold red"
