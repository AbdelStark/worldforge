"""Unified harness flow specs binding metadata, runners, and rendering facts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from worldforge.harness import cosmos_policy_flow as _cosmos_policy_flow
from worldforge.harness import groot_replay_flow as _groot_replay_flow
from worldforge.harness import robotics_compare_flow as _robotics_compare_flow
from worldforge.harness.basic_flows import run_diagnostics_demo, run_workbench_demo
from worldforge.harness.flow_catalog import FLOWS
from worldforge.harness.flow_events import provider_events_for
from worldforge.harness.flow_rendering import (
    _cosmos_policy_metrics,
    _cosmos_policy_steps,
    _cosmos_policy_transcript,
    _diagnostics_metrics,
    _diagnostics_steps,
    _diagnostics_transcript,
    _gr00t_replay_metrics,
    _gr00t_replay_steps,
    _gr00t_replay_transcript,
    _lerobot_metrics,
    _lerobot_steps,
    _lerobot_transcript,
    _leworldmodel_metrics,
    _leworldmodel_steps,
    _leworldmodel_transcript,
    _robotics_compare_metrics,
    _robotics_compare_steps,
    _robotics_compare_transcript,
    _workbench_metrics,
    _workbench_steps,
    _workbench_transcript,
)
from worldforge.harness.models import HarnessFlow, HarnessMetric, HarnessRun, HarnessStep
from worldforge.models import JSONDict

FlowRunner = Callable[..., JSONDict]
StepBuilder = Callable[[JSONDict], tuple[HarnessStep, ...]]
MetricBuilder = Callable[[JSONDict], tuple[HarnessMetric, ...]]
TranscriptBuilder = Callable[[JSONDict], tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class HarnessFlowSpec:
    """One harness flow with its metadata, default runner, and summary renderers."""

    flow: HarnessFlow
    runner: FlowRunner
    steps: StepBuilder
    metrics: MetricBuilder
    transcript: TranscriptBuilder

    def run_from_summary(
        self,
        *,
        state_dir: Path,
        summary: JSONDict,
        workspace_path: Path,
    ) -> HarnessRun:
        """Render a captured summary into a complete harness run."""

        from worldforge.harness.flow_rendering import metrics_for, steps_for, transcript_for

        return HarnessRun(
            flow=self.flow,
            state_dir=state_dir,
            summary=summary,
            steps=steps_for(self.flow.id, summary),
            metrics=metrics_for(self.flow.id, summary),
            transcript=transcript_for(self.flow.id, summary),
            workspace_path=workspace_path,
            provider_events=self.provider_events(summary),
            validation_errors=tuple(str(error) for error in summary.get("validation_errors", [])),
        )

    def provider_events(self, summary: JSONDict) -> tuple[JSONDict, ...]:
        """Return sanitized provider events for this flow summary."""

        return provider_events_for(self.flow.id, summary, flows=_FLOW_INDEX)


def cosmos_policy_saved_replay_payload() -> JSONDict:
    return _cosmos_policy_flow.cosmos_policy_saved_replay_payload()


def load_cosmos_policy_replay_artifact(path: Path) -> JSONDict:
    return _cosmos_policy_flow.load_cosmos_policy_replay_artifact(path)


def validate_cosmos_policy_replay_request(payload: object, saved_request: JSONDict) -> None:
    _cosmos_policy_flow.validate_cosmos_policy_replay_request(payload, saved_request)


def cosmos_policy_policy_info_from_replay(replay_artifact: JSONDict) -> JSONDict:
    return _cosmos_policy_flow.cosmos_policy_policy_info_from_replay(replay_artifact)


def cosmos_policy_response_payload(replay_artifact: JSONDict) -> JSONDict:
    return _cosmos_policy_flow.cosmos_policy_response_payload(replay_artifact)


def run_cosmos_policy_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
    return _cosmos_policy_flow.run_cosmos_policy_demo(
        state_dir=state_dir,
        emit=emit,
        response_payload=cosmos_policy_response_payload,
    )


def groot_saved_replay_payload() -> JSONDict:
    return _groot_replay_flow.groot_saved_replay_payload()


def load_groot_replay_artifact(path: Path) -> JSONDict:
    return _groot_replay_flow.load_groot_replay_artifact(path)


def groot_eef_rows(raw_actions: JSONDict) -> list[list[float]]:
    return _groot_replay_flow.groot_eef_rows(raw_actions)


def run_gr00t_replay_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
    return _groot_replay_flow.run_groot_replay_demo(
        state_dir=state_dir,
        emit=emit,
        eef_rows=groot_eef_rows,
    )


def run_leworldmodel_demo(*, state_dir: Path | None = None, emit: bool = False) -> JSONDict:
    from worldforge.demos import leworldmodel_e2e

    del state_dir
    return leworldmodel_e2e.run_demo(emit=emit)


def run_lerobot_demo(*, state_dir: Path | None = None, emit: bool = False) -> JSONDict:
    from worldforge.demos import lerobot_e2e

    del state_dir
    return lerobot_e2e.run_demo(emit=emit)


def run_robotics_compare_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
    return _robotics_compare_flow.run_robotics_compare_demo(
        state_dir=state_dir,
        emit=emit,
        runners=_robotics_compare_flow.RoboticsCompareRunners(
            lerobot=run_lerobot_demo,
            cosmos_policy=run_cosmos_policy_demo,
            groot_replay=run_gr00t_replay_demo,
        ),
    )


def robotics_compare_lerobot_row(summary: JSONDict) -> JSONDict:
    return _robotics_compare_flow.robotics_compare_lerobot_row(summary)


def robotics_compare_cosmos_row(summary: JSONDict) -> JSONDict:
    return _robotics_compare_flow.robotics_compare_cosmos_row(summary)


def robotics_compare_groot_row(summary: JSONDict) -> JSONDict:
    return _robotics_compare_flow.robotics_compare_groot_row(summary)


def harness_artifact_payload(summary: JSONDict, name: str) -> JSONDict:
    return _robotics_compare_flow.harness_artifact_payload(summary, name)


def flow_specs() -> tuple[HarnessFlowSpec, ...]:
    """Return packaged harness flow specs in public metadata order."""

    return FLOW_SPECS


def flow_spec_index() -> dict[str, HarnessFlowSpec]:
    """Return packaged harness flow specs keyed by flow id."""

    return dict(_FLOW_SPEC_INDEX)


def flow_spec(flow_id: str) -> HarnessFlowSpec:
    """Return one packaged harness flow spec."""

    try:
        return _FLOW_SPEC_INDEX[flow_id]
    except KeyError as exc:
        valid = ", ".join(sorted(_FLOW_SPEC_INDEX))
        raise ValueError(f"unknown harness flow '{flow_id}'. Valid flows: {valid}.") from exc


_FLOW_INDEX = {flow.id: flow for flow in FLOWS}

FLOW_SPECS: tuple[HarnessFlowSpec, ...] = (
    HarnessFlowSpec(
        flow=_FLOW_INDEX["leworldmodel"],
        runner=run_leworldmodel_demo,
        steps=_leworldmodel_steps,
        metrics=_leworldmodel_metrics,
        transcript=_leworldmodel_transcript,
    ),
    HarnessFlowSpec(
        flow=_FLOW_INDEX["lerobot"],
        runner=run_lerobot_demo,
        steps=_lerobot_steps,
        metrics=_lerobot_metrics,
        transcript=_lerobot_transcript,
    ),
    HarnessFlowSpec(
        flow=_FLOW_INDEX["cosmos-policy"],
        runner=run_cosmos_policy_demo,
        steps=_cosmos_policy_steps,
        metrics=_cosmos_policy_metrics,
        transcript=_cosmos_policy_transcript,
    ),
    HarnessFlowSpec(
        flow=_FLOW_INDEX["gr00t-replay"],
        runner=run_gr00t_replay_demo,
        steps=_gr00t_replay_steps,
        metrics=_gr00t_replay_metrics,
        transcript=_gr00t_replay_transcript,
    ),
    HarnessFlowSpec(
        flow=_FLOW_INDEX["robotics-compare"],
        runner=run_robotics_compare_demo,
        steps=_robotics_compare_steps,
        metrics=_robotics_compare_metrics,
        transcript=_robotics_compare_transcript,
    ),
    HarnessFlowSpec(
        flow=_FLOW_INDEX["diagnostics"],
        runner=run_diagnostics_demo,
        steps=_diagnostics_steps,
        metrics=_diagnostics_metrics,
        transcript=_diagnostics_transcript,
    ),
    HarnessFlowSpec(
        flow=_FLOW_INDEX["workbench"],
        runner=run_workbench_demo,
        steps=_workbench_steps,
        metrics=_workbench_metrics,
        transcript=_workbench_transcript,
    ),
)
_FLOW_SPEC_INDEX = {spec.flow.id: spec for spec in FLOW_SPECS}
