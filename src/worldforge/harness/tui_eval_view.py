"""Textual-free eval/report view helpers for TheWorldHarness."""

from __future__ import annotations

from dataclasses import dataclass

from worldforge.harness.tui_log_view import RichLogSpec
from worldforge.harness.tui_report_view import (
    ReportCompletionSpec,
    ReportRunControlSpec,
)
from worldforge.harness.tui_report_view import (
    report_saved_message as _report_saved_message,
)


@dataclass(frozen=True, slots=True)
class EvalSelectSpec:
    widget_id: str
    label: str
    default: str | None = None


@dataclass(frozen=True, slots=True)
class EvalButtonSpec:
    widget_id: str
    label: str
    variant: str


@dataclass(frozen=True, slots=True)
class EvalBindingSpec:
    key: str
    action: str
    description: str
    show: bool = True


@dataclass(frozen=True, slots=True)
class EvalOutputSpec:
    widget_id: str
    empty_message: str


@dataclass(frozen=True, slots=True)
class EvalScreenSpec:
    root_id: str
    form_id: str
    output_id: str
    suite: EvalSelectSpec
    provider: EvalSelectSpec
    run: EvalButtonSpec
    verdict: EvalOutputSpec
    log: RichLogSpec
    completion: ReportCompletionSpec
    run_control: ReportRunControlSpec


@dataclass(frozen=True, slots=True)
class EvalRunRequest:
    suite_id: str
    provider: str


EVAL_SCREEN_SPEC = EvalScreenSpec(
    root_id="eval-root",
    form_id="eval-form",
    output_id="eval-output",
    suite=EvalSelectSpec("eval-suite", "Suite", "planning"),
    provider=EvalSelectSpec("eval-provider", "Provider"),
    run=EvalButtonSpec("eval-run", "Run eval", "primary"),
    verdict=EvalOutputSpec("eval-verdict", "No suite run yet — press r to execute."),
    log=RichLogSpec("eval-log"),
    completion=ReportCompletionSpec(
        kind="eval",
        export_widget_id="eval-export",
        status_widget_id="eval-verdict",
    ),
    run_control=ReportRunControlSpec(
        worker_group="eval",
        worker_name="eval.run",
        notify_title="Eval",
        cancel_message="Cancelled eval run.",
        mismatch_title="Capability mismatch",
    ),
)
EVAL_BINDING_SPECS: tuple[EvalBindingSpec, ...] = (
    EvalBindingSpec("r", "run_eval", "Run"),
    EvalBindingSpec("escape", "cancel_or_back", "Cancel/Back"),
)
EVAL_RUN_BUTTON_ID = EVAL_SCREEN_SPEC.run.widget_id
EVAL_LOG_SELECTOR = EVAL_SCREEN_SPEC.log.selector


def eval_request_from_form(
    *,
    suite_value: object,
    provider_value: object,
) -> EvalRunRequest | None:
    """Return an eval run request when both select values are concrete strings."""

    if not isinstance(suite_value, str) or not isinstance(provider_value, str):
        return None
    return EvalRunRequest(suite_id=suite_value, provider=provider_value)


def eval_running_log_line(suite_id: str, provider: str) -> str:
    return f"running {suite_id} x {provider}"


def report_saved_message(path: object) -> str:
    return _report_saved_message(path)
