"""Textual-free Run Inspector view contracts for TheWorldHarness."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from worldforge.harness.models import HarnessFlow, HarnessStep

RUN_INSPECTOR_DEFAULT_FLOW_ID = "leworldmodel"
RUN_INSPECTOR_DEFAULT_STEP_DELAY_SECONDS = 0.18
RUN_INSPECTOR_RUN_BUTTON_LABEL = "Run selected flow"
RUN_INSPECTOR_READY_STEPS: tuple[HarnessStep, ...] = (
    HarnessStep(
        "Ready",
        "Select a flow and press Run to visualize the integration path.",
        "Waiting for execution.",
    ),
)


@dataclass(frozen=True, slots=True)
class RunInspectorButtonSpec:
    widget_id: str
    label: str
    variant: str


@dataclass(frozen=True, slots=True)
class RunInspectorScreenSpec:
    root_id: str
    body_id: str
    hero_id: str
    rail_id: str
    flow_select_id: str
    run: RunInspectorButtonSpec
    flow_timeline_id: str
    report_column_id: str
    inspector_column_id: str
    inspector_id: str
    transcript_id: str
    export_preview_id: str


@dataclass(frozen=True, slots=True)
class FlowBindingSpec:
    key: str
    action: str
    description: str
    show: bool = True


RUN_INSPECTOR_SCREEN_SPEC = RunInspectorScreenSpec(
    root_id="root",
    body_id="body",
    hero_id="hero",
    rail_id="rail",
    flow_select_id="flow-select",
    run=RunInspectorButtonSpec("run-button", RUN_INSPECTOR_RUN_BUTTON_LABEL, "warning"),
    flow_timeline_id="timeline",
    report_column_id="timeline",
    inspector_column_id="inspector-column",
    inspector_id="inspector",
    transcript_id="transcript",
    export_preview_id="export-preview",
)
RUN_INSPECTOR_BINDING_SPECS: tuple[FlowBindingSpec, ...] = (
    FlowBindingSpec("r", "run_selected", "Run"),
)
RUN_INSPECTOR_FLOW_SELECT_ID = RUN_INSPECTOR_SCREEN_SPEC.flow_select_id
RUN_INSPECTOR_RUN_BUTTON_ID = RUN_INSPECTOR_SCREEN_SPEC.run.widget_id
RUN_INSPECTOR_TIMELINE_ID = RUN_INSPECTOR_SCREEN_SPEC.flow_timeline_id
RUN_INSPECTOR_INSPECTOR_ID = RUN_INSPECTOR_SCREEN_SPEC.inspector_id
RUN_INSPECTOR_TRANSCRIPT_ID = RUN_INSPECTOR_SCREEN_SPEC.transcript_id
RUN_INSPECTOR_EXPORT_PREVIEW_ID = RUN_INSPECTOR_SCREEN_SPEC.export_preview_id


def run_inspector_flow_bindings(flows: Sequence[HarnessFlow]) -> tuple[FlowBindingSpec, ...]:
    return tuple(
        FlowBindingSpec(
            key=str(index),
            action=f"select_flow('{flow.id}')",
            description=flow.short_title,
        )
        for index, flow in enumerate(flows, start=1)
    )


def run_inspector_flow_options(flows: Sequence[HarnessFlow]) -> tuple[tuple[str, str], ...]:
    return tuple((flow.title, flow.id) for flow in flows)


def run_inspector_flow_card_id(flow: HarnessFlow) -> str:
    return f"flow-card-{flow.id}"


def resolve_run_inspector_flow_id(
    requested_flow_id: str,
    flows: Mapping[str, HarnessFlow],
) -> str:
    if requested_flow_id in flows:
        return requested_flow_id
    if RUN_INSPECTOR_DEFAULT_FLOW_ID in flows:
        return RUN_INSPECTOR_DEFAULT_FLOW_ID
    for flow_id in flows:
        return flow_id
    raise ValueError("run inspector requires at least one flow")
