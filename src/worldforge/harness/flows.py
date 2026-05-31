"""Flow definitions and runners for robotics showcase evidence."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from worldforge.harness import cosmos_policy_flow as _cosmos_policy_flow
from worldforge.harness import groot_replay_flow as _groot_replay_flow
from worldforge.harness import robotics_compare_flow as _robotics_compare_flow
from worldforge.harness.basic_flows import (
    run_diagnostics_demo as _run_diagnostics_demo,
)
from worldforge.harness.basic_flows import (
    run_workbench_demo as _run_workbench_demo,
)
from worldforge.harness.flow_catalog import FLOWS as FLOWS
from worldforge.harness.flow_catalog import available_flows as available_flows
from worldforge.harness.flow_catalog import flow_index as flow_index
from worldforge.harness.flow_catalog import flow_to_dicts as flow_to_dicts
from worldforge.harness.flow_rendering import (
    metrics_for as _metrics_for,
)
from worldforge.harness.flow_rendering import (
    provider_events_for as _render_provider_events_for,
)
from worldforge.harness.flow_rendering import (
    steps_for as _steps_for,
)
from worldforge.harness.flow_rendering import (
    transcript_for as _transcript_for,
)
from worldforge.harness.flow_replay_utils import (
    preview_action_rows as _flow_preview_action_rows,
)
from worldforge.harness.flow_workspace import write_flow_artifacts
from worldforge.harness.flow_workspace import (
    write_flow_workspace as _write_flow_workspace,
)
from worldforge.harness.models import HarnessFlow, HarnessRun
from worldforge.harness.report_runs import (
    benchmark_report_harness_run as benchmark_report_harness_run,
)
from worldforge.harness.report_runs import (
    benchmark_run_artifacts as benchmark_run_artifacts,
)
from worldforge.harness.report_runs import (
    eval_report_harness_run as eval_report_harness_run,
)
from worldforge.harness.report_runs import (
    eval_run_artifacts as eval_run_artifacts,
)
from worldforge.harness.report_runs import (
    preserve_benchmark_run_workspace as preserve_benchmark_run_workspace,
)
from worldforge.harness.report_runs import (
    preserve_eval_run_workspace as preserve_eval_run_workspace,
)
from worldforge.harness.report_runs import (
    recent_report_paths as recent_report_paths,
)
from worldforge.harness.report_runs import (
    report_run_from_path as report_run_from_path,
)
from worldforge.harness.report_runs import (
    write_report as write_report,
)
from worldforge.harness.workspace import (
    create_run_workspace,
    workspace_root_for_state_dir,
)
from worldforge.models import (
    JSONDict,
    ProviderEvent,
    WorldForgeError,
)

FlowRunner = Callable[..., JSONDict]
_write_flow_artifacts = write_flow_artifacts


def _cosmos_policy_saved_replay_payload() -> JSONDict:
    return _cosmos_policy_flow.cosmos_policy_saved_replay_payload()


def _load_cosmos_policy_replay_artifact(path: Path) -> JSONDict:
    return _cosmos_policy_flow.load_cosmos_policy_replay_artifact(path)


def _validate_cosmos_policy_replay_request(payload: object, saved_request: JSONDict) -> None:
    _cosmos_policy_flow.validate_cosmos_policy_replay_request(payload, saved_request)


def _cosmos_policy_policy_info_from_replay(replay_artifact: JSONDict) -> JSONDict:
    return _cosmos_policy_flow.cosmos_policy_policy_info_from_replay(replay_artifact)


def _cosmos_policy_response_payload(replay_artifact: JSONDict) -> JSONDict:
    return _cosmos_policy_flow.cosmos_policy_response_payload(replay_artifact)


def _run_cosmos_policy_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
    return _cosmos_policy_flow.run_cosmos_policy_demo(
        state_dir=state_dir,
        emit=emit,
        response_payload=_cosmos_policy_response_payload,
    )


def _preview_action_rows(rows: object) -> list[list[float]]:
    return _flow_preview_action_rows(rows)


def _groot_saved_replay_payload() -> JSONDict:
    return _groot_replay_flow.groot_saved_replay_payload()


def _load_groot_replay_artifact(path: Path) -> JSONDict:
    return _groot_replay_flow.load_groot_replay_artifact(path)


def _groot_eef_rows(raw_actions: JSONDict) -> list[list[float]]:
    return _groot_replay_flow.groot_eef_rows(raw_actions)


def _run_gr00t_replay_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
    return _groot_replay_flow.run_groot_replay_demo(
        state_dir=state_dir,
        emit=emit,
        eef_rows=_groot_eef_rows,
    )


# Demo modules import the optional-runtime provider classes at module scope, so
# keep these imports lazy: loading the harness should not pull LeRobot/LeWorldModel
# adapters into the base cold-start path.
def _run_leworldmodel_demo(**kwargs: object) -> JSONDict:
    from worldforge.demos import leworldmodel_e2e

    return leworldmodel_e2e.run_demo(**kwargs)  # type: ignore[arg-type]


def _run_lerobot_demo(**kwargs: object) -> JSONDict:
    from worldforge.demos import lerobot_e2e

    return lerobot_e2e.run_demo(**kwargs)  # type: ignore[arg-type]


def _run_robotics_compare_demo(*, state_dir: Path, emit: bool = False) -> JSONDict:
    return _robotics_compare_flow.run_robotics_compare_demo(
        state_dir=state_dir,
        emit=emit,
        runners=_robotics_compare_flow.RoboticsCompareRunners(
            lerobot=_run_lerobot_demo,
            cosmos_policy=_run_cosmos_policy_demo,
            groot_replay=_run_gr00t_replay_demo,
        ),
    )


def _robotics_compare_lerobot_row(summary: JSONDict) -> JSONDict:
    return _robotics_compare_flow.robotics_compare_lerobot_row(summary)


def _robotics_compare_cosmos_row(summary: JSONDict) -> JSONDict:
    return _robotics_compare_flow.robotics_compare_cosmos_row(summary)


def _robotics_compare_groot_row(summary: JSONDict) -> JSONDict:
    return _robotics_compare_flow.robotics_compare_groot_row(summary)


def _harness_artifact_payload(summary: JSONDict, name: str) -> JSONDict:
    return _robotics_compare_flow.harness_artifact_payload(summary, name)


_RUNNERS: dict[str, FlowRunner] = {
    "leworldmodel": _run_leworldmodel_demo,
    "lerobot": _run_lerobot_demo,
    "cosmos-policy": _run_cosmos_policy_demo,
    "gr00t-replay": _run_gr00t_replay_demo,
    "robotics-compare": _run_robotics_compare_demo,
    "diagnostics": _run_diagnostics_demo,
    "workbench": _run_workbench_demo,
}


def run_flow(flow_id: str, *, state_dir: Path | None = None) -> HarnessRun:
    """Execute one harness flow and return visualizable run data."""

    flows = flow_index()
    if flow_id not in flows:
        valid = ", ".join(sorted(flows))
        raise WorldForgeError(f"unknown harness flow '{flow_id}'. Valid flows: {valid}.")

    flow = flows[flow_id]
    resolved_state_dir = state_dir or Path(
        tempfile.mkdtemp(prefix=f"worldforge-robotics-flow-{flow_id}-")
    )
    workspace = create_run_workspace(
        workspace_root_for_state_dir(resolved_state_dir),
        kind="flow",
        command=flow.command,
        provider=flow.provider,
        operation=flow.id,
    )
    try:
        summary = _RUNNERS[flow_id](state_dir=resolved_state_dir, emit=False)
    except Exception as exc:
        summary = _failed_flow_summary(flow_id, resolved_state_dir, exc)
        run = _run_from_summary(
            flow=flow,
            state_dir=resolved_state_dir,
            summary=summary,
            workspace_path=workspace.path,
        )
        _write_flow_workspace(workspace, run)
        return run

    run = _run_from_summary(
        flow=flow,
        state_dir=resolved_state_dir,
        summary=summary,
        workspace_path=workspace.path,
    )
    _write_flow_workspace(workspace, run)
    return run


def _run_from_summary(
    *,
    flow: HarnessFlow,
    state_dir: Path,
    summary: JSONDict,
    workspace_path: Path,
) -> HarnessRun:
    return HarnessRun(
        flow=flow,
        state_dir=state_dir,
        summary=summary,
        steps=_steps_for(flow.id, summary),
        metrics=_metrics_for(flow.id, summary),
        transcript=_transcript_for(flow.id, summary),
        workspace_path=workspace_path,
        provider_events=_provider_events_for(flow.id, summary),
        validation_errors=tuple(str(error) for error in summary.get("validation_errors", [])),
    )


def _failed_flow_summary(flow_id: str, state_dir: Path, exc: Exception) -> JSONDict:
    event = ProviderEvent(
        provider=flow_index()[flow_id].provider,
        operation=flow_id,
        phase="failure",
        message=str(exc),
    )
    return {
        "demo_kind": "harness_flow",
        "state_dir": str(state_dir),
        "status": "failed",
        "event_phases": [event.phase],
        "provider_events": [event.to_dict()],
        "validation_errors": [event.message],
    }


def _provider_events_for(flow_id: str, summary: JSONDict) -> tuple[JSONDict, ...]:
    return _render_provider_events_for(flow_id, summary, flows=flow_index())
